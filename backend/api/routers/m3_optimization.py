"""素材优化路由（M3 域，optimization repo / review gate）。

- GET  /api/optimization/batches            生图批次列表（过滤 status）
- GET  /api/optimization/batches/{batch_id} 批次详情（assets: main/detail/status/
                                             rejection_reason/audit）
- POST /api/optimization/assets/{image_id}/decision
                                           图片审核人工判定（approve/reject；对接 M3
                                           review gate + P0-2 规则草稿闭环）
- POST /api/optimization/batches/{batch_id}/approve
                                           整批通过
- GET  /api/optimization/copywrites         文案/标题候选（只读 title/script/ad/badge）
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from ..auth import AuthUser
from ..deps import get_current_user, get_services
from ..errors import ApiError, invalid_state, iso_z, json_safe, not_found, redact_value
from ..schemas import ImageDecisionBody
from ..services import Services

router = APIRouter(prefix="/api/optimization", tags=["m3-optimization"])


# ---------------------------------------------------------------- 批次列表


def _batch_to_dict(row, image_count: int) -> dict[str, Any]:
    return {
        "batch_id": row.batch_id,
        "product_id": row.product_id,
        "image_type": row.image_type,
        "plan": json_safe(row.plan_json),
        "target_count": row.target_count or 0,
        "gate": json_safe(row.gate_json),
        "status": row.status,
        "image_count": image_count,
        "created_at": iso_z(row.created_at),
        "updated_at": iso_z(row.updated_at),
    }


@router.get("/batches")
def list_batches(
    status: Optional[str] = None,
    product_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    services: Services = Depends(get_services),
) -> dict:
    """生图批次列表：过滤 status/product_id + 分页（含每批图片数）。"""
    from optimization.tables import OptImage, OptImageBatch

    with services.m3_db.session() as session:
        filters = []
        if status:
            filters.append(OptImageBatch.status == status)
        if product_id:
            filters.append(OptImageBatch.product_id == product_id)
        total = session.execute(
            func.count(OptImageBatch.batch_id).select().where(*filters)
        ).scalar_one()
        batches = list(
            session.scalars(
                select(OptImageBatch)
                .where(*filters)
                .order_by(OptImageBatch.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        counts = dict(
            session.execute(
                select(OptImage.batch_id, func.count(OptImage.image_id))
                .group_by(OptImage.batch_id)
            ).all()
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            _batch_to_dict(b, counts.get(b.batch_id, 0)) for b in batches
        ],
    }


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: str, services: Services = Depends(get_services)) -> dict:
    """批次详情：批次 + assets（main/detail/status/reject_reason/audit 审核记录）。"""
    from optimization.tables import OptImage, OptImageBatch, OptReviewRecord

    with services.m3_db.session() as session:
        batch = session.get(OptImageBatch, batch_id)
        if batch is None:
            raise not_found(f"批次不存在: {batch_id}")
        images = list(
            session.scalars(
                select(OptImage)
                .where(OptImage.batch_id == batch_id)
                .order_by(OptImage.image_type, OptImage.variant_no)
            ).all()
        )
        image_ids = [i.image_id for i in images]
        reviews = []
        if image_ids:
            reviews = list(
                session.scalars(
                    select(OptReviewRecord)
                    .where(
                        OptReviewRecord.target_type == "image",
                        OptReviewRecord.target_id.in_(image_ids),
                    )
                    .order_by(OptReviewRecord.created_at)
                ).all()
            )
    review_by_image: dict[str, list[dict[str, Any]]] = {}
    for r in reviews:
        review_by_image.setdefault(r.target_id, []).append(
            {
                "review_id": r.review_id,
                "gate_type": r.gate_type,
                "result": r.result,
                "reasons": json_safe(r.reasons_json),
                "reviewer": r.reviewer,
                "created_at": iso_z(r.created_at),
            }
        )
    return {
        **_batch_to_dict(batch, len(images)),
        "assets": [
            {
                "image_id": i.image_id,
                "image_type": i.image_type,
                "variant_no": i.variant_no,
                "file_path": i.file_path,
                "phash": i.phash,
                "width": i.width,
                "height": i.height,
                "quality": json_safe(i.quality_json),
                "quality_ok": bool(i.quality_ok),
                "review_status": i.review_status,
                "reject_reason": i.reject_reason or "",
                "category_memory_key": i.category_memory_key or "",
                "audit": review_by_image.get(i.image_id, []),
                "created_at": iso_z(i.created_at),
                "updated_at": iso_z(i.updated_at),
            }
            for i in images
        ],
    }


# ---------------------------------------------------------------- 图片审核判定


@router.post("/assets/{image_id}/decision")
def image_decision(
    image_id: str,
    body: ImageDecisionBody,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """图片审核人工判定：decision ∈ approve/reject。

    - 写 opt_images.review_status（approved/rejected）+ reject_reason；
    - 写 opt_review_records（gate_type=manual，result=pass/reject，reviewer=操作人）；
    - P0-2 规则草稿闭环：沉淀 learning_rule_drafts（m0_queue.create_rule_draft）。
    """
    if body.decision not in ("approve", "reject"):
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="decision 仅支持 approve / reject",
        )
    from optimization.repo import new_id
    from optimization.tables import OptImage, OptReviewRecord

    with services.m3_db.session() as session:
        image = session.get(OptImage, image_id)
        if image is None:
            raise not_found(f"图片不存在: {image_id}")
        image.review_status = "approved" if body.decision == "approve" else "rejected"
        image.reject_reason = body.reason or ""
        # 同一事务内落审核记录（避免嵌套会话触发 SQLite 写锁）
        review = OptReviewRecord(
            review_id=new_id("rv"),
            target_type="image",
            target_id=image_id,
            gate_type="manual",
            result="pass" if body.decision == "approve" else "reject",
            reasons_json={
                "decision": body.decision,
                "reason": body.reason or "",
                "operator": user.username,
            },
            reviewer=user.username,
        )
        session.add(review)
        session.flush()
        review_id = review.review_id
    # P0-2：人审→规则草稿闭环（幂等：同 stage+rule_key 累计 sample_count）
    rule_key = f"image_review_{body.decision}"
    services.m0_queue.create_rule_draft(
        stage="image_generation",
        rule_key=rule_key,
        rule_text=f"人工审核判定图片 {image_id} 为 {body.decision}"
        + (f"（原因：{body.reason}）" if body.reason else ""),
        evidence={"image_id": image_id, "decision": body.decision, "review_id": review_id},
    )
    services.audit(
        event="optimization.image_decision",
        message=f"图片审核人工判定: {image_id} → {body.decision}",
        evidence={"image_id": image_id, "decision": body.decision},
        operator=user.username,
    )
    return {
        "ok": True,
        "image_id": image_id,
        "review_status": image.review_status,
        "review_id": review_id,
        "rule_draft_created": True,
        "operator": user.username,
    }


# ---------------------------------------------------------------- 整批通过


@router.post("/batches/{batch_id}/approve")
def approve_batch(
    batch_id: str,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """整批通过：批次 status → approved，批内全部图片 review_status → approved。"""
    from optimization.tables import OptImage, OptImageBatch

    with services.m3_db.session() as session:
        batch = session.get(OptImageBatch, batch_id)
        if batch is None:
            raise not_found(f"批次不存在: {batch_id}")
        if batch.status == "approved":
            return {
                "ok": True,
                "batch_id": batch_id,
                "status": batch.status,
                "already_approved": True,
            }
        batch.status = "approved"
        images = list(
            session.scalars(
                select(OptImage).where(OptImage.batch_id == batch_id)
            ).all()
        )
        for img in images:
            img.review_status = "approved"
    services.audit(
        event="optimization.batch_approve",
        message=f"生图整批通过: {batch_id}（{len(images)} 张）",
        evidence={"batch_id": batch_id, "images": len(images)},
        operator=user.username,
    )
    return {
        "ok": True,
        "batch_id": batch_id,
        "status": "approved",
        "images_approved": len(images),
        "operator": user.username,
    }


# ---------------------------------------------------------------- 文案候选


@router.get("/copywrites")
def list_copywrites(
    product_id: Optional[str] = None,
    copy_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    services: Services = Depends(get_services),
) -> dict:
    """文案/标题候选（只读）：title/script/ad/badge。"""
    from optimization.tables import OptCopywrite

    with services.m3_db.session() as session:
        filters = []
        if product_id:
            filters.append(OptCopywrite.product_id == product_id)
        if copy_type:
            filters.append(OptCopywrite.copy_type == copy_type)
        if status:
            filters.append(OptCopywrite.status == status)
        rows = list(
            session.scalars(
                select(OptCopywrite)
                .where(*filters)
                .order_by(OptCopywrite.copy_type, OptCopywrite.variant_no)
                .limit(limit)
            ).all()
        )
    return {
        "total": len(rows),
        "items": [
            {
                "copywrite_id": r.copywrite_id,
                "product_id": r.product_id,
                "copy_type": r.copy_type,
                "variant_no": r.variant_no,
                "content": r.content,
                "char_len": r.char_len,
                "sku_basis": json_safe(r.sku_basis_json),
                "compliance": json_safe(r.compliance_json),
                "status": r.status,
                "source": r.source,
                "created_at": iso_z(r.created_at),
            }
            for r in rows
        ],
    }
