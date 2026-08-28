"""M4 自动上架模块 ORM 表（严格对齐 _management/modules/m4-listing/database/README.md DDL v0）。

7 表：listing_tasks / listing_spus / listing_skus / listing_upload_assets /
listing_op_logs / listing_audit_records / listing_quota_states。
通用约定：时间戳列一律 `_at` 后缀存 TEXT（ISO8601 UTC 文本）；金额单位一律“分”；
JSON 字段统一存 TEXT（SQLite 无原生 JSON 类型，PostgreSQL 迁移为 jsonb）。
"""

from __future__ import annotations

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ListingTaskRow(Base):
    """上架任务（状态机主表）。"""

    __tablename__ = "listing_tasks"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "stage", "generation_version",
            name="uq_listing_task_identity",  # 幂等防重复入队
        ),
        Index("idx_listing_tasks_status", "status"),
        Index("idx_listing_tasks_product", "product_id"),
    )

    task_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_version: Mapped[str] = mapped_column(String(80), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False, default="listing_upload")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    gate_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    platform_spu_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_link: Mapped[str | None] = mapped_column(Text, nullable=True)  # 验证通过前为空（R22）
    link_verified_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reject_reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ListingSpuRow(Base):
    """SPU 平台映射。"""

    __tablename__ = "listing_spus"
    __table_args__ = (Index("idx_listing_spus_task", "task_id"),)

    spu_id: Mapped[str] = mapped_column(String(120), primary_key=True)  # 平台 SPU ID
    task_id: Mapped[str] = mapped_column(
        ForeignKey("listing_tasks.task_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    qualification: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 摘要（不含凭证原文）
    freight_template_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    purchase_limit: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON {per_user,period}
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    audit_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ListingSkuRow(Base):
    """SKU 平台映射。"""

    __tablename__ = "listing_skus"
    __table_args__ = (
        UniqueConstraint("spu_id", "product_sku_code", name="uq_listing_sku"),
    )

    sku_id: Mapped[str] = mapped_column(String(120), primary_key=True)  # 平台 SKU ID
    spu_id: Mapped[str] = mapped_column(
        ForeignKey("listing_spus.spu_id"), nullable=False
    )
    product_sku_code: Mapped[str] = mapped_column(String(120), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # 分；定价阶梯结果
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # 分；真实成本，仅入库不对外
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    purchase_limit: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON（默认每月 2 件）
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class ListingUploadAssetRow(Base):
    """上传历史（主图/详情图；与基座 upload_history 语义对齐）。"""

    __tablename__ = "listing_upload_assets"
    __table_args__ = (
        UniqueConstraint("task_id", "file_sha256", name="uq_listing_asset"),  # 上传幂等去重键
        Index("idx_listing_assets_task", "task_id"),
    )

    asset_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("listing_tasks.task_id"), nullable=False
    )
    image_asset_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 基座 image_assets.id（M3）
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_id: Mapped[str | None] = mapped_column(String(120), nullable=True)  # upload_image 返回
    usage: Mapped[str] = mapped_column(String(30), nullable=False)  # main_image / detail_image
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 主图 1–5，详情图 0
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 脱敏摘要
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ListingOpLogRow(Base):
    """微信操作日志（证据留痕；与基座 wechat_upload_logs 语义对齐）。"""

    __tablename__ = "listing_op_logs"
    __table_args__ = (
        Index("idx_listing_oplogs_task", "task_id", "created_at"),
    )

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(120), nullable=False)
    request_id: Mapped[str] = mapped_column(String(200), nullable=False)  # 幂等键
    api: Mapped[str] = mapped_column(String(60), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # request / response
    payload_digest: Mapped[str | None] = mapped_column(Text, nullable=True)  # 请求体脱敏摘要（无密钥）
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)  # WorkflowJob 错误码
    platform_code: Mapped[str | None] = mapped_column(String(40), nullable=True)  # 平台业务错误码原样
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 响应证据（敏感字段脱敏）
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ListingAuditRecordRow(Base):
    """审核记录（提交/轮询/驳回/拒审处理）。"""

    __tablename__ = "listing_audit_records"
    __table_args__ = (
        UniqueConstraint("task_id", "audit_id", name="uq_listing_audit"),
        Index("idx_listing_audits_task", "task_id"),
    )

    audit_record_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("listing_tasks.task_id"), nullable=False
    )
    audit_id: Mapped[str] = mapped_column(String(120), nullable=False)
    submit_at: Mapped[str] = mapped_column(String(40), nullable=False)
    last_query_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    audit_status: Mapped[str | None] = mapped_column(String(40), nullable=True)  # 平台原样状态
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reject_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fix_candidate: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 修复候选
    resubmit_required: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 二次门禁标志
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON


class ListingQuotaStateRow(Base):
    """接口配额状态（令牌桶 + 熔断探针）。"""

    __tablename__ = "listing_quota_states"

    api: Mapped[str] = mapped_column(String(60), primary_key=True)
    tokens: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[float] = mapped_column(Float, nullable=False)
    refill_rate: Mapped[float] = mapped_column(Float, nullable=False)  # 令牌/秒
    window_start: Mapped[str] = mapped_column(String(40), nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circuit_open_until: Mapped[str | None] = mapped_column(String(40), nullable=True)
