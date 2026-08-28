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
    """榜单上的原始商品条目（三源通用）。"""

    source: str  # opportunities | youmi | doudian（选品三源）；alibaba/taobao（询价/素材）
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
    """1688 逐 SKU 真实询价结果（订单确认页读价，不下单）。"""

    supplier_name: str
    sku_name: str
    unit_cost: float  # 单价（元）
    min_order: int = 1
    freight: float = 0.0
    raw_url: str = ""  # 拿到真实链接才算有效
    quoted_at: datetime = Field(default_factory=utcnow)

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
    pool: list[ProductCandidate] = Field(default_factory=list)
    skipped_sources: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def elapsed_seconds(self) -> float:
        if not self.finished_at:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()
