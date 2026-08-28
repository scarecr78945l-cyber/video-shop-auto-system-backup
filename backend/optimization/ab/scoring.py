"""M3 A/B 优化闭环 · 素材评分（对齐 06 文档第五节「素材评分 = f(成交 ROI, 曝光点击率, 诊断结果)」）。

公式（默认权重可配置）::

    score = roi_weight * roi_score + ctr_weight * ctr_score + diag_weight * diag_score

- 各分项归一化到 [0,1]：``roi_score = min(roi / roi_score_cap, 1)``（默认饱和点 5.0）、
  ``ctr_score = min(ctr / ctr_score_cap, 1)``（默认饱和点 0.05 = 5% CTR）；
- 诊断映射（对齐 M5 normalize_diagnosis 枚举，兼容中文/字典/数值形状）：
  excellent/优秀=1.0、good/良好=0.7、optimize_1/1项待优化=0.4、
  optimize_n/N项待优化=0.2、unknown/无=0.0；
- 无回写数据（exposure/orders 全 0）→ 输入 0 → score=0，由 evaluate/ranking 层
  一并置 evaluation=exploration（本层只算分，标签计算在 evaluate.py）；
- 权重与饱和点配置化：``ScoringPolicy.from_env()`` 读环境变量
  M3_AB_ROI_WEIGHT / M3_AB_CTR_WEIGHT / M3_AB_DIAG_WEIGHT /
  M3_AB_ROI_SCORE_CAP / M3_AB_CTR_SCORE_CAP（只出现环境变量名，不写密钥）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional

# ---------- 环境变量名（只出现名字，不出现密钥值） ----------

ENV_ROI_WEIGHT = "M3_AB_ROI_WEIGHT"
ENV_CTR_WEIGHT = "M3_AB_CTR_WEIGHT"
ENV_DIAG_WEIGHT = "M3_AB_DIAG_WEIGHT"
ENV_ROI_SCORE_CAP = "M3_AB_ROI_SCORE_CAP"
ENV_CTR_SCORE_CAP = "M3_AB_CTR_SCORE_CAP"

DEFAULT_ROI_WEIGHT = 0.5
DEFAULT_CTR_WEIGHT = 0.3
DEFAULT_DIAG_WEIGHT = 0.2
DEFAULT_ROI_SCORE_CAP = 5.0    # ROI ≥5 → roi_score=1.0
DEFAULT_CTR_SCORE_CAP = 0.05   # CTR ≥5% → ctr_score=1.0

# 诊断 → 分项（对齐 M5 report/stop_loss normalize_diagnosis 枚举与中文后台展示）
_DIAG_MAP: dict[str, float] = {
    "excellent": 1.0, "优秀": 1.0,
    "good": 0.7, "良好": 0.7,
    "optimize_1": 0.4, "1项待优化": 0.4,
    "optimize_n": 0.2, "n项待优化": 0.2, "N项待优化": 0.2,
    "unknown": 0.0, "无": 0.0, "": 0.0,
}
_OPTIMIZE_RE = re.compile(r"(\d+)\s*项待优化")


@dataclass
class ScoringPolicy:
    """评分权重与饱和点（默认值可经环境变量覆盖，注入构造亦可）。"""

    roi_weight: float = DEFAULT_ROI_WEIGHT
    ctr_weight: float = DEFAULT_CTR_WEIGHT
    diag_weight: float = DEFAULT_DIAG_WEIGHT
    roi_score_cap: float = DEFAULT_ROI_SCORE_CAP
    ctr_score_cap: float = DEFAULT_CTR_SCORE_CAP

    def __post_init__(self) -> None:
        total = self.roi_weight + self.ctr_weight + self.diag_weight
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"评分权重之和须为 1.0，当前 {total:.4f}")
        if self.roi_score_cap <= 0 or self.ctr_score_cap <= 0:
            raise ValueError("评分饱和点必须 > 0")

    @classmethod
    def from_env(cls) -> "ScoringPolicy":
        """从环境变量加载（非法值回退默认，绝不抛错）。"""
        def _f(name: str, default: float) -> float:
            try:
                return float(os.environ.get(name, "") or default)
            except (TypeError, ValueError):
                return default

        return cls(
            roi_weight=_f(ENV_ROI_WEIGHT, DEFAULT_ROI_WEIGHT),
            ctr_weight=_f(ENV_CTR_WEIGHT, DEFAULT_CTR_WEIGHT),
            diag_weight=_f(ENV_DIAG_WEIGHT, DEFAULT_DIAG_WEIGHT),
            roi_score_cap=_f(ENV_ROI_SCORE_CAP, DEFAULT_ROI_SCORE_CAP),
            ctr_score_cap=_f(ENV_CTR_SCORE_CAP, DEFAULT_CTR_SCORE_CAP),
        )


# ---------------------------------------------------------------- 分项工具


def _clamp01(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def ctr_of(clicks: Any, exposure: Any) -> float:
    """曝光点击率 = clicks / exposure（曝光 ≤0 视为无数据 → 0）。"""
    exp = float(exposure or 0)
    if exp <= 0:
        return 0.0
    return float(clicks or 0) / exp


def roi_score(roi: Any, cap: float = DEFAULT_ROI_SCORE_CAP) -> float:
    """ROI 分项：min(roi / cap, 1)，负值钳 0。"""
    return _clamp01(float(roi or 0) / max(float(cap), 1e-9))


def ctr_score(ctr: Any, cap: float = DEFAULT_CTR_SCORE_CAP) -> float:
    """CTR 分项：min(ctr / cap, 1)，负值钳 0。"""
    return _clamp01(float(ctr or 0) / max(float(cap), 1e-9))


def _diag_value(value: Any) -> float:
    """单个诊断值 → [0,1]（枚举字符串 / 数值 0~1 或 0~100 分制 / bool）。"""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        if 0.0 <= v <= 1.0:
            return v
        if 0.0 < v <= 100.0:   # 0~100 分制 → /100
            return v / 100.0
        return 0.0
    text = str(value or "").strip()
    if text in _DIAG_MAP:
        return _DIAG_MAP[text]
    m = _OPTIMIZE_RE.search(text)
    if m:
        return 0.4 if int(m.group(1)) == 1 else 0.2
    return _DIAG_MAP.get(text.lower(), 0.0)


def diag_score(diagnosis: Any) -> float:
    """诊断结果 → [0,1] 分项。

    接受形状：dict（level/diagnosis/evaluation/quality/score 键，取首个命中）、
    字符串（M5 枚举或中文后台值）、数值（0~1 或 0~100 分制）。未知 → 0.0。
    """
    if diagnosis is None:
        return 0.0
    if isinstance(diagnosis, dict):
        for key in ("level", "diagnosis", "evaluation", "quality"):
            if diagnosis.get(key) is not None:
                return _diag_value(diagnosis[key])
        if "score" in diagnosis:
            return _diag_value(diagnosis["score"])
        return 0.0
    return _diag_value(diagnosis)


# ---------------------------------------------------------------- 评分器


class MaterialScorer:
    """素材评分器：``score = roi_weight*roi_score + ctr_weight*ctr_score + diag_weight*diag_score``。"""

    def __init__(self, policy: Optional[ScoringPolicy] = None):
        self.policy = policy or ScoringPolicy.from_env()

    def score(self, roi: Any, ctr: Any, diagnosis: Any) -> float:
        """给定 ROI / CTR（比值）/ 诊断 → 加权得分 [0,1]。无数据输入 0 → 0 分。"""
        p = self.policy
        return round(
            p.roi_weight * roi_score(roi, p.roi_score_cap)
            + p.ctr_weight * ctr_score(ctr, p.ctr_score_cap)
            + p.diag_weight * diag_score(diagnosis),
            4,
        )

    def score_for_metrics(
        self, roi: Any, clicks: Any, exposure: Any, diagnosis: Any
    ) -> float:
        """按 曝光/点击 换算 CTR 后评分（evaluate 回写层使用的便捷入口）。"""
        return self.score(roi, ctr_of(clicks, exposure), diagnosis)


def compute_score(
    roi: Any, ctr: Any, diagnosis: Any, policy: Optional[ScoringPolicy] = None
) -> float:
    """模块级便捷入口（对齐任务书公式）。"""
    return MaterialScorer(policy).score(roi, ctr, diagnosis)
