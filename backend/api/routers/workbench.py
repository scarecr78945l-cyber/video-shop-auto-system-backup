"""人工闸门工作台路由（跨模块聚合）。

- GET  /api/workbench/gates       闸门待办聚合计数（选品复核/上架确认/图片审核/
                                   素材预审/验证码接管/登录接管）
- GET  /api/workbench/exceptions  异常中心（blocked/waiting_* 任务清单，evidence 脱敏）
- POST /api/workbench/retry/{job_id}  人工接管后重试（waiting_* → 断点续跑；记录操作人）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from ..auth import AuthUser
from ..deps import get_current_user, get_services
from ..errors import ApiError, invalid_state, iso_z, not_found, redact_value
from ..services import Services

router = APIRouter(prefix="/api/workbench", tags=["workbench"])

# 异常中心关注的状态
EXCEPTION_STATUSES = ("blocked", "waiting_verification", "waiting_login")


# ---------------------------------------------------------------- 闸门待办


@router.get("/gates")
def gate_todo_counts(services: Services = Depends(get_services)) -> dict:
    """闸门待办聚合计数（跨 M1/M4/M3/M2/M0 只读统计）。"""
    counts: dict[str, int] = {
        "sourcing_review": 0,       # 选品复核：products.state=manual_review
        "listing_confirm": 0,       # 上架确认：listing_tasks.status=pending
        "image_review": 0,          # 图片审核：opt_images.review_status=pending
        "material_pre_review": 0,   # 素材预审：asset_items.relevance_status=manual_review
        "verification_takeover": 0,  # 验证码接管：workflow_jobs.status=waiting_verification
        "login_takeover": 0,        # 登录接管：workflow_jobs.status=waiting_login
    }
    try:
        from sourcing.tables import Product

        with services.sourcing_db.session() as session:
            counts["sourcing_review"] = session.execute(
                select(func.count(Product.id)).where(Product.state == "manual_review")
            ).scalar_one()
    except Exception:  # noqa: BLE001 —— 单模块库不可用不影响其余计数
        pass
    try:
        from listing.tables import ListingTaskRow

        with services.m4_db.session() as session:
            counts["listing_confirm"] = session.execute(
                select(func.count(ListingTaskRow.task_id)).where(
                    ListingTaskRow.status == "pending"
                )
            ).scalar_one()
    except Exception:  # noqa: BLE001
        pass
    try:
        from optimization.tables import OptImage

        with services.m3_db.session() as session:
            counts["image_review"] = session.execute(
                select(func.count(OptImage.image_id)).where(
                    OptImage.review_status == "pending"
                )
            ).scalar_one()
    except Exception:  # noqa: BLE001
        pass
    try:
        from materials.tables import AssetItem

        with services.materials_db.session() as session:
            counts["material_pre_review"] = session.execute(
                select(func.count(AssetItem.id)).where(
                    AssetItem.relevance_status == "manual_review"
                )
            ).scalar_one()
    except Exception:  # noqa: BLE001
        pass
    try:
        from foundation.tables import WorkflowJob

        with services.m0_db.session() as session:
            counts["verification_takeover"] = session.execute(
                select(func.count(WorkflowJob.id)).where(
                    WorkflowJob.status == "waiting_verification"
                )
            ).scalar_one()
            counts["login_takeover"] = session.execute(
                select(func.count(WorkflowJob.id)).where(
                    WorkflowJob.status == "waiting_login"
                )
            ).scalar_one()
    except Exception:  # noqa: BLE001
        pass
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ---------------------------------------------------------------- 异常中心


@router.get("/exceptions")
def exceptions(
    status: Optional[str] = None,
    stage: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    services: Services = Depends(get_services),
) -> dict:
    """异常中心：blocked/waiting_* 任务清单（error_code/evidence 摘要/暂停截止）。"""
    from foundation.tables import WorkflowJob

    filters = [WorkflowJob.status.in_(EXCEPTION_STATUSES)]
    if status:
        filters.append(WorkflowJob.status == status)
    if stage:
        filters.append(WorkflowJob.stage == stage)
    with services.m0_db.session() as session:
        rows = list(
            session.scalars(
                select(WorkflowJob)
                .where(*filters)
                .order_by(WorkflowJob.updated_at.desc())
                .limit(limit)
            ).all()
        )
    return {
        "total": len(rows),
        "items": [
            {
                "id": j.id,
                "product_id": j.product_id,
                "stage": j.stage,
                "status": j.status,
                "error_code": j.error_code,
                "error_message": (j.error_message or "")[:200],
                "retry_count": j.retry_count,
                "retry_after": iso_z(j.retry_after),
                "lease_owner": j.lease_owner,
                "lease_expires_at": iso_z(j.lease_expires_at),
                "evidence": redact_value(j.evidence_json or {}),
                "created_at": iso_z(j.created_at),
                "updated_at": iso_z(j.updated_at),
            }
            for j in rows
        ],
    }


# ---------------------------------------------------------------- 人工接管重试


@router.post("/retry/{job_id}")
def retry_job(
    job_id: int,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """人工接管后重试：waiting_* / blocked → pending（断点续跑，立即可领取）。"""
    from datetime import datetime, timezone as _tz

    from foundation.tables import WorkflowJob

    with services.m0_db.session() as session:
        job = session.get(WorkflowJob, job_id)
        if job is None:
            raise not_found(f"任务 {job_id} 不存在")
        if job.status not in EXCEPTION_STATUSES:
            raise invalid_state(
                f"任务 {job_id} 状态为 {job.status}，仅 {EXCEPTION_STATUSES} 可人工重试"
            )
        job.status = "pending"
        job.retry_after = datetime.now(_tz.utc)  # 立即到点可被 claim
        job.lease_owner = None
        job.lease_expires_at = None
        result = {
            "id": job.id,
            "status": job.status,
            "stage": job.stage,
            "error_code": job.error_code,
        }
    services.audit(
        event="workbench.retry",
        message=f"人工接管后重试: job_id={job_id}",
        evidence={"job_id": job_id, "from_status": "waiting/manual"},
        operator=user.username,
    )
    return {"ok": True, **result, "operator": user.username}
