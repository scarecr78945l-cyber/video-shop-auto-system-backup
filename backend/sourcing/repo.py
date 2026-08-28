"""选品模块数据访问层（账本/商品/指纹/配置）。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import tables as T
from .models import (
    BoardRunState,
    ComplianceState,
    ProductCandidate,
    Quote,
    ScoreBreakdown,
    SourceItem,
    ensure_aware,
    utcnow,
)


# ---------------------------------------------------------------- 配置
def get_config_value(session: Session, key: str, default: Any = None) -> Any:
    row = session.get(T.AppConfigRow, key)
    if row is None:
        return default
    return row.value


def set_config_value(session: Session, key: str, value: Any, description: str = "") -> None:
    row = session.get(T.AppConfigRow, key)
    if row is None:
        row = T.AppConfigRow(key=key, value=value, description=description)
        session.add(row)
    else:
        row.value = value
        if description:
            row.description = description


# ---------------------------------------------------------------- 账本
def load_board_state(session: Session, source: str, board: str) -> BoardRunState:
    row = session.execute(
        select(T.SourceBoardState).where(
            T.SourceBoardState.source == source, T.SourceBoardState.board == board
        )
    ).scalar_one_or_none()
    if row is None:
        return BoardRunState(source=source, board=board)
    return BoardRunState(
        source=row.source,
        board=row.board,
        cursor=row.cursor,
        last_item_id=row.last_item_id,
        next_run_at=ensure_aware(row.next_run_at),
        completed_for_date=row.completed_for_date,
        empty_run_count=row.empty_run_count,
        throttle_level=row.throttle_level,
        consecutive_failures=row.consecutive_failures,
        status=row.status,
        last_error=row.last_error,
        updated_at=ensure_aware(row.updated_at),
    )


def save_board_state(session: Session, state: BoardRunState) -> None:
    row = session.execute(
        select(T.SourceBoardState).where(
            T.SourceBoardState.source == state.source,
            T.SourceBoardState.board == state.board,
        )
    ).scalar_one_or_none()
    if row is None:
        row = T.SourceBoardState(source=state.source, board=state.board)
        session.add(row)
    row.cursor = state.cursor
    row.last_item_id = state.last_item_id
    row.next_run_at = state.next_run_at
    row.completed_for_date = state.completed_for_date
    row.empty_run_count = state.empty_run_count
    row.throttle_level = state.throttle_level
    row.consecutive_failures = state.consecutive_failures
    row.status = state.status
    row.last_error = state.last_error
    row.updated_at = utcnow()


def get_platform_state(session: Session, source: str) -> T.SourcePlatformState:
    row = session.execute(
        select(T.SourcePlatformState).where(T.SourcePlatformState.source == source)
    ).scalar_one_or_none()
    if row is None:
        row = T.SourcePlatformState(source=source)
        session.add(row)
        session.flush()
    # SQLite 丢 tzinfo，统一补 UTC，避免 naive/aware 比较报错
    row.paused_until = ensure_aware(row.paused_until)
    return row


def record_run(
    session: Session,
    source: str,
    board: str,
    item_count: int,
    ok: bool,
    error: str = "",
) -> int:
    run = T.SourceRun(
        source=source, board=board, item_count=item_count, ok=ok, error=error
    )
    session.add(run)
    session.flush()
    return run.id


def record_events(session: Session, run_id: int, items: list[SourceItem]) -> None:
    for it in items:
        session.add(
            T.SourceCollectionEvent(
                run_id=run_id,
                source=it.source,
                board=it.board,
                platform_item_id=it.platform_item_id,
                title=it.title,
                price=it.price,
                sales=it.sales,
                rank=it.rank,
                raw_json=it.raw,
            )
        )


# ---------------------------------------------------------------- 指纹与库
def claim_fingerprint(
    session: Session, fingerprint: str, claimant: str = "pipeline"
) -> bool:
    """原子认领指纹；已存在则返回 False（防并发重复入库）。"""
    if session.get(T.ProductFingerprintClaim, fingerprint) is not None:
        return False
    session.add(
        T.ProductFingerprintClaim(fingerprint=fingerprint, claimant=claimant)
    )
    session.flush()
    return True


def library_lookup(
    session: Session, fingerprint: str, image_phash: str
) -> Optional[T.ProductLibrary]:
    row = session.get(T.ProductLibrary, fingerprint)
    if row is not None:
        return row
    if image_phash:
        row = session.execute(
            select(T.ProductLibrary).where(T.ProductLibrary.image_phash == image_phash)
        ).scalar_one_or_none()
    return row


def upsert_library(session: Session, candidate: ProductCandidate) -> T.ProductLibrary:
    row = session.get(T.ProductLibrary, candidate.fingerprint)
    if row is None:
        row = T.ProductLibrary(
            fingerprint=candidate.fingerprint,
            image_phash=candidate.image_phash,
            normalized_title=candidate.sanitized_title,
            category=candidate.category,
            source_count=1,
        )
        session.add(row)
    else:
        row.image_phash = candidate.image_phash or row.image_phash
        row.normalized_title = candidate.sanitized_title or row.normalized_title
        row.source_count += 1
    row.last_seen_at = utcnow()
    return row


# ---------------------------------------------------------------- 商品
def upsert_product(session: Session, candidate: ProductCandidate) -> T.Product:
    row = session.execute(
        select(T.Product).where(T.Product.fingerprint == candidate.fingerprint)
    ).scalar_one_or_none()
    if row is None:
        row = T.Product(fingerprint=candidate.fingerprint)
        session.add(row)
    row.image_phash = candidate.image_phash
    row.title = candidate.title
    row.sanitized_title = candidate.sanitized_title
    row.category = candidate.category
    row.platform_price = candidate.platform_price
    row.real_cost = candidate.real_cost
    row.suggested_price = candidate.suggested_price
    row.profit_margin = candidate.profit_margin
    row.sales = candidate.sales
    row.rank_best = candidate.rank_best
    row.board_count = candidate.board_count
    row.score = candidate.score.total
    row.score_breakdown = candidate.score.model_dump(mode="json")
    row.compliance_state = candidate.compliance.state.value
    row.compliance_reasons = candidate.compliance.reasons
    row.state = candidate.state
    row.return_rate = candidate.return_rate
    row.supplier_count = candidate.supplier_count
    row.ad_conversion = candidate.ad_conversion
    session.flush()
    return row


def save_evidence(session: Session, product_id: int, items: list[SourceItem]) -> None:
    for it in items:
        session.add(
            T.ProductSourceEvidence(
                product_id=product_id,
                source=it.source,
                board=it.board,
                platform_item_id=it.platform_item_id,
                title=it.title,
                price=it.price,
                sales=it.sales,
                rank=it.rank,
                image_urls=it.image_urls,
                raw_json=it.raw,
            )
        )


def save_quotes(session: Session, product_id: int, quotes: list[Quote]) -> None:
    for q in quotes:
        supplier_id = None
        sup = session.execute(
            select(T.Supplier).where(T.Supplier.name == q.supplier_name)
        ).scalar_one_or_none()
        if sup is None:
            sup = T.Supplier(name=q.supplier_name, url=q.raw_url)
            session.add(sup)
            session.flush()
        supplier_id = sup.id
        session.add(
            T.Sku(
                product_id=product_id,
                supplier_id=supplier_id,
                supplier_name=q.supplier_name,
                sku_name=q.sku_name,
                unit_cost=q.unit_cost,
                min_order=q.min_order,
                freight=q.freight,
                raw_url=q.raw_url,
            )
        )


# ---------------------------------------------------------------- 查询
def list_pool(
    session: Session, limit: int = 100, state: str = "pool"
) -> list[T.Product]:
    return list(
        session.execute(
            select(T.Product)
            .where(T.Product.state == state)
            .order_by(T.Product.score.desc())
            .limit(limit)
        ).scalars()
    )


def pool_summary(session: Session, limit: int = 20) -> str:
    rows = list_pool(session, limit=limit)
    lines = [f"{'#':>3} {'得分':>5} {'类目':<8} {'标题':<40} 状态"]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i:>3} {r.score:5.1f} {r.category:<8} {r.sanitized_title[:38]:<40} {r.state}"
        )
    return "\n".join(lines)


def dump_product(session: Session, product_id: int) -> dict[str, Any]:
    row = session.get(T.Product, product_id)
    if row is None:
        return {"error": f"product {product_id} not found"}
    data: dict[str, Any] = {}
    for c in T.Product.__table__.columns:
        v = getattr(row, c.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        data[c.name] = v
    data["score_breakdown"] = json.dumps(data.get("score_breakdown"), ensure_ascii=False)
    data["compliance_reasons"] = json.dumps(data.get("compliance_reasons"), ensure_ascii=False)
    data["ad_conversion"] = json.dumps(data.get("ad_conversion"), ensure_ascii=False)
    return data
