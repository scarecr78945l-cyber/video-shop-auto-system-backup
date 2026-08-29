"""M0 调度器测试（WorkflowScheduler）：断点自愈 / 单轮驱动 / 节流熔断 / 常驻循环。

对齐 09 文档第三节（节流 0~4 级、连续失败 ≥2 熔断、resume_on_startup 断点恢复）。
运行：python -m pytest tests -q --basetemp=".pytest-tmp-m0"（P-001/P-011，宪法第 12 节）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest

from foundation.config import FoundationConfig
from foundation.db import Database
from foundation.repo import WorkflowQueue
from foundation.scheduler import (
    LoggingWorker,
    Worker,
    WorkflowScheduler,
    default_worker_id,
)
from foundation.tables import STAGE_VALUES, WorkflowJob


class MockWorker(Worker):
    """脚本化 worker：按队列依次返回结果；耗尽后默认成功。"""

    def __init__(self, results: list[dict] | None = None):
        self.results = list(results or [])
        self.executed: list[int] = []

    def execute(self, job: WorkflowJob) -> dict:
        self.executed.append(job.id)
        if self.results:
            return self.results.pop(0)
        return {"ok": True, "error_code": None, "evidence": {"mock": True}}


def _fail(code: str = "RATE_LIMIT") -> dict:
    return {"ok": False, "error_code": code, "evidence": {"reason": "mock failure"}}


@pytest.fixture()
def sched() -> WorkflowScheduler:
    cfg = FoundationConfig(db_url="sqlite:///:memory:", lease_minutes=45, data_dir=Path("."))
    database = Database(cfg)
    database.create_all()
    database.seed()
    queue = WorkflowQueue(database)
    return WorkflowScheduler(queue, MockWorker(), config=cfg.scheduler, worker_id="test-worker")


def test_resume_on_startup_recovers_expired_leases(sched: WorkflowScheduler) -> None:
    """断点自愈：崩溃遗留的 running 过期租约 → 重置 pending，恢复数正确。"""
    job = sched.queue.enqueue(product_id=1, stage="source_collect")
    sched.queue.claim(worker_id="old-worker")
    with sched.queue.database.session() as session:
        db_job = session.get(WorkflowJob, job.id)
        db_job.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    recovered = sched.resume_on_startup()
    assert recovered == 1
    done = sched.queue.get(job.id)
    assert done.status == "pending"
    assert done.lease_owner is None


def test_run_once_executes_and_completes(sched: WorkflowScheduler) -> None:
    """单轮：领取到期 job → worker 成功 → complete 落库。"""
    job = sched.queue.enqueue(product_id=1, stage="alibaba_quote", payload={"sku": "A1"})
    stats = sched.run_once()
    assert stats["claimed"] == 1 and stats["succeeded"] == 1 and stats["failed"] == 0
    done = sched.queue.get(job.id)
    assert done.status == "success"
    assert done.evidence_json == {"mock": True}


def test_run_once_failure_applies_error_policy(sched: WorkflowScheduler) -> None:
    """单轮失败：RATE_LIMIT → fail 回写（pending + retry_after≈now+180s）。"""
    sched.worker.results.append(_fail("RATE_LIMIT"))
    job = sched.queue.enqueue(product_id=1, stage="source_collect")
    now = datetime.now(timezone.utc)
    stats = sched.run_once()
    assert stats["failed"] == 1 and stats["succeeded"] == 0
    done = sched.queue.get(job.id)
    assert done.status == "pending"
    assert done.error_code == "RATE_LIMIT"
    assert done.retry_count == 1
    assert done.retry_after is not None
    assert abs((done.retry_after - (now + timedelta(seconds=180))).total_seconds()) <= 10


def test_manual_takeover_error_pauses_job_only(sched: WorkflowScheduler) -> None:
    """VERIFICATION_REQUIRED → waiting_verification（人工接管），其他 job 不受影响。"""
    sched.worker.results.append(_fail("VERIFICATION_REQUIRED"))
    j1 = sched.queue.enqueue(product_id=1, stage="source_collect")
    j2 = sched.queue.enqueue(product_id=2, stage="source_collect")
    # 一轮领取两个（limit=10）：j1 fail 为等待验证（人工接管），j2 默认成功——失败隔离生效
    stats1 = sched.run_once()
    assert stats1["failed"] == 1 and stats1["succeeded"] == 1
    assert sched.queue.get(j1.id).status == "waiting_verification"  # 单任务暂停
    assert sched.queue.get(j2.id).status == "success"  # 不阻塞其他 job
    # 后续轮次无 pending，安全返回
    assert sched.run_once()["claimed"] == 0


def test_circuit_breaker_pauses_stage_after_consecutive_failures(sched: WorkflowScheduler) -> None:
    """熔断：连续失败 ≥2 → 暂停整个 stage，后续轮次不领取该 stage 任务。"""
    sched.worker.results.extend([_fail("UNEXPECTED"), _fail("UNEXPECTED")])
    sched.queue.enqueue(product_id=1, stage="source_collect")
    sched.queue.enqueue(product_id=2, stage="source_collect")
    sched.run_once()  # 失败 1
    sched.run_once()  # 失败 2 → 熔断
    # 第三次：该 stage 熔断，不领取（新任务也不领取）
    sched.queue.enqueue(product_id=3, stage="source_collect")
    stats = sched.run_once()
    assert stats["claimed"] == 0
    assert "source_collect" in stats["paused_stages"]
    # 其他 stage 不受影响
    sched.queue.enqueue(product_id=4, stage="shop_ads_report")
    stats2 = sched.run_once()
    assert stats2["claimed"] == 1 and stats2["succeeded"] == 1


def test_stage_recovers_after_cooldown(sched: WorkflowScheduler) -> None:
    """熔断冷却：暂停到期后 stage 自动恢复（探针恢复语义）。"""
    sched.worker.results.extend([_fail("UNEXPECTED"), _fail("UNEXPECTED")])
    sched.queue.enqueue(product_id=1, stage="source_collect")
    sched.queue.enqueue(product_id=2, stage="source_collect")
    sched.run_once()
    sched.run_once()  # 熔断
    assert sched.run_once()["claimed"] == 0
    # 手动把暂停时间改为过去（模拟冷却到期）
    sched._stage_paused_until["source_collect"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    sched.queue.enqueue(product_id=3, stage="source_collect")
    stats = sched.run_once()
    assert stats["claimed"] == 1 and stats["succeeded"] == 1
    assert sched._stage_failures.get("source_collect", 0) == 0  # 成功后失败计数清零


def test_all_stages_paused_skips_round(sched: WorkflowScheduler) -> None:
    """全部 stage 熔断 → 本轮直接跳过不领取。"""
    for stage in STAGE_VALUES:
        sched._stage_paused_until[stage] = datetime.now(timezone.utc) + timedelta(hours=1)
    sched.queue.enqueue(product_id=1, stage="source_collect")
    stats = sched.run_once()
    assert stats["claimed"] == 0
    assert len(stats["paused_stages"]) == len(STAGE_VALUES)


def test_run_forever_stops_via_event(sched: WorkflowScheduler) -> None:
    """常驻循环：stop_event 预置 → 快速优雅退出。"""
    stop = Event()
    stop.set()
    sched.run_forever(interval=0.05, stop_event=stop)  # 不应阻塞/抛异常


def test_run_forever_executes_at_least_one_round(sched: WorkflowScheduler) -> None:
    """常驻循环：正常跑至少一轮后由 stop_event 停止。"""
    sched.queue.enqueue(product_id=1, stage="source_collect")
    stop = Event()

    def _later_stop() -> None:
        import threading
        threading.Timer(0.3, stop.set).start()

    _later_stop()
    sched.run_forever(interval=0.05, stop_event=stop)
    assert sched.queue.get(1).status == "success"  # 第一轮已执行


def test_worker_id_format() -> None:
    """worker_id 格式：hostname-pid（进程级唯一，重启换新）。"""
    wid = default_worker_id()
    assert "-" in wid
    parts = wid.rsplit("-", 1)
    assert parts[1].isdigit()


def test_logging_worker_returns_ok(sched: WorkflowScheduler) -> None:
    """CLI 默认 LoggingWorker：不执行业务、返回 ok（演示/占位）。"""
    lw = LoggingWorker()
    job = sched.queue.enqueue(product_id=1, stage="source_collect")
    result = lw.execute(job)
    assert result["ok"] is True


def test_success_resets_stage_failures(sched: WorkflowScheduler) -> None:
    """成功重置 stage 失败计数（单次失败不熔断，成功后清零）。"""
    sched.worker.results.append(_fail("TIMEOUT"))
    sched.queue.enqueue(product_id=1, stage="source_collect")
    sched.run_once()  # 失败 1（未达阈值 2）
    assert sched._stage_failures.get("source_collect", 0) == 1
    sched.queue.enqueue(product_id=2, stage="source_collect")
    sched.run_once()  # 成功 → 清零
    assert sched._stage_failures.get("source_collect", 0) == 0
