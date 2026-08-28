"""M3 自动素材优化模块 · 共享数据访问（公共骨架，子代理只使用不修改）。

统一经 Database.session 操作本模块库 opt_* 表；跨模块数据（M1 products /
M2 assets / M5 回写）只读引用，不在此建库。
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select

from . import tables
from .db import Database
from .models import CopywriteDraft, EvaluationSnapshot


def new_id(prefix: str = "opt") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------- 文案 ----------

class CopywriteRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, draft: CopywriteDraft) -> str:
        """幂等写入：同 (product_id, copy_type, variant_no) 覆盖更新。"""
        copywrite_id = new_id("cw")
        with self.db.session() as s:
            row = s.execute(
                select(tables.OptCopywrite).where(
                    tables.OptCopywrite.product_id == draft.product_id,
                    tables.OptCopywrite.copy_type == draft.copy_type,
                    tables.OptCopywrite.variant_no == draft.variant_no,
                )
            ).scalar_one_or_none()
            if row is None:
                row = tables.OptCopywrite(copywrite_id=copywrite_id)
                s.add(row)
            row.product_id = draft.product_id
            row.copy_type = draft.copy_type
            row.variant_no = draft.variant_no
            row.content = draft.content
            row.char_len = draft.char_len
            row.sku_basis_json = draft.sku_basis or {}
            row.compliance_json = {"hits": draft.compliance_hits, "passed": draft.passed}
            row.status = "passed" if draft.passed else "rejected"
            row.source = draft.source
            s.flush()
            return row.copywrite_id

    def list_by_product(self, product_id: str, copy_type: Optional[str] = None) -> list[dict[str, Any]]:
        with self.db.session() as s:
            stmt = select(tables.OptCopywrite).where(
                tables.OptCopywrite.product_id == product_id
            )
            if copy_type:
                stmt = stmt.where(tables.OptCopywrite.copy_type == copy_type)
            rows = s.execute(stmt.order_by(tables.OptCopywrite.copy_type, tables.OptCopywrite.variant_no)).scalars().all()
            return [
                {
                    "copywrite_id": r.copywrite_id,
                    "copy_type": r.copy_type,
                    "variant_no": r.variant_no,
                    "content": r.content,
                    "char_len": r.char_len,
                    "status": r.status,
                    "source": r.source,
                }
                for r in rows
            ]


# ---------- 图片 ----------

class ImageRepo:
    def __init__(self, db: Database):
        self.db = db

    def create_batch(self, batch_id: str, product_id: str, image_type: str,
                     plan: dict[str, Any], target_count: int) -> None:
        with self.db.session() as s:
            s.add(tables.OptImageBatch(
                batch_id=batch_id, product_id=product_id, image_type=image_type,
                plan_json=plan, target_count=target_count, status="generating",
            ))

    def upsert_image(self, image: dict[str, Any]) -> str:
        """幂等写入单图：同 (batch_id, image_type, variant_no) 覆盖更新。"""
        image_id = image.get("image_id") or new_id("img")
        with self.db.session() as s:
            row = s.execute(
                select(tables.OptImage).where(
                    tables.OptImage.batch_id == image["batch_id"],
                    tables.OptImage.image_type == image["image_type"],
                    tables.OptImage.variant_no == image["variant_no"],
                )
            ).scalar_one_or_none()
            if row is None:
                row = tables.OptImage(image_id=image_id)
                s.add(row)
            row.batch_id = image["batch_id"]
            row.product_id = image["product_id"]
            row.image_type = image["image_type"]
            row.variant_no = image["variant_no"]
            row.file_path = image.get("file_path", "")
            row.phash = image.get("phash", "")
            row.width = image.get("width", 0)
            row.height = image.get("height", 0)
            row.quality_json = image.get("quality_json", {})
            row.quality_ok = int(image.get("quality_ok", False))
            s.flush()
            return row.image_id

    def set_batch_status(self, batch_id: str, status: str, gate: dict[str, Any] | None = None) -> None:
        with self.db.session() as s:
            row = s.get(tables.OptImageBatch, batch_id)
            if row:
                row.status = status
                if gate is not None:
                    row.gate_json = gate


# ---------- 类目记忆 ----------

class CategoryMemoryRepo:
    def __init__(self, db: Database):
        self.db = db

    def get_or_create(self, category: str) -> tables.OptCategoryMemory:
        with self.db.session() as s:
            row = s.get(tables.OptCategoryMemory, category)
            if row is None:
                row = tables.OptCategoryMemory(category=category)
                s.add(row)
                s.flush()
            return row

    def record(self, category: str, *, passed: bool = True, reject_reason: str = "") -> None:
        with self.db.session() as s:
            row = s.get(tables.OptCategoryMemory, category)
            if row is None:
                row = tables.OptCategoryMemory(category=category)
                s.add(row)
            if passed:
                row.pass_count += 1
            else:
                row.reject_count += 1
                reasons = dict(row.reject_reasons_json or {})
                reasons[reject_reason] = reasons.get(reject_reason, 0) + 1
                row.reject_reasons_json = reasons

    def update_strategy(self, category: str, strategy: dict[str, Any]) -> None:
        with self.db.session() as s:
            row = s.get(tables.OptCategoryMemory, category)
            if row is None:
                row = tables.OptCategoryMemory(category=category)
                s.add(row)
            row.image_strategy_json = strategy


# ---------- 视频二创版本 ----------

class VideoVariantRepo:
    """视频二创版本（A/B 候选）数据访问：读取 + 上传成功后回填平台素材 ID。"""

    def __init__(self, db: Database):
        self.db = db

    def get(self, variant_id: str) -> Optional[dict[str, Any]]:
        with self.db.session() as s:
            row = s.get(tables.OptVideoVariant, variant_id)
            if row is None:
                return None
            return {
                "variant_id": row.variant_id,
                "product_id": row.product_id,
                "source_asset_id": row.source_asset_id,
                "variant_no": row.variant_no,
                "template_id": row.template_id,
                "copywrite_ids": row.copywrite_ids,
                "file_path": row.file_path,
                "spec_ok": bool(row.spec_ok),
                "review_status": row.review_status,
                "upload_status": row.upload_status,
                "platform_material_id": row.platform_material_id or "",
                "evaluation": row.evaluation,
            }

    def update_platform_material_id(
        self, variant_id: str, platform_material_id: str,
        upload_status: str = "uploaded",
    ) -> bool:
        """上传成功后回填平台素材 ID（幂等；不存在返回 False）。

        集成缺口修复（v1.0-4）：上传只写 opt_upload_records 不回填 variant，
        导致 A/B 排序 only_uploaded 无法感知已上传素材；上传编排层在上传
        成功后调用本方法完成闭环。
        """
        if not platform_material_id:
            return False
        with self.db.session() as s:
            row = s.get(tables.OptVideoVariant, variant_id)
            if row is None:
                return False
            row.platform_material_id = platform_material_id
            row.upload_status = upload_status
            return True


# ---------- 评估回写 ----------

class EvaluationRepo:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, snap: EvaluationSnapshot) -> str:
        """幂等回写：(variant_id, report_date) 唯一。"""
        feedback_id = new_id("ev")
        with self.db.session() as s:
            row = s.execute(
                select(tables.OptEvaluationFeedback).where(
                    tables.OptEvaluationFeedback.variant_id == snap.variant_id,
                    tables.OptEvaluationFeedback.report_date == snap.report_date,
                )
            ).scalar_one_or_none()
            if row is None:
                row = tables.OptEvaluationFeedback(feedback_id=feedback_id)
                s.add(row)
            row.variant_id = snap.variant_id
            row.platform_material_id = ""
            row.report_date = snap.report_date
            row.exposure = snap.exposure
            row.clicks = snap.clicks
            row.spend = snap.spend
            row.orders = snap.orders
            row.roi = snap.roi
            row.diagnosis_json = snap.diagnosis
            row.score = snap.score
            row.evaluation = snap.evaluation
            row.stale = int(snap.stale)
            s.flush()
            return row.feedback_id

    def latest_by_variant(self, variant_id: str) -> Optional[dict[str, Any]]:
        with self.db.session() as s:
            row = s.execute(
                select(tables.OptEvaluationFeedback)
                .where(tables.OptEvaluationFeedback.variant_id == variant_id)
                .order_by(tables.OptEvaluationFeedback.report_date.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "report_date": row.report_date,
                "exposure": row.exposure,
                "clicks": row.clicks,
                "spend": row.spend,
                "orders": row.orders,
                "roi": row.roi,
                "score": row.score,
                "evaluation": row.evaluation,
                "stale": bool(row.stale),
            }
