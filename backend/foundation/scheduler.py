"""M0 调度器进程化（WorkflowScheduler）。

对齐 09 文档第三节与 02 文档「调度与容错」亮点：
- 断点自愈：`resume_on_startup()` 恢复崩溃进程遗留的 running job 租约（45min 过期回收），
  重启即恢复（09 文档 recover_after_process_restart / resume_on_startup）；
- 节流 0~4 级：stage 连续失败 → throttle_level 提升，暂停该 stage 至 base×2^level 后（×1/2/4/8/16）；
- 熔断：连续失败 ≥2 → 暂停整 stage（risk_control 语义，09 文档第二节），冷却后自动恢复；
- 进程化：独立进程运行 `python -m foundation scheduler --loop`（systemd/后台托管），
  重启自愈（resume_on_startup 幂等）；
- 失败隔离：单 job 失败/等待人工不阻塞其他 stage/job 排队（复用 WorkflowQueue.claim）。

职责边界：M0 调度器 = 通用队列驱动（轮询领取 → 分派 Worker → 回写 complete/fail + 节流熔断）。
业务执行由注入的 `Worker` 实现（各模块提供；CLI 默认 LoggingWorker 仅留痕演示）。
选品源级账本/降频（实时榜空转降日轮询）属业务调度（sourcing），M0 通用调度器不实现。

数据口径（REC-005）：时间一律 UTC；evidence 内金额按「分」int。
"""

from __future__ import annotations

import logging
import os
import socket
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from threading import Event
from typing import Optional

from .config import SchedulerConfig
from .repo import WorkflowQueue
from .tables import STAGE_VALUES, WorkflowJob

logger = logging.getLogger("foundation.scheduler")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Worker(ABC):
    """任务执行器抽象：各业务模块实现 execute(job)，返回结构化结果。

    返回 dict：{"ok": bool, "error_code": str|None, "evidence": dict|None}
    - ok=True：调度器 complete(job, evidence)
    - ok=False：error_code 必填（09 码表），调度器 fail(job, error_code)，
      由 error_codes 表决定重试/人工接管/阻塞。
    """

    @abstractmethod
    def execute(self, job: WorkflowJob) -> dict:
        """执行一个 job。实现必须捕获自身异常并结构化返回（不抛出）。"""
        raise NotImplementedError


class LoggingWorker(Worker):
    """CLI 默认 worker：仅打印 job 信息并视为成功（演示/占位，不执行业务）。"""

    def execute(self, job: WorkflowJob) -> dict:
        logger.info("job id=%s stage=%s product_id=%s status=%s", job.id, job.stage, job.product_id, job.status)
        return {"ok": True, "error_code": None, "evidence": {"worker": "logging"}}

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return "<LoggingWorker>"


def default_worker_id() -> str:
    """进程级 worker 标识：hostname-pid（重启即新 id，租约回收语义正确）。"""
    return f"{socket.gethostname()}-{os.getpid()}"


class WorkflowScheduler:
    """通用队列调度器：轮询领取 → 分派 Worker → 回写 + 节流/熔断/断点自愈。"""

    def __init__(
        self,
        queue: WorkflowQueue,
        worker: Worker,
        config: Optional[SchedulerConfig] = None,
        worker_id: Optional[str] = None,
    ):
        self.queue = queue
        self.worker = worker
        self.config = config or SchedulerConfig()
        self.worker_id = worker_id or default_worker_id()
        # stage 级节流/熔断状态（进程内存态；重启后重置，09 文档 risk_control 探针恢复语义）
        self._stage_failures: dict[str, int] = {}                  # stage -> 连续失败次数
        self._stage_throttle_level: dict[str, int] = {}            # stage -> 0~4
        self._stage_paused_until: dict[str, datetime] = {}         # stage -> 暂停到何时

    # ------------------------------------------------------------ 断点自愈
    def resume_on_startup(self) -> int:
        """进程重启自愈：恢复租约过期的 running job 为 pending（幂等），返回恢复数。"""
        return self.queue.recover_expired_leases()

    # ------------------------------------------------------------ 节流/熔断
    def _stage_paused(self, stage: str, now: datetime) -> bool:
        until = self._stage_paused_until.get(stage)
        return until is not None and until > now

    def _active_stages(self, now: datetime) -> list[str]:
        """返回未暂停的 stage 列表（全暂停时返回空 → 本轮不领取）。"""
        return [s for s in STAGE_VALUES if not self._stage_paused(s, now)]

    def _record_success(self, stage: str) -> None:
        self._stage_failures[stage] = 0
        self._stage_throttle_level[stage] = 0
        self._stage_paused_until.pop(stage, None)

    def _record_failure(self, stage: str) -> bool:
        """记录 stage 失败；连续失败达阈值 → 提升节流级并熔断暂停，返回是否熔断。"""
        failures = self._stage_failures.get(stage, 0) + 1
        self._stage_failures[stage] = failures
        if failures >= self.config.circuit_breaker_failures:
            level = min(self._stage_throttle_level.get(stage, 0) + 1, self.config.throttle_levels - 1)
            self._stage_throttle_level[stage] = level
            backoff = self.config.throttle_base_seconds * (2 ** level)
            self._stage_paused_until[stage] = _utcnow() + timedelta(seconds=backoff)
            logger.warning(
                "stage=%s 连续失败 %d 次 → 熔断暂停 %s 秒（throttle_level=%d）",
                stage, failures, backoff, level,
            )
            return True
        return False

    def _reset_stage_stats(self) -> None:
        self._stage_failures.clear()
        self._stage_throttle_level.clear()
        self._stage_paused_until.clear()

    # ------------------------------------------------------------ 单轮
    def run_once(self) -> dict:
        """执行一轮：断点自愈 → 领取到期 job（跳过熔断 stage）→ 分派 worker → 回写。

        返回统计：{"recovered", "claimed", "succeeded", "failed", "paused_stages"}。
        """
        stats = {"recovered": 0, "claimed": 0, "succeeded": 0, "failed": 0, "paused_stages": []}
        stats["recovered"] = self.resume_on_startup()
        now = _utcnow()
        active_stages = self._active_stages(now)
        stats["paused_stages"] = [s for s in STAGE_VALUES if s not in active_stages]
        if not active_stages:
            logger.info("全部 stage 处于熔断暂停，本轮跳过（%s）", stats["paused_stages"])
            return stats
        jobs = self.queue.claim(
            worker_id=self.worker_id,
            stages=active_stages,
            limit=self.config.max_claim_per_round,
        )
        stats["claimed"] = len(jobs)
        for job in jobs:
            result = self.worker.execute(job)  # Worker 契约：不抛出
            if result.get("ok"):
                self.queue.complete(job_id=job.id, worker_id=self.worker_id, evidence=result.get("evidence"))
                self._record_success(job.stage)
                stats["succeeded"] += 1
            else:
                error_code = result.get("error_code") or "UNEXPECTED"
                self.queue.fail(
                    job_id=job.id,
                    worker_id=self.worker_id,
                    error_code=error_code,
                    error_message=str(result.get("evidence") or result.get("error_message") or ""),
                )
                self._record_failure(job.stage)
                stats["failed"] += 1
        return stats

    # ------------------------------------------------------------ 常驻循环
    def run_forever(self, interval: Optional[float] = None, stop_event: Optional[Event] = None) -> None:
        """常驻轮询：周期执行 run_once，支持优雅退出（KeyboardInterrupt / stop_event）。

        生产建议由 systemd/后台托管拉起（09 文档：调度器独立进程，重启自愈）。
        """
        interval = interval if interval is not None else self.config.poll_interval_seconds
        stop = stop_event if stop_event is not None else Event()
        logger.info("scheduler 启动 worker_id=%s interval=%ss", self.worker_id, interval)
        try:
            while not stop.is_set():
                stats = self.run_once()
                logger.info("run_once 完成 %s", stats)
                # 可中断等待：stop_event 短等（可测性）；否则正常 sleep
                waited = 0.0
                while waited < interval and not stop.is_set():
                    stop.wait(min(0.5, interval - waited))
                    waited += 0.5
        except KeyboardInterrupt:
            logger.info("scheduler 收到中断，优雅退出")
        finally:
            logger.info("scheduler 退出")


__all__ = ["Worker", "LoggingWorker", "WorkflowScheduler", "default_worker_id"]
