"""M6 后端 API 层 · pydantic 请求/响应模型（schemas）。

金额口径（DA-001 总控裁决）：API 对外一律「元（float）」——内部存储分不变，
API 层 ÷100 换算；M1 商品池元字段直接透传。本文件所有金额响应字段均为
`float` 元（禁止分输出给前端）。时间一律 ISO8601 UTC（`...Z`），字段名 `*_at`。
枚举原样透传不翻译（英文/中文枚举均由前端 lib/enums.ts 翻译）。
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ================================================================ 请求模型


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=256)


class KillSwitchBody(BaseModel):
    enabled: bool


class AppConfigPutBody(BaseModel):
    value: Any = None
    description: Optional[str] = None


class GateConfirmBody(BaseModel):
    product_id: int


class RelevanceConfirmBody(BaseModel):
    decision: str = Field(..., description="pass / reject / manual_review（M3 gate.result 口径）")


class ImageDecisionBody(BaseModel):
    decision: str = Field(..., description="approve / reject")
    reason: Optional[str] = None


class ListingConfirmBody(BaseModel):
    note: Optional[str] = None


class AdsMaterialsBody(BaseModel):
    material_ids: list[str] = Field(..., min_length=1)


# ================================================================ 响应模型


class MeResponse(BaseModel):
    username: str
    role: str


class LoginResponse(BaseModel):
    username: str
    role: str


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: Optional[Any] = None


class OverviewResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_jobs: int
    jobs_by_stage: dict[str, int]
    jobs_by_status: dict[str, int]
    jobs_by_error_code: dict[str, int]
    today_funnel: dict[str, int]
    risk: dict[str, Any]


class JobSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    product_id: int
    stage: str
    status: str
    error_code: Optional[str] = None
    error_message: str = ""
    retry_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PaginatedJobs(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[dict[str, Any]]


class ProductSummary(BaseModel):
    """商品池条目（M1 元字段直接透传，不外发分）。"""

    model_config = ConfigDict(extra="allow")

    id: int
    fingerprint: str
    title: str = ""
    sanitized_title: str = ""
    category: str = ""
    platform_price: Optional[float] = None
    real_cost: Optional[float] = None
    suggested_price: Optional[float] = None
    profit_margin: Optional[float] = None
    sales: int = 0
    rank_best: int = 0
    board_count: int = 0
    score: float = 0.0
    state: str = ""
    compliance: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class ProductDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    fingerprint: str
    title: str = ""
    sanitized_title: str = ""
    category: str = ""
    platform_price: Optional[float] = None
    real_cost: Optional[float] = None
    suggested_price: Optional[float] = None
    profit_margin: Optional[float] = None
    score: float = 0.0
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    compliance: dict[str, Any] = Field(default_factory=dict)
    state: str = ""
    quotes: list[dict[str, Any]] = Field(default_factory=list)
    source_evidence: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None


class AdsCampaignSummary(BaseModel):
    """托管看板条目（对齐后台列：商品/目标出价/诊断/曝光/花费/成交/补贴/操作）。

    金额一律 float 元（分 ÷100）。status/diagnosis/target_type 原样透传（英文枚举）。
    """

    model_config = ConfigDict(extra="allow")

    id: int
    product_id: int
    ad_mode: str = "goods_trust"
    target_type: str = "roi"
    target_roi: Optional[float] = None
    status: str = ""
    diagnosis: Optional[str] = None
    material_ids: list[str] = Field(default_factory=list)
    batch_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # 最近快照（金额元）
    latest_snapshot: Optional[dict[str, Any]] = None


class AdsAccountResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    balance_yuan: Optional[float] = None
    status: str = "active"
    throttle_level: int = 0
    paused_until: Optional[str] = None
    pause_reason: str = ""
    min_balance_yuan: float = 100.0
    updated_at: Optional[str] = None


class AdsReportRow(BaseModel):
    date: str
    impressions: int = 0
    spend_yuan: float = 0.0
    gmv_yuan: float = 0.0
    subsidy_yuan: float = 0.0
    campaign_count: int = 0


class ListingReadyItem(BaseModel):
    """待上架/已上架候选（候选池视图；价格 分→元）。"""

    model_config = ConfigDict(extra="allow")

    product_id: int
    task_id: str
    title: Optional[str] = None
    category_id: Optional[int] = None
    product_link: Optional[str] = None
    link_verified_at: Optional[str] = None
    price_min_yuan: Optional[float] = None
    price_max_yuan: Optional[float] = None
