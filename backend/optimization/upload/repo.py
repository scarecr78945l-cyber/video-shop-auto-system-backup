"""M3 上传素材库 upload · opt_upload_records 落库（v1.0 集成任务 3 · 子代理-F）。

公共骨架 repo.py 只读使用；本模块新增 UploadRepo 负责上传成功/失败/待人工
记录的写入（REC-002 双轨 UploadService 的统一留痕），对齐 tables.OptUploadRecord
字段口径（batch_no ≤ config.upload.batch_size、status、error_code、
platform_material_id、evidence_json）。

只操作本模块 m3-optimization.db 的 opt_upload_records 表；每行一个事务
（session 上下文提交），天然支持「单条失败不阻塞整批」的失败隔离。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import func, select

from .. import tables
from ..repo import new_id

if TYPE_CHECKING:  # 仅类型标注，避免循环 import
    from .service import UploadResult


class UploadRepo:
    """opt_upload_records 仓储：record（写入）/ list_recent / count。"""

    def __init__(self, db):
        self.db = db

    def record(
        self,
        *,
        target_type: str,
        target_id: str,
        result: "UploadResult",
        batch_no: int = 1,
        mode: str = "api",
        upload_id: Optional[str] = None,
    ) -> str:
        """写入一条上传记录（成功/失败/待人工统一走此入口）。"""
        upload_id = upload_id or new_id("up")
        with self.db.session() as s:
            s.add(tables.OptUploadRecord(
                upload_id=upload_id,
                target_type=target_type,
                target_id=target_id,
                batch_no=int(batch_no),
                mode=mode,
                status=result.status,
                error_code=result.error_code,
                platform_material_id=result.platform_material_id,
                platform_evaluation=result.platform_evaluation,
                evidence_json=result.evidence,
            ))
        return upload_id

    def list_recent(
        self, limit: int = 50, mode: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """最近记录（created_at 倒序），mode 可过滤（api/ui/semi）。"""
        with self.db.session() as s:
            stmt = select(tables.OptUploadRecord).order_by(
                tables.OptUploadRecord.created_at.desc()
            )
            if mode:
                stmt = stmt.where(tables.OptUploadRecord.mode == mode)
            rows = s.execute(stmt.limit(int(limit))).scalars().all()
            return [self._to_dict(r) for r in rows]

    def count(self, mode: Optional[str] = None) -> int:
        with self.db.session() as s:
            stmt = select(func.count()).select_from(tables.OptUploadRecord)
            if mode:
                stmt = stmt.where(tables.OptUploadRecord.mode == mode)
            return int(s.execute(stmt).scalar_one())

    @staticmethod
    def _to_dict(r: Any) -> dict[str, Any]:
        return {
            "upload_id": r.upload_id,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "batch_no": r.batch_no,
            "mode": r.mode,
            "status": r.status,
            "error_code": r.error_code,
            "platform_material_id": r.platform_material_id,
            "platform_evaluation": r.platform_evaluation,
            "evidence_json": r.evidence_json or {},
        }
