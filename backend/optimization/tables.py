"""M3 自动素材优化模块 · ORM 表（opt_* 前缀，对齐 database/README.md 规划）。

一模块一库铁律：本模块只操作 m3-optimization.db；共享表（workflow_jobs /
app_config / logs / ai_generation_logs）归 M0 只读；M2 assets / M1 products
只读引用，不建外键约束（跨库不建 FK）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .models import utcnow


class Base(DeclarativeBase):
    pass


class OptTemplate(Base):
    """二创模板参数（按类目，可配置 + 按类目重训练）。"""

    __tablename__ = "opt_templates"

    template_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    template_name: Mapped[str] = mapped_column(String(120))
    opening_seconds: Mapped[int] = mapped_column(Integer, default=3)
    subtitle_style: Mapped[dict] = mapped_column(JSON, default=dict)
    badge_position: Mapped[str] = mapped_column(String(30), default="top-right")
    bgm_loudness: Mapped[float] = mapped_column(Float, default=-16.0)
    cut_count: Mapped[int] = mapped_column(Integer, default=3)
    params_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")
    stats_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OptVideoVariant(Base):
    """视频二创版本（A/B 结构核心：(product_id, variant_no) 唯一）。"""

    __tablename__ = "opt_video_variants"
    __table_args__ = (UniqueConstraint("product_id", "variant_no", name="uq_variant"),)

    variant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(64), index=True)  # M1 products（只读引用）
    source_asset_id: Mapped[str] = mapped_column(String(64))         # M2 assets（只读引用）
    variant_no: Mapped[int] = mapped_column(Integer, default=1)
    template_id: Mapped[str] = mapped_column(String(64), default="")
    copywrite_ids: Mapped[list] = mapped_column(JSON, default=list)
    template_params_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    file_path: Mapped[str] = mapped_column(String(500), default="")
    spec_check_json: Mapped[dict] = mapped_column(JSON, default=dict)  # ffprobe 校验结果
    spec_ok: Mapped[bool] = mapped_column(Integer, default=0)
    compliance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    upload_status: Mapped[str] = mapped_column(String(20), default="local")
    platform_material_id: Mapped[str] = mapped_column(String(120), default="")
    evaluation: Mapped[str] = mapped_column(String(20), default="exploring")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OptImageBatch(Base):
    """生图批次（REC-001：图片资产域归 M3，自建 opt_image_*）。"""

    __tablename__ = "opt_image_batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(64), index=True)
    image_type: Mapped[str] = mapped_column(String(20))  # main/detail
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict)  # Kimi 规划快照
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    gate_json: Mapped[dict] = mapped_column(JSON, default=dict)  # 质量门禁统计
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OptImage(Base):
    """主图/详情图资产。"""

    __tablename__ = "opt_images"
    __table_args__ = (
        UniqueConstraint("batch_id", "image_type", "variant_no", name="uq_image"),
    )

    image_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    product_id: Mapped[str] = mapped_column(String(64), index=True)
    image_type: Mapped[str] = mapped_column(String(20))
    variant_no: Mapped[int] = mapped_column(Integer, default=1)  # 主图 1..5
    file_path: Mapped[str] = mapped_column(String(500), default="")
    phash: Mapped[str] = mapped_column(String(64), default="", index=True)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    quality_json: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_ok: Mapped[bool] = mapped_column(Integer, default=0)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    category_memory_key: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OptCopywrite(Base):
    """文案（标题/口播稿/投放文案/角标）。"""

    __tablename__ = "opt_copywrites"
    __table_args__ = (
        UniqueConstraint("product_id", "copy_type", "variant_no", name="uq_copy"),
    )

    copywrite_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(64), index=True)
    copy_type: Mapped[str] = mapped_column(String(20))  # title/script/ad/badge
    variant_no: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text)
    char_len: Mapped[int] = mapped_column(Integer, default=0)
    sku_basis_json: Mapped[dict] = mapped_column(JSON, default=dict)
    compliance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    source: Mapped[str] = mapped_column(String(20), default="llm")  # llm/rule_fallback
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OptReviewRecord(Base):
    """审核记录（闸门流水：rule/evaluate/manual）。"""

    __tablename__ = "opt_review_records"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20))  # video/image/copywrite
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    gate_type: Mapped[str] = mapped_column(String(20))    # rule/evaluate/manual
    result: Mapped[str] = mapped_column(String(20))       # pass/reject/manual_review
    reasons_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewer: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("idx_opt_review_target", OptReviewRecord.target_type, OptReviewRecord.target_id)


class OptCategoryMemory(Base):
    """类目记忆：按类目累积人工通过/平台拒审经验，调整生图/模板策略。"""

    __tablename__ = "opt_category_memory"

    category: Mapped[str] = mapped_column(String(80), primary_key=True)
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    reject_count: Mapped[int] = mapped_column(Integer, default=0)
    reject_reasons_json: Mapped[dict] = mapped_column(JSON, default=dict)
    image_strategy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    template_stats_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OptEvaluationFeedback(Base):
    """评估回写（A/B 闭环核心：(variant_id, report_date) 唯一）。"""

    __tablename__ = "opt_evaluation_feedback"
    __table_args__ = (
        UniqueConstraint("variant_id", "report_date", name="uq_feedback"),
    )

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    variant_id: Mapped[str] = mapped_column(String(64), index=True)
    platform_material_id: Mapped[str] = mapped_column(String(120), default="")
    report_date: Mapped[str] = mapped_column(String(20))  # UTC YYYY-MM-DD
    exposure: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    spend: Mapped[float] = mapped_column(Float, default=0.0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    roi: Mapped[float] = mapped_column(Float, default=0.0)
    diagnosis_json: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    evaluation: Mapped[str] = mapped_column(String(20), default="exploring")
    stale: Mapped[bool] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OptUploadRecord(Base):
    """小店素材库上传记录（REC-002：api|ui|semi 双轨）。"""

    __tablename__ = "opt_upload_records"

    upload_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20))  # video/image
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    batch_no: Mapped[int] = mapped_column(Integer, default=1)
    mode: Mapped[str] = mapped_column(String(20), default="api")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_code: Mapped[str] = mapped_column(String(40), default="")  # 复用错误码表
    platform_material_id: Mapped[str] = mapped_column(String(120), default="")
    platform_evaluation: Mapped[str] = mapped_column(String(20), default="")
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
