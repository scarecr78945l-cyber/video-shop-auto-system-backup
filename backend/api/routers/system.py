"""系统路由（M0 域）：总览 / 任务队列 / 一键全停 / 配置读写 / 操作日志。

- GET  /api/overview                   总览看板聚合（stage/status/error_code 计数、
                                        今日漏斗、风控状态）
- GET  /api/jobs                       任务队列（过滤 stage/status/error_code + 分页）
- GET  /api/jobs/{job_id}              任务详情（evidence 脱敏摘要）
- POST /api/kill-switch                一键全停（S8，管理员）
- GET/PUT /api/app-config/{key}        配置读写（管理员写）
- GET  /api/logs                       操作日志（脱敏）
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from ..auth import AuthUser
from ..deps import get_current_user, get_services, require_admin
from ..errors import ApiError, invalid_state, not_found, redact_value
from ..schemas import AppConfigPutBody, KillSwitchBody
from ..services import KILL_SWITCH_CONFIG_KEY, Services

router = APIRouter(prefix="/api", tags=["system"])


# ---------------------------------------------------------------- 总览


@router.get("/overview")
def overview(services: Services = Depends(get_services)) -> dict:
    """总览看板：任务队列统计 + 错误码分布 + 今日漏斗 + 风控状态。"""
    from foundation.tables import WorkflowJob

    db = services.m0_db
    with db.session() as session:
        jobs = list(session.scalars(select(WorkflowJob)).all())

    by_stage: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_error: dict[str, int] = {}
    today_funnel: dict[str, int] = {}
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    for job in jobs:
        by_stage[job.stage] = by_stage.get(job.stage, 0) + 1
        by_status[job.status] = by_status.get(job.status, 0) + 1
        if job.error_code:
            by_error[job.error_code] = by_error.get(job.error_code, 0) + 1
        created = job.created_at
        if created is not None and created >= today_start:
            today_funnel[job.stage] = today_funnel.get(job.stage, 0) + 1

    risk = _risk_status(services)
    return {
        "total_jobs": len(jobs),
        "jobs_by_stage": by_stage,
        "jobs_by_status": by_status,
        "jobs_by_error_code": by_error,
        "today_funnel": today_funnel,
        "risk": risk,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
    }


def _risk_status(services: Services) -> dict[str, Any]:
    """风控状态：kill_switch + M5 投放账户（余额元/状态/节流级）。"""
    kill = services.kill_switch_get()
    balance_yuan: Optional[float] = None
    account_status = "unknown"
    throttle_level = 0
    try:
        import ads.repo as ads_repo

        with services.m5_db.session() as session:
            state = ads_repo.get_account_state(session)
        if state is not None:
            balance_yuan = round(float(state.balance) / 100.0, 2) if state.balance is not None else None
            account_status = state.status
            throttle_level = state.throttle_level
    except Exception:  # noqa: BLE001 —— M5 库不可用不影响总览其余部分
        pass
    return {
        "kill_switch_enabled": kill,
        "kill_switch_key": KILL_SWITCH_CONFIG_KEY,
        "ad_balance_yuan": balance_yuan,
        "ad_account_status": account_status,
        "ad_throttle_level": throttle_level,
    }


# ---------------------------------------------------------------- 任务队列


def _job_to_dict(job) -> dict[str, Any]:
    from ..errors import iso_z

    return {
        "id": job.id,
        "product_id": job.product_id,
        "stage": job.stage,
        "status": job.status,
        "error_code": job.error_code,
        "error_message": job.error_message or "",
        "retry_count": job.retry_count,
        "generation_version": job.generation_version,
        "retry_after": iso_z(job.retry_after),
        "lease_owner": job.lease_owner,
        "lease_expires_at": iso_z(job.lease_expires_at),
        "created_at": iso_z(job.created_at),
        "updated_at": iso_z(job.updated_at),
    }


@router.get("/jobs")
def list_jobs(
    stage: Optional[str] = None,
    status: Optional[str] = None,
    error_code: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    services: Services = Depends(get_services),
) -> dict:
    """任务队列列表：过滤 stage/status/error_code + 分页（按 id 降序）。"""
    from foundation.tables import WorkflowJob

    with services.m0_db.session() as session:
        stmt = select(WorkflowJob)
        if stage:
            stmt = stmt.where(WorkflowJob.stage == stage)
        if status:
            stmt = stmt.where(WorkflowJob.status == status)
        if error_code:
            stmt = stmt.where(WorkflowJob.error_code == error_code)
        total = session.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()
        rows = list(
            session.scalars(
                stmt.order_by(WorkflowJob.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_job_to_dict(r) for r in rows],
    }


@router.get("/jobs/{job_id}")
def job_detail(job_id: int, services: Services = Depends(get_services)) -> dict:
    """任务详情：含 evidence 脱敏摘要（payload/evidence 递归脱敏）。"""
    from foundation.tables import WorkflowJob

    with services.m0_db.session() as session:
        job = session.get(WorkflowJob, job_id)
    if job is None:
        raise not_found(f"任务 {job_id} 不存在")
    data = _job_to_dict(job)
    data["payload"] = redact_value(job.payload)
    data["evidence"] = redact_value(job.evidence_json)
    return data


# ---------------------------------------------------------------- 一键全停


@router.post("/kill-switch")
def kill_switch(
    body: KillSwitchBody,
    user: AuthUser = Depends(require_admin),
    services: Services = Depends(get_services),
) -> dict:
    """一键全停（S8，管理员）：写 M0 app_config `risk.kill_switch`（对齐 M0_KILL_SWITCH）。"""
    result = services.kill_switch_set(body.enabled)
    services.audit(
        event="kill_switch.set",
        message=f"一键全停 {'开启' if body.enabled else '关闭'}",
        evidence=result,
        operator=user.username,
        level="WARNING",
    )
    return {"ok": True, **result}


# ---------------------------------------------------------------- 配置读写


@router.get("/app-config/{key}")
def get_app_config(key: str, services: Services = Depends(get_services)) -> dict:
    """读全局配置（M0 app_config 表，值一律 JSON）。"""
    from foundation.tables import AppConfigRow

    with services.m0_db.session() as session:
        row = session.get(AppConfigRow, key)
    if row is None:
        raise not_found(f"配置键不存在: {key}")
    return _app_config_row(row)


@router.put("/app-config/{key}")
def put_app_config(
    key: str,
    body: AppConfigPutBody,
    user: AuthUser = Depends(require_admin),
    services: Services = Depends(get_services),
) -> dict:
    """写全局配置（管理员）：upsert M0 app_config（值 JSON）。"""
    from foundation.tables import AppConfigRow

    with services.m0_db.session() as session:
        row = session.get(AppConfigRow, key)
        if row is None:
            row = AppConfigRow(
                key=key,
                value=body.value if body.value is not None else {},
                description=body.description or "",
            )
            session.add(row)
        else:
            row.value = body.value if body.value is not None else row.value
            if body.description is not None:
                row.description = body.description
        session.flush()
        out = _app_config_row(row)
    services.audit(
        event="app_config.set",
        message=f"配置写入: {key}",
        evidence={"key": key},
        operator=user.username,
    )
    return out


def _app_config_row(row) -> dict[str, Any]:
    from ..errors import iso_z

    return {
        "key": row.key,
        "value": row.value if row.value is not None else {},
        "description": row.description or "",
        "updated_at": iso_z(row.updated_at),
    }


# ---------------------------------------------------------------- 操作日志


@router.get("/logs")
def list_logs(
    module: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    services: Services = Depends(get_services),
) -> dict:
    """操作日志（只读，evidence 脱敏）。"""
    from foundation.tables import LogEntry

    with services.m0_db.session() as session:
        stmt = select(LogEntry).order_by(LogEntry.id.desc()).limit(limit)
        if module:
            stmt = stmt.where(LogEntry.module == module)
        if level:
            stmt = stmt.where(LogEntry.level == level)
        rows = list(session.scalars(stmt).all())
    items = []
    for r in reversed(rows):  # 升序输出（时间正序）
        items.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat().replace("+00:00", "Z")
                if r.created_at else None,
                "module": r.module,
                "level": r.level,
                "event": r.event or "",
                "message": r.message or "",
                "evidence": redact_value(r.evidence or {}),
            }
        )
    return {"total": len(items), "items": items}
