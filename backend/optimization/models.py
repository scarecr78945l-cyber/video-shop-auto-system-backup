"""M3 自动素材优化模块 · 领域模型。

对齐方案文档 06 与 _management/modules/m3-optimization/context/README.md 数据字典。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- 文案 ----------

class TitleCleanResult(BaseModel):
    """标题机械清洗结果（以淘宝原始标题为唯一来源，不虚构卖点）。"""

    original: str = ""
    title: str = ""
    char_len: int = 0
    ok: bool = False                      # 清洗后是否满足 15~35 字符
    reasons: list[str] = Field(default_factory=list)
    # 去除项证据（去标签/营销词/品牌词/供应链词/功效词各命中哪些）
    removed: dict[str, list[str]] = Field(default_factory=dict)


class CopywriteDraft(BaseModel):
    """文案候选（标题/口播稿/投放文案/角标）。"""

    product_id: str
    copy_type: str                        # title/script/ad/badge
    content: str
    variant_no: int = 1
    char_len: int = 0
    sku_basis: Optional[dict[str, Any]] = None   # 口播稿 SKU 依据（防虚假承诺）
    compliance_hits: list[str] = Field(default_factory=list)  # 合规命中词
    passed: bool = False                  # 合规预审是否通过
    source: str = "llm"                   # llm / rule_fallback（降级标记）


# ---------- 图片 ----------

class ImagePlan(BaseModel):
    """Kimi 视觉策略规划结果（失败降级默认策略并标记 source=rule_fallback）。"""

    product_id: str
    image_type: str                       # main/detail
    strategy: str = ""                    # 策略描述（角度/背景/卖点焦点）
    prompts: list[str] = Field(default_factory=list)  # 每张图的生图提示词
    source: str = "llm"                   # llm / rule_fallback


class ImageDraft(BaseModel):
    """单张生图结果（离线 fixtures 模式为占位图）。"""

    batch_id: str
    product_id: str
    image_type: str                       # main/detail
    variant_no: int = 1
    file_path: str = ""
    phash: str = ""
    width: int = 0
    height: int = 0


class QualityVerdict(BaseModel):
    """质量门禁结论（对齐 06：分辨率/清晰度/完整性/phash 相似度）。"""

    image_id: str
    ok: bool = True
    score: float = 100.0
    issues: list[str] = Field(default_factory=list)


# ---------- 类目记忆 / 评估 ----------

class CategoryMemory(BaseModel):
    """类目记忆：按类目累积「人工通过/平台拒审」经验，调整生图/模板策略。"""

    category: str
    pass_count: int = 0
    reject_count: int = 0
    reject_reasons: dict[str, int] = Field(default_factory=dict)
    image_strategy: dict[str, Any] = Field(default_factory=dict)


class EvaluationSnapshot(BaseModel):
    """投放效果回写快照（M5 → opt_evaluation_feedback）。"""

    variant_id: str
    report_date: str                      # UTC YYYY-MM-DD
    exposure: int = 0
    clicks: int = 0
    spend: float = 0.0
    orders: int = 0
    roi: float = 0.0
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0                    # 素材评分 = f(ROI, CTR, 诊断)
    evaluation: str = "exploration"       # 探索期/潜力/高效
    stale: bool = False
