"""上架路由（M4 域，listing repo/状态机）。

- GET  /api/listing/tasks             上架任务列表（按 9 态 status 过滤；列：
                                       product_id/title/status/attempts/error_code/updated_at）
- GET  /api/listing/tasks/{task_id}   上架任务详情（状态机轨迹 + gate_result +
                                       platform_spu_id/product_link + 拒审记录）
- GET  /api/listing/tasks/{task_id}/op-logs
                                      微信操作日志（只读，脱敏摘要）
- POST /api/listing/tasks/{task_id}/confirm
                                      上架最终确认闸门（pending → 入队 creating；记录操作人）
- POST /api/listing/tasks/{task_id}/retry
                                      拒审修复后重提（rejected/retry_candidate →
                                       二次门禁后重提；记录操作人）
- GET  /api/listing/ready             待上架商品（候选池视图，价格 分→元）
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from ..auth import AuthUser
from ..deps import get_current_user, get_services
from ..errors import (
    ApiError,
    cents_to_yuan,
    invalid_state,
    iso_z,
    json_safe,
    not_found,
    redact_value,
)
from ..schemas import ListingConfirmBody
from ..services import Services

router = APIRouter(prefix="/api/listing", tags=["m4-listing"])


def _task_row_dict(row, title: Optional[str] = None, error_code: Optional[str] = None) -> dict[str, Any]:
    return {
        "task_id": row.task_id,
        "product_id": row.product_id,
        "generation_version": row.generation_version,
        "stage": row.stage,
        "status": row.status,
        "title": title,
        "gate_result": json_safe(row.gate_result),
        "platform_spu_id": row.platform_spu_id,
        "product_link": row.product_link,
        "link_verified_at": iso_z(row.link_verified_at),
        "reject_reason_code": row.reject_reason_code,
        "attempts": row.attempts or 0,
        "error_code": error_code,
        "lease_owner": row.lease_owner,
        "lease_expires_at": iso_z(row.lease_expires_at),
        "created_at": iso_z(row.created_at),
        "updated_at": iso_z(row.updated_at),
    }


def _latest_oplog_error(session, task_id: str) -> Optional[str]:
    from listing.tables import ListingOpLogRow

    row = session.execute(
        select(ListingOpLogRow.error_code)
        .where(
            ListingOpLogRow.task_id == task_id,
            ListingOpLogRow.error_code.is_not(None),
        )
        .order_by(ListingOpLogRow.log_id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row


@router.get("/tasks")
def list_tasks(
    status: Optional[str] = None,
    product_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    services: Services = Depends(get_services),
) -> dict:
    """上架任务列表：按 9 态 status 过滤 + 分页（含标题/最新 op_log error_code）。"""
    from listing.tables import ListingSpuRow, ListingTaskRow

    with services.m4_db.session() as session:
        filters = []
        if status:
            filters.append(ListingTaskRow.status == status)
        if product_id is not None:
            filters.append(ListingTaskRow.product_id == product_id)
        total = session.execute(
            func.count(ListingTaskRow.task_id).select().where(*filters)
        ).scalar_one()
        rows = list(
            session.scalars(
                select(ListingTaskRow)
                .where(*filters)
                .order_by(ListingTaskRow.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        task_ids = [r.task_id for r in rows]
        spu_titles: dict[str, str] = {}
        if task_ids:
            spu_rows = list(
                session.scalars(
                    select(ListingSpuRow)
                    .where(ListingSpuRow.task_id.in_(task_ids))
                    .order_by(ListingSpuRow.created_at.asc())
                ).all()
            )
            for s in spu_rows:
                spu_titles.setdefault(s.task_id, s.title)
        error_codes = {
            r.task_id: _latest_oplog_error(session, r.task_id)
            for r in rows
        }
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            _task_row_dict(r, title=spu_titles.get(r.task_id), error_code=error_codes.get(r.task_id))
            for r in rows
        ],
    }


@router.get("/tasks/{task_id}")
def task_detail(task_id: str, services: Services = Depends(get_services)) -> dict:
    """上架任务详情：状态机轨迹（op_logs transition）+ gate_result + 拒审记录。"""
    from listing.tables import ListingAuditRecordRow, ListingSpuRow, ListingTaskRow

    with services.m4_db.session() as session:
        row = session.get(ListingTaskRow, task_id)
        if row is None:
            raise not_found(f"上架任务不存在: {task_id}")
        spu = session.execute(
            select(ListingSpuRow)
            .where(ListingSpuRow.task_id == task_id)
            .order_by(ListingSpuRow.created_at.asc())
        ).scalars().first()
        audits = list(
            session.scalars(
                select(ListingAuditRecordRow)
                .where(ListingAuditRecordRow.task_id == task_id)
                .order_by(ListingAuditRecordRow.audit_record_id)
            ).all()
        )
    data = _task_row_dict(row, title=spu.title if spu else None)
    data["spu"] = (
        {
            "spu_id": spu.spu_id,
            "title": spu.title,
            "category_id": spu.category_id,
            "status": spu.status,
            "audit_id": spu.audit_id,
        }
        if spu
        else None
    )
    data["audit_records"] = [
        {
            "audit_record_id": a.audit_record_id,
            "audit_id": a.audit_id,
            "submit_at": iso_z(a.submit_at),
            "last_query_at": iso_z(a.last_query_at),
            "audit_status": a.audit_status,
            "reject_reason": a.reject_reason,
            "reject_category": a.reject_category,
            "fix_candidate": json_safe(a.fix_candidate),
            "resubmit_required": bool(a.resubmit_required),
            "evidence": redact_value(json_safe(a.evidence)),
        }
        for a in audits
    ]
    return data


@router.get("/tasks/{task_id}/op-logs")
def task_op_logs(
    task_id: str,
    limit: int = Query(200, ge=1, le=1000),
    services: Services = Depends(get_services),
) -> dict:
    """微信操作日志（只读，evidence 脱敏摘要）。"""
    from listing.tables import ListingTaskRow

    with services.m4_db.session() as session:
        exists = session.get(ListingTaskRow, task_id)
    if exists is None:
        raise not_found(f"上架任务不存在: {task_id}")
    logs = services.m4_repo.list_op_logs(task_id=task_id, limit=limit)
    return {
        "task_id": task_id,
        "total": len(logs),
        "items": [
            {
                "log_id": log.log_id,
                "request_id": log.request_id,
                "api": log.api,
                "direction": log.direction,
                "payload_digest": log.payload_digest,
                "status_code": log.status_code,
                "error_code": log.error_code,
                "platform_code": log.platform_code,
                "evidence": redact_value(json_safe(log.evidence_json)),
                "created_at": iso_z(log.created_at),
            }
            for log in logs
        ],
    }


# ---------------------------------------------------------------- 确认闸门


@router.post("/tasks/{task_id}/confirm")
def task_confirm(
    task_id: str,
    body: ListingConfirmBody,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """上架最终确认闸门（10 文档第五节）：pending → 入队 creating（记录操作人）。"""
    repo = services.m4_repo
    machine = services.m4_state_machine
    task = repo.get_task(task_id)
    if task is None:
        raise not_found(f"上架任务不存在: {task_id}")
    if task.status != "pending":
        raise invalid_state(
            f"任务 {task_id} 状态为 {task.status}，仅 pending 可确认入队"
        )
    try:
        updated = machine.transition(
            task,
            "creating",
            evidence={"operator": user.username, "note": body.note or ""},
        )
    except Exception as exc:  # noqa: BLE001 —— 状态机异常统一转 409
        raise invalid_state(f"确认入队失败: {exc}") from exc
    services.audit(
        event="listing.confirm",
        message=f"上架确认入队: {task_id}",
        evidence={"task_id": task_id, "note": body.note or ""},
        operator=user.username,
    )
    return {
        "ok": True,
        "task_id": task_id,
        "status": updated.status,
        "operator": user.username,
    }


# ---------------------------------------------------------------- 拒审重提


@router.post("/tasks/{task_id}/retry")
def task_retry(
    task_id: str,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """拒审修复后重提（二次门禁语义由前端确认后调用）：

    - retry_candidate → creating（合法迁移）；
    - rejected → 先 rejected→retry_candidate（人工确认已修复），再 → creating。
    真实 ListingGate 全量校验未接入（v1.0 fixtures 简化，REPORT.md 已登记）。
    """
    repo = services.m4_repo
    machine = services.m4_state_machine
    task = repo.get_task(task_id)
    if task is None:
        raise not_found(f"上架任务不存在: {task_id}")
    try:
        if task.status == "retry_candidate":
            updated = machine.transition(
                task, "creating", evidence={"operator": user.username, "action": "manual_retry"}
            )
        elif task.status == "rejected":
            intermediate = machine.transition(
                task,
                "retry_candidate",
                evidence={"operator": user.username, "action": "manual_fixed"},
            )
            updated = machine.transition(
                intermediate,
                "creating",
                evidence={"operator": user.username, "action": "manual_retry"},
            )
        else:
            raise invalid_state(
                f"任务 {task_id} 状态为 {task.status}，仅 rejected/retry_candidate 可重提"
            )
    except Exception as exc:  # noqa: BLE001 —— 状态机异常统一转 409
        raise invalid_state(f"重提失败: {exc}") from exc
    services.audit(
        event="listing.retry",
        message=f"拒审修复后重提: {task_id}",
        evidence={"task_id": task_id},
        operator=user.username,
    )
    return {
        "ok": True,
        "task_id": task_id,
        "status": updated.status,
        "operator": user.username,
    }


# ---------------------------------------------------------------- 待上架商品


@router.get("/ready")
def listing_ready(
    limit: Optional[int] = Query(None, ge=1, le=50),
    services: Services = Depends(get_services),
) -> dict:
    """待上架/已上架商品（候选池视图）：仅 status=listed 且链接已验证；价格 分→元。"""
    pool = services.m4_candidate_pool
    items = pool.get_sale_candidates(limit=limit)
    return {
        "total": len(items),
        "evidence": pool.last_evidence or {},
        "items": [
            {
                **item,
                "price_min_yuan": cents_to_yuan(item.pop("price_min_cents", None)),
                "price_max_yuan": cents_to_yuan(item.pop("price_max_cents", None)),
                "link_verified_at": iso_z(item.get("link_verified_at")),
            }
            for item in items
        ],
    }
