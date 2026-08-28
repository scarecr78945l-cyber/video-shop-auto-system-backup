"""选品模块 ORM 表（对齐方案文档 09 数据模型表清单）。

现有（复用）：source_board_states / source_platform_states /
source_collection_events / source_runs / product_source_evidence /
products / product_library / product_fingerprint_claims /
suppliers / sku / app_config
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .models import utcnow


class Base(DeclarativeBase):
    pass


class AppConfigRow(Base):
    """配置表：类目白名单/打分权重/预算上限等运行时配置（键值+JSON 值）。"""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceBoardState(Base):
    """选品账本：每（平台,榜单）的游标/节流/熔断/断点。"""

    __tablename__ = "source_board_states"
    __table_args__ = (UniqueConstraint("source", "board", name="uq_board"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    board: Mapped[str] = mapped_column(String(80))
    cursor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_item_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_for_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    empty_run_count: Mapped[int] = mapped_column(Integer, default=0)
    throttle_level: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="active")
    last_error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SourcePlatformState(Base):
    """平台级风控状态（risk_control/探针恢复/登录等待）。"""

    __tablename__ = "source_platform_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SourceRun(Base):
    """一次采集批次记录。"""

    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    board: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str] = mapped_column(Text, default="")


class SourceCollectionEvent(Base):
    """单条采集事件（证据留痕）。"""

    __tablename__ = "source_collection_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("source_runs.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    board: Mapped[str] = mapped_column(String(80))
    platform_item_id: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(500), default="")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    sales: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    """商品主表（候选/入池/上架状态全字段，核心打分以 JSON 落库）。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    image_phash: Mapped[str] = mapped_column(String(64), default="", index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    sanitized_title: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(80), default="", index=True)
    platform_price: Mapped[float] = mapped_column(Float, default=0.0)
    real_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggested_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    sales: Mapped[int] = mapped_column(Integer, default=0)
    rank_best: Mapped[int] = mapped_column(Integer, default=0)
    board_count: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    compliance_state: Mapped[str] = mapped_column(String(20), default="candidate")
    compliance_reasons: Mapped[dict] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(30), default="pool", index=True)
    return_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    supplier_count: Mapped[int] = mapped_column(Integer, default=0)
    ad_conversion: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evidence = relationship("ProductSourceEvidence", back_populates="product")


class ProductLibrary(Base):
    """商品库：归一化名称/指纹去重/历史表现。"""

    __tablename__ = "product_library"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    image_phash: Mapped[str] = mapped_column(String(64), default="", index=True)
    normalized_title: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(80), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    history: Mapped[dict] = mapped_column(JSON, default=dict)  # 历史表现/成交


class ProductFingerprintClaim(Base):
    """指纹认领（防并发重复入库，唯一约束兜底）。"""

    __tablename__ = "product_fingerprint_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    claimant: Mapped[str] = mapped_column(String(120), default="")


class ProductSourceEvidence(Base):
    """来源证据（平台+榜单+item）。"""

    __tablename__ = "product_source_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    source: Mapped[str] = mapped_column(String(40))
    board: Mapped[str] = mapped_column(String(80))
    platform_item_id: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(500), default="")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    sales: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    image_urls: Mapped[list] = mapped_column(JSON, default=list)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    product = relationship("Product", back_populates="evidence")


class Supplier(Base):
    """1688 供应商。"""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    url: Mapped[str] = mapped_column(String(500), default="")
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Sku(Base):
    """逐 SKU 成本（询价结果）。"""

    __tablename__ = "sku"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    supplier_name: Mapped[str] = mapped_column(String(200), default="")
    sku_name: Mapped[str] = mapped_column(String(300), default="")
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    min_order: Mapped[int] = mapped_column(Integer, default=1)
    freight: Mapped[float] = mapped_column(Float, default=0.0)
    raw_url: Mapped[str] = mapped_column(String(500), default="")
    quoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
