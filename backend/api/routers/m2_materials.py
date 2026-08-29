"""素材路由（M2 域，materials repo）。

- GET  /api/assets                 素材库列表（过滤 asset_type/source_platform/
                                    relevance_status/upload_status/evaluation/
                                    compliance_status + 分页）
- GET  /api/assets/{asset_id}      素材详情（规格字段 + 双去重指纹 + 评估标签）
- POST /api/assets/{asset_id}/relevance-confirm
                                  素材相关性人工确认（multi_style → 确认目标款，
                                  调 M2 RelevanceGateService 语义；记录操作人）
- GET  /api/assets/uploads        上传记录（upload_status 追踪）
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from ..auth import AuthUser
from ..deps import get_current_user, get_services
from ..errors import ApiError, iso_z, json_safe, not_found, redact_urls_in, redact_value
from ..schemas import RelevanceConfirmBody
from ..services import Services

router = APIRouter(prefix="/api", tags=["m2-materials"])


def _asset_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "asset_type": row.asset_type,
        "source_platform": row.source_platform,
        "source_url": redact_urls_in(row.source_url or ""),
        "source_author": row.source_author,
        "md5": row.md5,
        "phash": row.phash,
        "file_path": row.file_path,
        "duration": row.duration,
        "resolution": row.resolution,
        "size": row.size,
        "tags_json": json_safe(row.tags_json),
        "heat_score": row.heat_score,
        "evaluation": row.evaluation,
        "upload_status": row.upload_status,
        "platform_material_id": row.platform_material_id,
        "compliance_status": row.compliance_status,
        "relevance_status": row.relevance_status,
        "derivation_note": row.derivation_note,
        "created_at": iso_z(row.created_at),
        "updated_at": iso_z(row.updated_at),
    }


@router.get("/assets")
def list_assets(
    asset_type: Optional[str] = None,
    source_platform: Optional[str] = None,
    relevance_status: Optional[str] = None,
    upload_status: Optional[str] = None,
    evaluation: Optional[str] = None,
    compliance_status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    services: Services = Depends(get_services),
) -> dict:
    """素材库列表：多条件过滤 + 分页（id 降序）。"""
    from materials.tables import AssetItem

    with services.materials_db.session() as session:
        filters = []
        if asset_type:
            filters.append(AssetItem.asset_type == asset_type)
        if source_platform:
            filters.append(AssetItem.source_platform == source_platform)
        if relevance_status:
            filters.append(AssetItem.relevance_status == relevance_status)
        if upload_status:
            filters.append(AssetItem.upload_status == upload_status)
        if evaluation:
            filters.append(AssetItem.evaluation == evaluation)
        if compliance_status:
            filters.append(AssetItem.compliance_status == compliance_status)
        total = session.execute(
            func.count(AssetItem.id).select().where(*filters)
        ).scalar_one()
        rows = list(
            session.scalars(
                select(AssetItem)
                .where(*filters)
                .order_by(AssetItem.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_asset_to_dict(r) for r in rows],
    }


@router.get("/assets/uploads")
def asset_uploads(
    status: Optional[str] = None,
    asset_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    services: Services = Depends(get_services),
) -> dict:
    """上传记录：asset_uploads 台账（upload_status 追踪，evidence 脱敏）。"""
    from materials.tables import AssetUpload

    with services.materials_db.session() as session:
        filters = []
        if status:
            filters.append(AssetUpload.status == status)
        if asset_id is not None:
            filters.append(AssetUpload.asset_id == asset_id)
        total = session.execute(
            func.count(AssetUpload.id).select().where(*filters)
        ).scalar_one()
        rows = list(
            session.scalars(
                select(AssetUpload)
                .where(*filters)
                .order_by(AssetUpload.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "asset_id": r.asset_id,
                "attempt": r.attempt,
                "status": r.status,
                "platform_material_id": r.platform_material_id,
                "error_code": r.error_code,
                "evidence": redact_value(json_safe(r.evidence_json)),
                "created_at": iso_z(r.created_at),
                "updated_at": iso_z(r.updated_at),
            }
            for r in rows
        ],
    }


@router.get("/assets/{asset_id}")
def asset_detail(asset_id: int, services: Services = Depends(get_services)) -> dict:
    """素材详情：规格字段 + 双去重指纹 + 评估标签。"""
    repo = services.materials_repo
    row = repo.get_asset(asset_id)
    if row is None:
        raise not_found(f"素材 {asset_id} 不存在")
    out = dict(row)
    out["source_url"] = redact_urls_in(out.get("source_url") or "")
    out["tags_json"] = json_safe(out.get("tags_json"))
    out["created_at"] = iso_z(out.get("created_at"))
    out["updated_at"] = iso_z(out.get("updated_at"))
    return out


@router.post("/assets/{asset_id}/relevance-confirm")
def relevance_confirm(
    asset_id: int,
    body: RelevanceConfirmBody,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """素材相关性人工确认：decision ∈ pass/reject/manual_review（M3 gate.result 口径）。

    pass → relevance_status=passed（放行进询价/上架链）；reject → failed；
    manual_review → manual_review。调 M2 RelevanceGateService（幂等，结构化返回）。
    """
    service = services.relevance_gate_service
    result = service.receive_relevance(
        asset_id,
        body.decision,
        evidence={"operator": user.username, "source_agent": "m6-api"},
        source_agent="m6-api",
    )
    if not result.get("ok"):
        raise ApiError(
            status_code=404 if result.get("code") == "NO_MATCH" else 400,
            code=result.get("code", "UNEXPECTED"),
            message=result.get("reason", "相关性确认失败"),
        )
    services.audit(
        event="materials.relevance_confirm",
        message=f"素材相关性人工确认: asset_id={asset_id} decision={body.decision}",
        evidence={"asset_id": asset_id, "decision": body.decision},
        operator=user.username,
    )
    return {"ok": True, **{k: v for k, v in result.items() if k != "ok"}}
