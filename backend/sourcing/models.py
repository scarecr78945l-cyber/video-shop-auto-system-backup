"""选品模块领域模型（pydantic v2）。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite 存储会丢失 tzinfo；读取时统一补 UTC（避免 naive/aware 比较报错）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ComplianceState(str, Enum):
    HARD_REJECT = "hard_reject"
    CANDIDATE = "candidate"
    MANUAL_REVIEW = "manual_review"


class SourceItem(BaseModel):
    """榜单上的原始商品条目（三源通用）。

    P2-7 对照旧系统 contracts.SourcedProduct（字段命名统一结论见 decisions.md D-10）：
      image_url      → image_urls（新系统为 list，支持图集；旧系统单 URL）
      name           → title（命名统一：title）
      source_url     → 无单字段；由 (source, board, platform_item_id) 定位，
                       原始证据保留在 raw["source_product_url"]（旧系统证据键同名）
      category       → category（一致）
      sales_rank     → rank（命名统一：rank，语义=榜单名次，0=无）
      price_range    → price（语义差异：旧系统为区间字符串如 "9.9-29.9"；
                       新系统统一为展示价 float 元，区间信息如需保留可入 raw）
    """

    source: str  # opportunities | youmi | doudian（选品三源）；alibaba/taobao（询价/素材）；kaogujia（第四源备胎，未启用）
    board: str  # 榜单名
    platform_item_id: str
    title: str
    price: float = 0.0
    sales: int = 0
    rank: int = 0
    category: str = ""
    image_urls: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=utcnow)

    @property
    def core_key(self) -> str:
        return f"{self.source}:{self.board}:{self.platform_item_id}"


class BoardRunState(BaseModel):
    """单个（平台,榜单）账本状态 —— 对应 source_board_states 表。"""

    source: str
    board: str
    cursor: Optional[str] = None
    last_item_id: Optional[str] = None
    # 默认过去时间 = 从未运行 → 立即到期
    next_run_at: datetime = Field(
        default_factory=lambda: datetime(1970, 1, 1, tzinfo=timezone.utc)
    )
    completed_for_date: Optional[str] = None
    empty_run_count: int = 0
    throttle_level: int = 0
    consecutive_failures: int = 0
    status: str = "active"  # active | risk_control | waiting_login | waiting_verification
    last_error: str = ""
    updated_at: datetime = Field(default_factory=utcnow)


class Quote(BaseModel):
    """1688 逐 SKU 真实询价结果（订单确认页读价，不下单）。

    P2-7 对照旧系统 contracts.AlibabaMatch（以图搜款匹配结果，语义为「匹配」而非「询价」；
    命名统一结论见 decisions.md D-10）：
      url                → raw_url（命名统一：raw_url，拿到真实链接才算有效）
      purchase_price     → unit_cost（命名统一：unit_cost，元）
      freight            → freight（一致）
      supplier_name      → supplier_name（一致）
      sku_summary        → sku_name（近似：旧系统汇总描述，新系统单 SKU 名）
      missing_fields     → missing_attrs（命名统一：REC-迁移-02 已用 missing_attrs 对照
                           listing-requirements.json missing_field_labels）
      旧系统独有未建模（登记 D-10，后续按需扩展）：score(匹配分)/material(材质)/
      dropshipping_supported/product_attrs/customer_service_questions/customer_service_targets/
      image_offer_candidates —— 其中 customer_service_* 归 M4 客服补参链路（C2）。
    """

    supplier_name: str
    sku_name: str
    unit_cost: float  # 单价（元）
    min_order: int = 1
    freight: float = 0.0
    raw_url: str = ""  # 拿到真实链接才算有效
    quoted_at: datetime = Field(default_factory=utcnow)
    # REC-迁移-02（C2）：商品缺失的必填上架参数（适用年龄/包装清单/重量/容量/适用场景/类别/功能等）
    # 由采集器从商品页属性区探测，M4 listing_gate attrs_complete 门禁消费；
    # 空列表 = 参数完整或无法探测（不阻断）。字段名对照 listing-requirements.json missing_field_labels。
    missing_attrs: list[str] = Field(default_factory=list)

    @property
    def effective_cost(self) -> float:
        return self.unit_cost


class ComplianceResult(BaseModel):
    state: ComplianceState
    reasons: list[str] = Field(default_factory=list)
    sanitized_title: str = ""
    category: str = ""
    matched_rules: list[str] = Field(default_factory=list)


class ScoreDimension(BaseModel):
    key: str
    label: str
    raw: float = 0.0
    weight: float = 0.0  # 归一化后权重
    weighted: float = 0.0
    active: bool = True
    reasons: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    total: float = 0.0
    dimensions: dict[str, ScoreDimension] = Field(default_factory=dict)
    rank: int = 0  # 排序名次（TopN 阶段回填）
    note: str = ""

    def summary(self) -> str:
        parts = [
            f"{d.label}={d.weighted:.1f}" + ("" if d.active else "(无数据)")
            for d in self.dimensions.values()
        ]
        return f"{self.total:.1f} 分 [" + ", ".join(parts) + "]"


class ProductCandidate(BaseModel):
    """流水线产物：一个候选商品（可持久化为 products 表）。"""

    fingerprint: str = ""  # source_core_attributes_hash
    image_phash: str = ""
    title: str = ""
    sanitized_title: str = ""
    category: str = ""
    platform_price: float = 0.0
    real_cost: Optional[float] = None
    suggested_price: Optional[float] = None
    profit_margin: Optional[float] = None
    sales: int = 0
    rank_best: int = 0
    board_count: int = 0
    source_items: list[SourceItem] = Field(default_factory=list)
    quotes: list[Quote] = Field(default_factory=list)
    supplier_count: int = 0
    return_rate: Optional[float] = None
    compliance: ComplianceResult = Field(default_factory=ComplianceResult)
    score: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    ad_conversion: dict[str, float] = Field(default_factory=dict)
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    state: str = "pool"  # pool | manual_review | rejected
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def is_candidate(self) -> bool:
        return self.compliance.state == ComplianceState.CANDIDATE


class PipelineResult(BaseModel):
    """一次流水线运行的统计结果。"""

    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
    collected: int = 0
    after_dedup: int = 0
    hard_rejected: int = 0
    manual_review: int = 0
    candidates: int = 0
    quoted: int = 0
    pool_entered: int = 0
    gate_relaxed: int = 0  # S5：人工闸门按达标自动放行的 manual_review 数（默认 0，enabled=false 零变化）
    pool: list[ProductCandidate] = Field(default_factory=list)
    skipped_sources: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def elapsed_seconds(self) -> float:
        if not self.finished_at:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()
