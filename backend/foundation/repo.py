"""M0 任务队列（WorkflowQueue）。

语义对齐 `_management/modules/m0-foundation/database/README.md`（五表最终 DDL v0.2）与 09 文档第二节：
- enqueue：幂等——(product_id, stage, generation_version) 唯一约束，重复入队返回已有 job；
- claim：领取可执行 job（pending 且到点 / running 但租约过期回收），写租约 45min；失败隔离
  （waiting_verification/waiting_login/blocked/success/failed 绝不被领取，不阻塞其他 job）；
- complete/fail：租约归属校验；fail 按 error_codes 表策略分流
  （retry → pending+退避 / manual_takeover → waiting_* / block_forever → blocked）；
- recover_expired_leases：进程重启自愈（09 文档 resume_on_startup）。

字段命名对齐 DDL：重试时间 `retry_after`、结果证据 `evidence_json`。
数据口径（REC-005 / DA-001）：时间一律 UTC；payload/evidence_json JSON 内金额一律「分」int。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, or_, select

from .db import Database
from .tables import ErrorCode, WorkflowJob

# 人工接管类错误码 → 任务状态映射（10 文档：验证码/登录人工处理，单任务暂停不阻塞队列）
_MANUAL_STATUS: dict[str, str] = {
    "VERIFICATION_REQUIRED": "waiting_verification",
    "AUTH_REQUIRED": "waiting_login",
}

# 未知错误码兜底策略（60s 退避重试，留证据）
_UNKNOWN_CODE_FALLBACK = "UNEXPECTED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowQueue:
    """基于共享表 workflow_jobs 的持久化任务队列。"""

    def __init__(self, database: Database):
        self.database = database

    # ---------------------------------------------------------------- 入队
    def enqueue(
        self,
        product_id: int,
        stage: str,
        payload: dict | None = None,
        generation_version: str = "v1",
    ) -> WorkflowJob:
        """幂等入队：同 (product_id, stage, generation_version) 已存在则返回已有 job 不新增。"""
        with self.database.session() as session:
            existing = session.scalar(
                select(WorkflowJob).where(
                    WorkflowJob.product_id == product_id,
                    WorkflowJob.stage == stage,
                    WorkflowJob.generation_version == generation_version,
                )
            )
            if existing is not None:
                session.expunge(existing)
                return existing
            job = WorkflowJob(
                product_id=product_id,
                stage=stage,
                generation_version=generation_version,
                payload=payload or {},
            )
            session.add(job)
            session.flush()
            session.expunge(job)
            return job

    # ---------------------------------------------------------------- 领取
    def claim(self, worker_id: str, stages: list[str] | None = None, limit: int = 1) -> list[WorkflowJob]:
        """领取可执行 job 并写租约（lease_minutes，默认 45min）。

        可选领取条件（SQL 内过滤，避免占名额）：
        - pending 且 (retry_after 为空或已到点)；
        - running 但租约已过期（进程崩溃回收，09 文档 recover_after_process_restart）。
        失败隔离：waiting_verification/waiting_login/blocked/success/failed 不会被领取。
        """
        now = _utcnow()
        claimable = or_(
            and_(
                WorkflowJob.status == "pending",
                or_(
                    WorkflowJob.retry_after.is_(None),
                    WorkflowJob.retry_after <= now,
                ),
            ),
            and_(
                WorkflowJob.status == "running",
                WorkflowJob.lease_expires_at.is_not(None),
                WorkflowJob.lease_expires_at < now,
            ),
        )
        with self.database.session() as session:
            stmt = (
                select(WorkflowJob)
                .where(claimable)
                .order_by(WorkflowJob.id)
                .limit(limit)
            )
            if stages:
                stmt = stmt.where(WorkflowJob.stage.in_(stages))
            jobs = list(session.scalars(stmt).all())
            claimed: list[WorkflowJob] = []
            for job in jobs:
                job.status = "running"
                job.lease_owner = worker_id
                job.lease_expires_at = now + timedelta(minutes=self.database.config.lease_minutes)
                claimed.append(job)
            session.flush()
            for job in claimed:
                session.expunge(job)
            return claimed

    # ---------------------------------------------------------------- 完成
    def complete(self, job_id: int, worker_id: str, evidence: dict | None = None) -> bool:
        """标记成功：仅当 job 为 running 且租约归属 worker_id（非持有者拒绝）。

        evidence 为结果证据，写入 evidence_json（09/02 文档留痕）。
        """
        with self.database.session() as session:
            job = session.get(WorkflowJob, job_id)
            if job is None or job.status != "running" or job.lease_owner != worker_id:
                return False
            job.status = "success"
            job.evidence_json = evidence or {}
            job.lease_owner = None
            job.lease_expires_at = None
            return True

    # ---------------------------------------------------------------- 失败
    def fail(
        self,
        job_id: int,
        worker_id: str,
        error_code: str,
        error_message: str = "",
    ) -> bool:
        """按 error_codes 表策略分流失败任务（租约归属校验，非持有者拒绝）。

        - retry（retryable=1）：status=pending，retry_count+1，retry_after=now+backoff_seconds；
        - manual_takeover：VERIFICATION_REQUIRED→waiting_verification、AUTH_REQUIRED→waiting_login，
          保留断点 payload，不自动重试；
        - block_forever：status=blocked，记录原因转人工/修复候选；
        - 未知错误码按 UNEXPECTED 兜底（60s 退避重试，留证据）。
        """
        with self.database.session() as session:
            job = session.get(WorkflowJob, job_id)
            if job is None or job.status != "running" or job.lease_owner != worker_id:
                return False
            spec = session.get(ErrorCode, error_code)
            if spec is None:  # 未知错误码按 UNEXPECTED 兜底（60s 退避重试，留证据）
                spec = session.get(ErrorCode, _UNKNOWN_CODE_FALLBACK)
                error_code = _UNKNOWN_CODE_FALLBACK
            job.error_code = error_code
            job.error_message = error_message
            if spec is not None and spec.action == "manual_takeover":
                # 人工接管：单任务暂停，保留断点 payload，不重试
                job.status = _MANUAL_STATUS.get(error_code, "blocked")
                job.retry_after = None
            elif spec is not None and spec.action == "block_forever":
                # 平台驳回等：永久阻塞，记录原因转人工/修复候选
                job.status = "blocked"
                job.retry_after = None
            else:
                # retry：回 pending + 按码表退避秒数计算下次可重试时间
                job.status = "pending"
                job.retry_count += 1
                backoff = spec.backoff_seconds if spec is not None else 60
                job.retry_after = _utcnow() + timedelta(seconds=backoff)
            job.lease_owner = None
            job.lease_expires_at = None
            return True

    # ---------------------------------------------------------------- 恢复
    def recover_expired_leases(self) -> int:
        """租约过期的 running job 重置为 pending 并清租约（进程重启自愈），返回回收数。"""
        now = _utcnow()
        with self.database.session() as session:
            jobs = list(
                session.scalars(
                    select(WorkflowJob).where(
                        WorkflowJob.status == "running",
                        WorkflowJob.lease_expires_at.is_not(None),
                        WorkflowJob.lease_expires_at < now,
                    )
                ).all()
            )
            for job in jobs:
                job.status = "pending"
                job.lease_owner = None
                job.lease_expires_at = None
            return len(jobs)

    # ---------------------------------------------------------------- 查询
    def get(self, job_id: int) -> Optional[WorkflowJob]:
        with self.database.session() as session:
            job = session.get(WorkflowJob, job_id)
            if job is not None:
                session.expunge(job)
            return job

    def list_jobs(
        self,
        status: str | None = None,
        stage: str | None = None,
        limit: int = 100,
    ) -> list[WorkflowJob]:
        with self.database.session() as session:
            stmt = select(WorkflowJob).order_by(WorkflowJob.id.desc()).limit(limit)
            if status:
                stmt = stmt.where(WorkflowJob.status == status)
            if stage:
                stmt = stmt.where(WorkflowJob.stage == stage)
            jobs = list(session.scalars(stmt).all())
            for job in jobs:
                session.expunge(job)
            return jobs
