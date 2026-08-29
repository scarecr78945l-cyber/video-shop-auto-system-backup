"""投放/托管路由（M5 域，ads repo）。

- GET  /api/ads/campaigns             托管看板列表（对齐后台列：商品/目标出价/诊断/
                                       曝光/花费/成交/补贴/操作；金额一律 元 float）
- GET  /api/ads/campaigns/{campaign_id} 托管详情（设置 + 报表快照序列）
- GET  /api/ads/account               投放账户状态（余额 分→元）
- POST /api/ads/campaigns/{id}/pause|resume|end
                                      暂停/恢复/结束托管（记录操作人）
- POST /api/ads/campaigns/{id}/materials
                                      添加/换素材（body {material_ids}；优选顺序提示）
- GET  /api/ads/report                报表聚合（按日 spend/gmv/subsidy/impressions，元）
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
)
from ..schemas import AdsMaterialsBody
from ..services import Services

router = APIRouter(prefix="/api/ads", tags=["m5-ads"])

# M5 状态（英文枚举，入库值，原样透传；前端 lib/enums.ts 翻译展示）
CAMPAIGN_STATUSES = ("pending", "active", "paused", "not_eligible", "ended")


# ---------------------------------------------------------------- 工具


def _snapshot_dict(snap) -> dict[str, Any]:
    return {
        "id": snap.id,
        "recorded_at": iso_z(snap.recorded_at),
        "impressions": snap.impressions or 0,
        "spend_yuan": cents_to_yuan(snap.spend),
        "gmv_yuan": cents_to_yuan(snap.gmv),
        "subsidy_yuan": cents_to_yuan(snap.platform_subsidy),
        "diagnosis": snap.diagnosis,
        "status": snap.status,
    }


def _campaign_dict(cam, latest_snapshot: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "id": cam.id,
        "product_id": cam.product_id,
        "ad_mode": cam.ad_mode,
        "target_type": cam.target_type,
        "target_roi": cam.target_roi,
        "material_ids": json_safe(cam.material_ids_json) or [],
        "status": cam.status,
        "diagnosis": cam.diagnosis,
        "batch_id": cam.batch_id,
        "created_at": iso_z(cam.created_at),
        "updated_at": iso_z(cam.updated_at),
        "latest_snapshot": latest_snapshot,
    }


def _get_campaign_or_404(services: Services, campaign_id: int):
    import ads.repo as ads_repo

    with services.m5_db.session() as session:
        cam = ads_repo.get_campaign(session, campaign_id)
    if cam is None:
        raise not_found(f"托管计划不存在: {campaign_id}")
    return cam


# ---------------------------------------------------------------- 看板列表


@router.get("/campaigns")
def list_campaigns(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    services: Services = Depends(get_services),
) -> dict:
    """托管看板列表（对齐后台列：商品/目标出价/诊断/曝光/花费/成交/补贴/操作）。"""
    from ads.tables import AdCampaign, AdReportSnapshot

    with services.m5_db.session() as session:
        filters = []
        if status:
            filters.append(AdCampaign.status == status)
        total = session.execute(
            func.count(AdCampaign.id).select().where(*filters)
        ).scalar_one()
        cams = list(
            session.scalars(
                select(AdCampaign)
                .where(*filters)
                .order_by(AdCampaign.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        cam_ids = [c.id for c in cams]
        latest: dict[int, Any] = {}
        if cam_ids:
            rows = list(
                session.scalars(
                    select(AdReportSnapshot)
                    .where(AdReportSnapshot.campaign_id.in_(cam_ids))
                    .order_by(AdReportSnapshot.recorded_at.desc())
                ).all()
            )
            for r in rows:
                latest.setdefault(r.campaign_id, r)  # 每条 campaign 保留最新快照
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            _campaign_dict(c, latest_snapshot=_snapshot_dict(latest[c.id]) if c.id in latest else None)
            for c in cams
        ],
    }


# ---------------------------------------------------------------- 托管详情


@router.get("/campaigns/{campaign_id}")
def campaign_detail(
    campaign_id: int, services: Services = Depends(get_services)
) -> dict:
    """托管详情：设置（target_type/target_roi/material_ids）+ 报表快照序列（recorded_at 升序）。"""
    import ads.repo as ads_repo

    cam = _get_campaign_or_404(services, campaign_id)
    with services.m5_db.session() as session:
        snaps = ads_repo.list_snapshots(session, campaign_id=campaign_id)
    data = _campaign_dict(cam)
    data["snapshots"] = [_snapshot_dict(s) for s in snaps]
    data["snapshot_count"] = len(snaps)
    return data


# ---------------------------------------------------------------- 账户状态


@router.get("/account")
def account_state(services: Services = Depends(get_services)) -> dict:
    """投放账户状态：余额（分→元）/status/throttle_level（S5 余额告警）。"""
    import ads.repo as ads_repo

    from ads.config import load_config as ads_load_config

    with services.m5_db.session() as session:
        state = ads_repo.get_account_state(session)
    min_balance_fen = ads_load_config().min_balance_fen
    if state is None:
        return {
            "balance_yuan": None,
            "status": "unknown",
            "throttle_level": 0,
            "paused_until": None,
            "pause_reason": "",
            "min_balance_yuan": round(min_balance_fen / 100.0, 2),
            "updated_at": None,
        }
    return {
        "balance_yuan": cents_to_yuan(state.balance),
        "status": state.status,
        "throttle_level": state.throttle_level or 0,
        "paused_until": iso_z(state.paused_until),
        "pause_reason": state.pause_reason or "",
        "min_balance_yuan": round(min_balance_fen / 100.0, 2),
        "updated_at": iso_z(state.updated_at),
    }


# ---------------------------------------------------------------- 暂停/恢复/结束


def _campaign_action(campaign_id: int, action: str, user: AuthUser, services: Services) -> dict:
    """pause → paused；resume → active；end → ended（状态机语义，记录操作人）。"""
    import ads.repo as ads_repo

    cam = _get_campaign_or_404(services, campaign_id)
    target = {"pause": "paused", "resume": "active", "end": "ended"}[action]
    if cam.status == target:
        return {
            "ok": True,
            "campaign_id": campaign_id,
            "status": cam.status,
            "already": True,
            "operator": user.username,
        }
    if action == "resume" and cam.status == "ended":
        raise invalid_state(f"已结束的托管计划不能恢复: {campaign_id}")
    with services.m5_db.session() as session:
        ok = ads_repo.update_campaign_status(session, campaign_id, target)
    if not ok:
        raise not_found(f"托管计划不存在: {campaign_id}")
    services.audit(
        event=f"ads.campaign_{action}",
        message=f"托管计划 {action}: campaign_id={campaign_id}",
        evidence={"campaign_id": campaign_id, "action": action, "to_status": target},
        operator=user.username,
    )
    return {
        "ok": True,
        "campaign_id": campaign_id,
        "status": target,
        "operator": user.username,
    }


@router.post("/campaigns/{campaign_id}/pause")
def campaign_pause(
    campaign_id: int,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """暂停托管。"""
    return _campaign_action(campaign_id, "pause", user, services)


@router.post("/campaigns/{campaign_id}/resume")
def campaign_resume(
    campaign_id: int,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """恢复托管。"""
    return _campaign_action(campaign_id, "resume", user, services)


@router.post("/campaigns/{campaign_id}/end")
def campaign_end(
    campaign_id: int,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """结束托管。"""
    return _campaign_action(campaign_id, "end", user, services)


# ---------------------------------------------------------------- 素材绑定


@router.post("/campaigns/{campaign_id}/materials")
def campaign_materials(
    campaign_id: int,
    body: AdsMaterialsBody,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """添加/换素材：body {material_ids}；优选顺序 高效>潜力>探索期 提示（settings 语义）。"""
    import ads.repo as ads_repo

    from ads.settings import pick_materials
    from ads.tables import AdCampaign, AdMaterial

    cam = _get_campaign_or_404(services, campaign_id)
    ids = body.material_ids
    with services.m5_db.session() as session:
        row = session.get(AdCampaign, campaign_id)
        row.material_ids_json = ids
        materials = [
            {
                "material_id": m.material_id,
                "evaluation": m.evaluation,
                "upload_status": m.upload_status,
                "impressions": 0,
                "gmv": 0,
            }
            for m in session.scalars(
                select(AdMaterial).where(AdMaterial.material_id.in_(ids))
            ).all()
        ]
    preferred = pick_materials(materials, limit=len(ids)) if materials else []
    preferred_ids = [m["material_id"] for m in preferred] or list(ids)
    services.audit(
        event="ads.campaign_materials",
        message=f"托管素材更新: campaign_id={campaign_id}",
        evidence={"campaign_id": campaign_id, "material_ids": ids},
        operator=user.username,
    )
    return {
        "ok": True,
        "campaign_id": campaign_id,
        "material_ids": ids,
        "preferred_order": preferred_ids,
        "note": "优选顺序：高效(efficient) > 潜力(potential) > 探索期(exploring)",
        "operator": user.username,
    }


# ---------------------------------------------------------------- 报表聚合


@router.get("/report")
def ads_report(
    days: int = Query(7, ge=1, le=90),
    services: Services = Depends(get_services),
) -> dict:
    """报表聚合：按日 spend/gmv/subsidy/impressions（金额 元 float）。"""
    from datetime import datetime, timedelta, timezone

    from ads.tables import AdReportSnapshot

    since = datetime.now(timezone.utc) - timedelta(days=days)
    with services.m5_db.session() as session:
        rows = list(
            session.scalars(
                select(AdReportSnapshot).where(AdReportSnapshot.recorded_at >= since)
            ).all()
        )
    by_date: dict[str, dict[str, Any]] = {}
    for r in rows:
        day = iso_z(r.recorded_at)[:10] if r.recorded_at else "unknown"
        agg = by_date.setdefault(
            day,
            {
                "date": day,
                "impressions": 0,
                "spend_fen": 0,
                "gmv_fen": 0,
                "subsidy_fen": 0,
                "campaign_ids": set(),
            },
        )
        agg["impressions"] += r.impressions or 0
        agg["spend_fen"] += r.spend or 0
        agg["gmv_fen"] += r.gmv or 0
        agg["subsidy_fen"] += r.platform_subsidy or 0
        agg["campaign_ids"].add(r.campaign_id)
    items = [
        {
            "date": agg["date"],
            "impressions": agg["impressions"],
            "spend_yuan": round(agg["spend_fen"] / 100.0, 2),
            "gmv_yuan": round(agg["gmv_fen"] / 100.0, 2),
            "subsidy_yuan": round(agg["subsidy_fen"] / 100.0, 2),
            "campaign_count": len(agg["campaign_ids"]),
        }
        for agg in sorted(by_date.values(), key=lambda x: x["date"], reverse=True)
    ]
    return {"days": days, "total": len(items), "items": items}
