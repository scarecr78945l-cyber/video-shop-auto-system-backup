"""M0 任务队列测试：enqueue/claim/complete/fail + 租约 45min 回收 + 幂等 + 错误码退避 + 失败隔离。

对齐 `_management/modules/m0-foundation/database/README.md` 与 09 文档第二节语义。
运行：python -m pytest tests -q --basetemp=".pytest-tmp"（P-001）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from foundation.config import FoundationConfig
from foundation.db import Database
from foundation.repo import WorkflowQueue
from foundation.tables import WorkflowJob

TOLERANCE_SECONDS = 10


@pytest.fixture()
def queue() -> WorkflowQueue:
    """SQLite 内存库（StaticPool 单连接）上的队列。"""
    cfg = FoundationConfig(db_url="sqlite:///:memory:", lease_minutes=45, data_dir=Path("."))
    database = Database(cfg)
    database.create_all()
    database.seed()
    return WorkflowQueue(database)


def _approx_after(now: datetime, seconds: int) -> datetime:
    return now + timedelta(seconds=seconds)


def test_enqueue_creates_job(queue: WorkflowQueue) -> None:
    """入队创建 pending job，字段正确落库。"""
    job = queue.enqueue(product_id=1, stage="alibaba_quote", payload={"sku": "A1"})
    assert job.id is not None
    assert job.status == "pending"
    assert job.stage == "alibaba_quote"
    assert job.payload == {"sku": "A1"}
    assert job.generation_version == "v1"


def test_enqueue_idempotent_same_key(queue: WorkflowQueue) -> None:
    """幂等：同 (product_id, stage, generation_version) 重复入队返回同一 job，不新增。"""
    first = queue.enqueue(product_id=1, stage="image_generation")
    second = queue.enqueue(product_id=1, stage="image_generation")
    assert first.id == second.id
    assert len(queue.list_jobs()) == 1


def test_enqueue_different_generation_new_job(queue: WorkflowQueue) -> None:
    """generation_version 不同视为不同 job（幂等键含版本）。"""
    a = queue.enqueue(product_id=1, stage="listing_upload", generation_version="v1")
    b = queue.enqueue(product_id=1, stage="listing_upload", generation_version="v2")
    assert a.id != b.id
    assert len(queue.list_jobs()) == 2


def test_claim_acquires_lease(queue: WorkflowQueue) -> None:
    """claim 写租约：status=running、lease_owner、lease_expires_at≈now+45min。"""
    now = datetime.now(timezone.utc)
    job = queue.enqueue(product_id=1, stage="source_collect")
    claimed = queue.claim(worker_id="worker-1")
    assert len(claimed) == 1
    c = claimed[0]
    assert c.id == job.id
    assert c.status == "running"
    assert c.lease_owner == "worker-1"
    assert c.lease_expires_at is not None
    assert abs((c.lease_expires_at - _approx_after(now, 45 * 60)).total_seconds()) <= TOLERANCE_SECONDS


def test_claim_mutual_exclusion(queue: WorkflowQueue) -> None:
    """租约互斥：job 已被 worker-1 领取，worker-2 无法再领取。"""
    queue.enqueue(product_id=1, stage="source_collect")
    queue.claim(worker_id="worker-1")
    assert queue.claim(worker_id="worker-2") == []


def test_claim_expired_lease_reclaimed_directly(queue: WorkflowQueue) -> None:
    """running 但租约过期的 job 可被新 worker 直接领取（进程崩溃恢复）。"""
    job = queue.enqueue(product_id=1, stage="source_collect")
    queue.claim(worker_id="worker-1")
    # 手动把租约改过期
    with queue.database.session() as session:
        db_job = session.get(WorkflowJob, job.id)
        db_job.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    claimed = queue.claim(worker_id="worker-2")
    assert len(claimed) == 1
    assert claimed[0].id == job.id
    assert claimed[0].lease_owner == "worker-2"


def test_recover_expired_leases(queue: WorkflowQueue) -> None:
    """recover_expired_leases：过期 running job 重置 pending 并清租约。"""
    job = queue.enqueue(product_id=1, stage="source_collect")
    queue.claim(worker_id="worker-1")
    with queue.database.session() as session:
        db_job = session.get(WorkflowJob, job.id)
        db_job.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    recovered = queue.recover_expired_leases()
    assert recovered == 1
    job = queue.get(job.id)
    assert job.status == "pending"
    assert job.lease_owner is None
    assert job.lease_expires_at is None


def test_claim_respects_retry_after(queue: WorkflowQueue) -> None:
    """retry_after 未到点不可 claim，到点后可 claim。"""
    job = queue.enqueue(product_id=1, stage="source_collect")
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    with queue.database.session() as session:
        db_job = session.get(WorkflowJob, job.id)
        db_job.retry_after = future
    assert queue.claim(worker_id="worker-1") == []
    with queue.database.session() as session:
        db_job = session.get(WorkflowJob, job.id)
        db_job.retry_after = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert len(queue.claim(worker_id="worker-1")) == 1


def test_claim_stages_filter(queue: WorkflowQueue) -> None:
    """claim 支持按 stage 过滤。"""
    queue.enqueue(product_id=1, stage="alibaba_quote")
    queue.enqueue(product_id=2, stage="image_generation")
    claimed = queue.claim(worker_id="worker-1", stages=["alibaba_quote"], limit=10)
    assert len(claimed) == 1
    assert claimed[0].stage == "alibaba_quote"


def test_complete_success_writes_evidence(queue: WorkflowQueue) -> None:
    """complete：status=success，evidence 写入 evidence_json，租约清空。"""
    job = queue.enqueue(product_id=1, stage="source_collect")
    queue.claim(worker_id="worker-1")
    ok = queue.complete(job_id=job.id, worker_id="worker-1", evidence={"spu_id": "s_1", "price_fen": 1990})
    assert ok is True
    done = queue.get(job.id)
    assert done.status == "success"
    assert done.evidence_json == {"spu_id": "s_1", "price_fen": 1990}
    assert done.lease_owner is None
    assert done.lease_expires_at is None


def test_complete_wrong_worker_rejected(queue: WorkflowQueue) -> None:
    """complete 租约归属校验：非持有者被拒绝，状态不变。"""
    job = queue.enqueue(product_id=1, stage="source_collect")
    queue.claim(worker_id="worker-1")
    assert queue.complete(job_id=job.id, worker_id="worker-2") is False
    assert queue.get(job.id).status == "running"


def test_complete_non_running_rejected(queue: WorkflowQueue) -> None:
    """状态机安全：非 running job 调 complete 返回 False。"""
    job = queue.enqueue(product_id=1, stage="source_collect")  # pending
    assert queue.complete(job_id=job.id, worker_id="worker-1") is False


def test_fail_rate_limit_sets_backoff(queue: WorkflowQueue) -> None:
    """RATE_LIMIT：status=pending、retry_count+1、retry_after≈now+180s。"""
    now = datetime.now(timezone.utc)
    job = queue.enqueue(product_id=1, stage="source_collect")
    queue.claim(worker_id="worker-1")
    assert queue.fail(job_id=job.id, worker_id="worker-1", error_code="RATE_LIMIT", error_message="too frequent") is True
    failed = queue.get(job.id)
    assert failed.status == "pending"
    assert failed.error_code == "RATE_LIMIT"
    assert failed.error_message == "too frequent"
    assert failed.retry_count == 1
    assert abs((failed.retry_after - _approx_after(now, 180)).total_seconds()) <= TOLERANCE_SECONDS
    # 未到 retry_after 不可被再次领取
    assert queue.claim(worker_id="worker-2") == []


def test_fail_verification_manual_takeover(queue: WorkflowQueue) -> None:
    """VERIFICATION_REQUIRED：waiting_verification，不重试（retry_after=None），断点保留。"""
    job = queue.enqueue(product_id=1, stage="listing_upload", payload={"step": 3})
    queue.claim(worker_id="worker-1")
    assert queue.fail(job_id=job.id, worker_id="worker-1", error_code="VERIFICATION_REQUIRED") is True
    paused = queue.get(job.id)
    assert paused.status == "waiting_verification"
    assert paused.retry_after is None
    assert paused.payload == {"step": 3}  # 断点保留


def test_fail_auth_manual_takeover(queue: WorkflowQueue) -> None:
    """AUTH_REQUIRED：waiting_login。"""
    job = queue.enqueue(product_id=1, stage="source_collect")
    queue.claim(worker_id="worker-1")
    queue.fail(job_id=job.id, worker_id="worker-1", error_code="AUTH_REQUIRED")
    assert queue.get(job.id).status == "waiting_login"


def test_fail_platform_reject_blocked(queue: WorkflowQueue) -> None:
    """PLATFORM_REJECT：blocked，永久阻塞。"""
    job = queue.enqueue(product_id=1, stage="listing_upload")
    queue.claim(worker_id="worker-1")
    queue.fail(job_id=job.id, worker_id="worker-1", error_code="PLATFORM_REJECT", error_message="资质缺失")
    blocked = queue.get(job.id)
    assert blocked.status == "blocked"
    assert blocked.error_message == "资质缺失"
    assert queue.claim(worker_id="worker-2") == []


def test_fail_unknown_code_falls_back_unexpected(queue: WorkflowQueue) -> None:
    """未知错误码按 UNEXPECTED 兜底：pending、retry_count+1、retry_after≈now+60s。"""
    now = datetime.now(timezone.utc)
    job = queue.enqueue(product_id=1, stage="source_collect")
    queue.claim(worker_id="worker-1")
    queue.fail(job_id=job.id, worker_id="worker-1", error_code="SOME_NEW_ERROR")
    failed = queue.get(job.id)
    assert failed.error_code == "UNEXPECTED"
    assert failed.status == "pending"
    assert failed.retry_count == 1
    assert abs((failed.retry_after - _approx_after(now, 60)).total_seconds()) <= TOLERANCE_SECONDS


def test_fail_wrong_worker_rejected(queue: WorkflowQueue) -> None:
    """fail 租约归属校验：非持有者被拒绝。"""
    job = queue.enqueue(product_id=1, stage="source_collect")
    queue.claim(worker_id="worker-1")
    assert queue.fail(job_id=job.id, worker_id="worker-2", error_code="TIMEOUT") is False
    assert queue.get(job.id).status == "running"


def test_failure_isolation(queue: WorkflowQueue) -> None:
    """失败隔离：一个 job 进入 waiting_verification，其他 pending job 仍可被领取。"""
    j1 = queue.enqueue(product_id=1, stage="source_collect")
    queue.enqueue(product_id=2, stage="source_collect")
    queue.claim(worker_id="worker-1", limit=10)
    queue.fail(job_id=j1.id, worker_id="worker-1", error_code="VERIFICATION_REQUIRED")
    claimed = queue.claim(worker_id="worker-2", limit=10)
    assert len(claimed) == 1
    assert claimed[0].product_id == 2  # 只有未阻塞的 job 被领取


def test_list_jobs_filters(queue: WorkflowQueue) -> None:
    """list_jobs 支持 status/stage 过滤。"""
    queue.enqueue(product_id=1, stage="source_collect")
    queue.enqueue(product_id=2, stage="alibaba_quote")
    assert len(queue.list_jobs(stage="source_collect")) == 1
    assert len(queue.list_jobs(status="pending")) == 2
    assert len(queue.list_jobs(stage="alibaba_quote", status="pending")) == 1
