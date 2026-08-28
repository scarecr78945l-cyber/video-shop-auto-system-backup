"""M4 上架任务仓储：listing_* 表读写 + 租约断点续跑 + 证据留痕。

- create_task 依赖 UNIQUE(product_id, stage, generation_version) 幂等防重复入队；
- claim_task 只领取非终态且租约过期/为空的合格任务（45min 过期回收，断点续跑）；
- append_op_log 写 listing_op_logs 证据（payload_digest 为脱敏摘要，不存敏感值）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from .db import ListingDatabase
from .models import ListingOpLog, ListingTask, utcnow_iso
from .tables import ListingOpLogRow, ListingQuotaStateRow, ListingTaskRow

# 可被 worker 自动领取的非终态（断点续跑）：rejected/manual 需人工/拒审决策，不自动领取
CLAIMABLE_STATUSES = (
    "pending",
    "creating",
    "draft",
    "platform_auditing",
    "retry_candidate",
)


class DuplicateTaskError(Exception):
    """重复入队：同 (product_id, stage, generation_version) 已存在（幂等防重复）。"""

    def __init__(self, task_id: str, product_id: int, stage: str, generation_version: str):
        self.task_id = task_id
        self.product_id = product_id
        self.stage = stage
        self.generation_version = generation_version
        super().__init__(
            f"重复上架任务: task_id={task_id} 已存在 (product_id={product_id}, "
            f"stage={stage}, generation_version={generation_version})"
        )


class TaskNotFoundError(Exception):
    """任务不存在。"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"上架任务不存在: task_id={task_id}")


class ListingRepo:
    """listing_* 表仓储（函数式方法，全部走本模块库）。"""

    def __init__(self, database: ListingDatabase):
        self.database = database

    # ------------------------------------------------------------ 任务 CRUD

    def create_task(self, task: ListingTask) -> ListingTask:
        """INSERT；重复 (product_id, stage, generation_version) 抛 DuplicateTaskError。"""
        try:
            with self.database.session() as session:
                session.add(self._to_row(task))
        except IntegrityError as exc:
            raise DuplicateTaskError(
                task.task_id, task.product_id, task.stage, task.generation_version
            ) from exc
        return task

    def get_task(self, task_id: str) -> Optional[ListingTask]:
        with self.database.session() as session:
            row = session.get(ListingTaskRow, task_id)
            return self._to_model(row) if row is not None else None

    def get_task_by_product(
        self, product_id: int, generation_version: str
    ) -> Optional[ListingTask]:
        with self.database.session() as session:
            row = (
                session.execute(
                    select(ListingTaskRow)
                    .where(
                        ListingTaskRow.product_id == product_id,
                        ListingTaskRow.generation_version == generation_version,
                    )
                    .order_by(ListingTaskRow.created_at.desc())
                )
                .scalars()
                .first()
            )
            return self._to_model(row) if row is not None else None

    def update_status(self, task_id: str, status: str, **fields: Any) -> ListingTask:
        """UPDATE status + updated_at + 可选附加字段；返回更新后的任务。"""
        values: dict[str, Any] = {"status": status, "updated_at": utcnow_iso()}
        values.update(fields)
        with self.database.session() as session:
            result = session.execute(
                update(ListingTaskRow)
                .where(ListingTaskRow.task_id == task_id)
                .values(**values)
            )
            if result.rowcount == 0:
                raise TaskNotFoundError(task_id)
            row = session.get(ListingTaskRow, task_id)
            assert row is not None
            return self._to_model(row)

    # ------------------------------------------------------------ 租约（断点续跑）

    def claim_task(
        self, worker_id: str, task_id: Optional[str] = None
    ) -> Optional[ListingTask]:
        """租约领取：非终态且（租约空/已过期）→ 置 lease_owner + now+45min 到期。

        task_id 为空时领取最早创建的合格任务（队列语义）；无合格任务返回 None。
        """
        now_iso = utcnow_iso()
        expires_iso = (
            datetime.now(timezone.utc)
            + timedelta(minutes=self.database.config.lease_minutes)
        ).isoformat()
        with self.database.session() as session:
            stmt = (
                select(ListingTaskRow)
                .where(
                    ListingTaskRow.status.in_(CLAIMABLE_STATUSES),
                    or_(
                        ListingTaskRow.lease_expires_at.is_(None),
                        ListingTaskRow.lease_expires_at < now_iso,  # ISO8601 同格式文本字典序=时间序
                    ),
                )
                .order_by(ListingTaskRow.created_at.asc())
            )
            if task_id is not None:
                stmt = stmt.where(ListingTaskRow.task_id == task_id)
            row = session.execute(stmt).scalars().first()
            if row is None:
                return None
            row.lease_owner = worker_id
            row.lease_expires_at = expires_iso
            row.updated_at = now_iso
            return self._to_model(row)

    def release_task(self, task_id: str) -> None:
        """清空租约（worker 正常结束/放弃）。"""
        with self.database.session() as session:
            session.execute(
                update(ListingTaskRow)
                .where(ListingTaskRow.task_id == task_id)
                .values(lease_owner=None, lease_expires_at=None, updated_at=utcnow_iso())
            )

    # ------------------------------------------------------------ 证据留痕

    def append_op_log(
        self,
        task_id: str,
        api: str,
        direction: str,
        payload_digest: Optional[str] = None,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        platform_code: Optional[str] = None,
        evidence_json: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> int:
        """写 listing_op_logs 一条（证据留痕）：payload_digest 为脱敏摘要，不存敏感值。

        返回新 log_id。
        """
        if request_id is None:
            request_id = f"{task_id}:{api}:{direction}:{uuid.uuid4().hex[:12]}"
        with self.database.session() as session:
            row = ListingOpLogRow(
                task_id=task_id,
                request_id=request_id,
                api=api,
                direction=direction,
                payload_digest=payload_digest,
                status_code=status_code,
                error_code=error_code,
                platform_code=platform_code,
                evidence_json=evidence_json,
                created_at=utcnow_iso(),
            )
            session.add(row)
            session.flush()
            return row.log_id

    def list_op_logs(
        self, task_id: Optional[str] = None, limit: int = 200
    ) -> list[ListingOpLog]:
        """回查操作日志（按 log_id 升序；可只查单任务）。"""
        with self.database.session() as session:
            stmt = select(ListingOpLogRow).order_by(ListingOpLogRow.log_id.asc())
            if task_id is not None:
                stmt = stmt.where(ListingOpLogRow.task_id == task_id)
            stmt = stmt.limit(limit)
            rows = session.execute(stmt).scalars().all()
            return [
                ListingOpLog(
                    log_id=r.log_id,
                    task_id=r.task_id,
                    request_id=r.request_id,
                    api=r.api,
                    direction=r.direction,
                    payload_digest=r.payload_digest,
                    status_code=r.status_code,
                    error_code=r.error_code,
                    platform_code=r.platform_code,
                    evidence_json=r.evidence_json,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    # ------------------------------------------------------------ 配额状态

    def upsert_quota_state(
        self,
        api: str,
        tokens: float,
        capacity: float,
        refill_rate: float,
        window_start: str,
        consecutive_failures: int = 0,
        circuit_open_until: Optional[str] = None,
    ) -> None:
        """令牌桶状态 upsert（SQLite ON CONFLICT(api) DO UPDATE）。"""
        values: dict[str, Any] = {
            "api": api,
            "tokens": tokens,
            "capacity": capacity,
            "refill_rate": refill_rate,
            "window_start": window_start,
            "consecutive_failures": consecutive_failures,
            "circuit_open_until": circuit_open_until,
        }
        stmt = sqlite_insert(ListingQuotaStateRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ListingQuotaStateRow.api],
            set_={k: v for k, v in values.items() if k != "api"},
        )
        with self.database.session() as session:
            session.execute(stmt)

    # ------------------------------------------------------------ 行/模型转换

    @staticmethod
    def _to_row(task: ListingTask) -> ListingTaskRow:
        return ListingTaskRow(
            task_id=task.task_id,
            product_id=task.product_id,
            generation_version=task.generation_version,
            stage=task.stage,
            status=task.status,
            gate_result=(
                json.dumps(task.gate_result, ensure_ascii=False)
                if task.gate_result is not None
                else None
            ),
            platform_spu_id=task.platform_spu_id,
            product_link=task.product_link,
            link_verified_at=task.link_verified_at,
            reject_reason_code=task.reject_reason_code,
            attempts=task.attempts,
            lease_owner=task.lease_owner,
            lease_expires_at=task.lease_expires_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @staticmethod
    def _to_model(row: ListingTaskRow) -> ListingTask:
        return ListingTask(
            task_id=row.task_id,
            product_id=row.product_id,
            generation_version=row.generation_version,
            stage=row.stage,
            status=row.status,
            gate_result=(
                json.loads(row.gate_result) if row.gate_result else None
            ),
            platform_spu_id=row.platform_spu_id,
            product_link=row.product_link,
            link_verified_at=row.link_verified_at,
            reject_reason_code=row.reject_reason_code,
            attempts=row.attempts,
            lease_owner=row.lease_owner,
            lease_expires_at=row.lease_expires_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
