"""选品路由（M1 域，sourcing repo/CLI 聚合）。

- GET  /api/products              商品池列表（score 降序；过滤 category/state/score 区间；
                                   含 score_breakdown 摘要、compliance 三态）
- GET  /api/products/{product_id} 商品详情（五维 raw/weight/weighted/reasons + quotes
                                   + source_evidence，证据脱敏）
- GET  /api/sourcing/status       调度状态（各源账本 next_run_at/throttle_level/
                                   consecutive_failures/status 含 waiting_*）
- POST /api/sourcing/gate-confirm 选品复核闸门（manual_review → pool，对齐 CLI
                                   gate-confirm；记录操作人）
- GET  /api/sourcing/report       选品周报（复用 sourcing/report.py）
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

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
    redact_urls_in,
)
from ..schemas import GateConfirmBody
from ..services import Services

router = APIRouter(prefix="/api", tags=["m1-sourcing"])


def _ad_conversion_out(raw: Any) -> dict[str, Any]:
    """ad_conversion 输出：roi/sales 等比值与原样透传；sales_amount（分）→ 元。

    M5 C-2 契约 sales_amount 单位为分（int）——API 对外禁止输出分（DA-001），
    换算为 sales_amount_yuan（round 2 位）；其余键原样保留。
    """
    data = dict(json_safe(raw) or {})
    sales_amount = data.pop("sales_amount", None)
    if sales_amount is not None:
        data["sales_amount_yuan"] = cents_to_yuan(sales_amount)
    return data


# ---------------------------------------------------------------- 商品池


def _product_summary(row) -> dict[str, Any]:
    """商品池条目：M1 元字段直接透传（不外发分）；score_breakdown 摘要 + compliance 三态。"""
    return {
        "id": row.id,
        "fingerprint": row.fingerprint,
        "image_phash": row.image_phash,
        "title": row.title or "",
        "sanitized_title": row.sanitized_title or "",
        "category": row.category or "",
        "platform_price": row.platform_price,
        "real_cost": row.real_cost,
        "suggested_price": row.suggested_price,
        "profit_margin": row.profit_margin,
        "sales": row.sales or 0,
        "rank_best": row.rank_best or 0,
        "board_count": row.board_count or 0,
        "score": row.score or 0.0,
        "score_breakdown": json_safe(row.score_breakdown),
        "compliance": {
            "state": row.compliance_state or "candidate",
            "reasons": json_safe(row.compliance_reasons) or [],
        },
        "state": row.state or "pool",
        "supplier_count": row.supplier_count or 0,
        "return_rate": row.return_rate,
        "ad_conversion": _ad_conversion_out(row.ad_conversion),
        "created_at": iso_z(row.created_at),
    }


@router.get("/products")
def list_products(
    category: Optional[str] = None,
    state: Optional[str] = None,
    compliance: Optional[str] = None,
    min_score: Optional[float] = Query(None, ge=0, le=100),
    max_score: Optional[float] = Query(None, ge=0, le=100),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    services: Services = Depends(get_services),
) -> dict:
    """商品池列表：score 降序；过滤 category/state/compliance/score 区间。"""
    from sqlalchemy import func as sa_func

    from sourcing.tables import Product

    with services.sourcing_db.session() as session:
        filters = []
        if category:
            filters.append(Product.category == category)
        if state:
            filters.append(Product.state == state)
        if compliance:
            filters.append(Product.compliance_state == compliance)
        if min_score is not None:
            filters.append(Product.score >= min_score)
        if max_score is not None:
            filters.append(Product.score <= max_score)
        total = session.execute(
            sa_func.count(Product.id).select().where(*filters)
        ).scalar_one()
        stmt = select(Product).where(*filters).order_by(Product.score.desc())
        rows = list(session.scalars(stmt.offset(offset).limit(limit)).all())
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_product_summary(r) for r in rows],
    }


@router.get("/products/{product_id}")
def product_detail(
    product_id: int, services: Services = Depends(get_services)
) -> dict:
    """商品详情：五维打分（raw/weight/weighted/reasons）+ quotes + source_evidence（脱敏）。"""
    from sourcing.tables import Product, ProductSourceEvidence, Sku

    with services.sourcing_db.session() as session:
        row = session.get(Product, product_id)
        if row is None:
            raise not_found(f"商品 {product_id} 不存在")
        skus = list(
            session.scalars(
                select(Sku).where(Sku.product_id == product_id).order_by(Sku.id)
            ).all()
        )
        evidence = list(
            session.scalars(
                select(ProductSourceEvidence)
                .where(ProductSourceEvidence.product_id == product_id)
                .order_by(ProductSourceEvidence.id)
            ).all()
        )
    data = _product_summary(row)
    data["quotes"] = [
        {
            "id": s.id,
            "supplier_name": s.supplier_name or "",
            "sku_name": s.sku_name or "",
            "unit_cost": s.unit_cost,
            "min_order": s.min_order or 1,
            "freight": s.freight or 0.0,
            "raw_url": redact_urls_in(s.raw_url or ""),
            "quoted_at": iso_z(s.quoted_at),
        }
        for s in skus
    ]
    data["source_evidence"] = [
        {
            "id": e.id,
            "source": e.source,
            "board": e.board,
            "platform_item_id": e.platform_item_id,
            "title": e.title or "",
            "price": e.price,
            "sales": e.sales or 0,
            "rank": e.rank or 0,
            "image_urls": redact_urls_in(e.image_urls or []),
            "raw": redact_value(e.raw_json or {}),
            "collected_at": iso_z(e.collected_at),
        }
        for e in evidence
    ]
    return data


# ---------------------------------------------------------------- 调度状态


@router.get("/sourcing/status")
def sourcing_status(services: Services = Depends(get_services)) -> dict:
    """选品调度状态：各源账本 + 平台级风控状态。"""
    from sourcing.tables import SourceBoardState, SourcePlatformState

    with services.sourcing_db.session() as session:
        boards = list(session.scalars(select(SourceBoardState)).all())
        platforms = list(session.scalars(select(SourcePlatformState)).all())
    return {
        "boards": [
            {
                "id": b.id,
                "source": b.source,
                "board": b.board,
                "status": b.status or "active",
                "cursor": b.cursor,
                "last_item_id": b.last_item_id,
                "next_run_at": iso_z(b.next_run_at),
                "completed_for_date": b.completed_for_date,
                "empty_run_count": b.empty_run_count or 0,
                "throttle_level": b.throttle_level or 0,
                "consecutive_failures": b.consecutive_failures or 0,
                "last_error": (b.last_error or "")[:200],
                "updated_at": iso_z(b.updated_at),
            }
            for b in boards
        ],
        "platforms": [
            {
                "id": p.id,
                "source": p.source,
                "status": p.status or "active",
                "consecutive_failures": p.consecutive_failures or 0,
                "paused_until": iso_z(p.paused_until),
                "reason": (p.reason or "")[:200],
                "updated_at": iso_z(p.updated_at),
            }
            for p in platforms
        ],
    }


# ---------------------------------------------------------------- 复核闸门


@router.post("/sourcing/gate-confirm")
def gate_confirm(
    body: GateConfirmBody,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """选品复核闸门：manual_review（或任意非 pool）→ pool；记录操作人。"""
    from sourcing.tables import Product

    with services.sourcing_db.session() as session:
        row = session.get(Product, body.product_id)
        if row is None:
            raise not_found(f"商品 {body.product_id} 不存在")
        if row.state == "pool":
            raise invalid_state(f"商品 {body.product_id} 已在池中")
        row.state = "pool"
        result = {
            "product_id": row.id,
            "title": row.sanitized_title or row.title,
            "state": row.state,
            "operator": user.username,
        }
    services.audit(
        event="sourcing.gate_confirm",
        message=f"选品复核确认入池: product_id={body.product_id}",
        evidence={"product_id": body.product_id},
        operator=user.username,
    )
    return {"ok": True, **result}


# ---------------------------------------------------------------- 选品周报


@router.get("/sourcing/report")
def sourcing_report(
    days: int = Query(7, ge=1, le=90),
    services: Services = Depends(get_services),
) -> dict:
    """选品周报：来源/错误/漏斗聚合（复用 sourcing/report.py 统计口径）。"""
    from sourcing.report import SourcingReport

    report = SourcingReport(services.sourcing_db)
    return report.weekly(days=days)
