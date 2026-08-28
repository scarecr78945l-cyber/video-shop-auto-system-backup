"""M5 自动小店投放（商品托管）模块 ORM 表（对齐数据字典与 DDL 规划 v0.1）。

表前缀 ad_*（宪法第 4 节）：ad_campaigns / ad_runs / ad_report_snapshots /
ad_account_states / ad_materials。
口径（总控 data-audit DA-001）：金额一律「分」（int）；时间一律
DateTime(timezone=True) 默认 utcnow，时间戳字段名后缀 `_at`；主键自增 INTEGER。
枚举存储英文（中文仅注释/展示映射，与 M2 evaluation 口径完全一致）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .models import utcnow


class Base(DeclarativeBase):
    pass


class AdCampaign(Base):
    """托管投放计划：一个托管计划 = 1 商品 + 1 组投放设置。

    status 枚举：pending(待托管)/active(托管中)/paused(已暂停)/
    not_eligible(不可投放)/ended(已结束)。
    target_type 枚举：roi(成交ROI)/net_roi(净成交ROI)/goods(商品成交)。
    diagnosis 枚举：excellent(优秀)/good(良好)/optimize_1(1项待优化)/optimize_n(N项待优化)。
    """

    __tablename__ = "ad_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)  # 与 M1 products.id 对齐（仅销售中商品）
    ad_mode: Mapped[str] = mapped_column(String(30), default="goods_trust")  # 商品托管（本项目唯一模式）
    target_type: Mapped[str] = mapped_column(String(30), default="roi")  # roi/net_roi/goods
    target_roi: Mapped[float] = mapped_column(Float, default=2.00)  # 默认取系统推荐，可配置覆盖
    material_ids_json: Mapped[list] = mapped_column(JSON, default=list)  # 素材库ID列表（含视频号形象）
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)  # 对齐后台投放管理列表
    diagnosis: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 智能诊断回读值
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 批量托管批次
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AdRun(Base):
    """托管执行记录：单次执行（复用 WorkflowJob 机制：租约/错误分类/断点）。

    status 枚举：running/success/failed/blocked。
    error_code 复用 09 码表：VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/
    TIMEOUT/NO_MATCH/PLATFORM_REJECT/UNEXPECTED/page_changed。
    """

    __tablename__ = "ad_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)  # 第几次尝试
    status: Mapped[str] = mapped_column(String(30), default="running")  # running/success/failed/blocked
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)  # 09 码表
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)  # 操作留痕（截图路径/选择器/耗时/URL，脱敏）
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)  # 执行进程标识
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # 租约 45min 过期回收
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 批次号（≤50/批）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdReportSnapshot(Base):
    """投放报表快照：定时回读投放列表（幂等关键）。

    (campaign_id, recorded_at) 唯一约束 uq_snapshot_campaign_time：
    同周期仅保留最新快照。金额字段一律分（int）。
    """

    __tablename__ = "ad_report_snapshots"
    __table_args__ = (
        UniqueConstraint("campaign_id", "recorded_at", name="uq_snapshot_campaign_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)  # 回读时间
    impressions: Mapped[int] = mapped_column(Integer, default=0)  # 商品曝光数（次）
    spend: Mapped[int] = mapped_column(Integer, default=0)  # 花费（分）
    gmv: Mapped[int] = mapped_column(Integer, default=0)  # 成交金额（分）
    platform_subsidy: Mapped[int] = mapped_column(Integer, default=0)  # 平台补贴（分），补贴后ROI单独统计
    diagnosis: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 智能诊断
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 投放列表状态


class AdAccountState(Base):
    """投放账户状态（仿 SourcePlatformState）：单例语义。

    status 枚举：active(正常)/risk_control(风控)/waiting_login(等待登录)/
    waiting_verification(等待验证)/paused(暂停)。
    throttle_level：0~4 节流级（间隔 ×1/2/4/8/16）。
    """

    __tablename__ = "ad_account_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)  # 可用余额（分）
    status: Mapped[str] = mapped_column(String(30), default="active")  # active/risk_control/waiting_login/waiting_verification/paused
    throttle_level: Mapped[int] = mapped_column(Integer, default=0)  # 0~4 节流级
    paused_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # 暂停截止（人工接管后断点续跑）
    pause_reason: Mapped[str] = mapped_column(String(200), default="")  # 暂停原因
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AdMaterial(Base):
    """素材库视频（与 M2/M3 assets 打通，评估标签回流）。

    material_id 唯一。evaluation 枚举：exploring(探索期)/efficient(高效)/potential(潜力)
    —— 与 M2 materials/config.py EVALUATION_VALUES 完全一致。
    upload_status 枚举：uploading(上传中)/uploaded(已上传)/reviewing(审核中)/
    approved(审核通过)/rejected(审核不通过)/corrupt(源文件损坏)。
    """

    __tablename__ = "ad_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[str] = mapped_column(String(120), unique=True)  # 小店素材库ID（后台素材库）
    asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 关联 M2/M3 assets.id（data-audit 核对）
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 本地路径（环境变量根目录下）
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)  # 秒（5~300s）
    resolution: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 如 1080x1920（9:16，≥720×1280）
    evaluation: Mapped[str] = mapped_column(String(30), default="exploring", index=True)  # exploring/efficient/potential（投放效果回流更新）
    upload_status: Mapped[str] = mapped_column(String(30), default="reviewing")  # uploading/uploaded/reviewing/approved/rejected/corrupt
    platform_material_id: Mapped[str | None] = mapped_column(String(120), nullable=True)  # 平台侧素材ID
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
