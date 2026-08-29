"""REC-融合 P1-5：投放 ROI 计算器（旧系统 promotion.py 迁移）。

旧系统 promotion_metrics / break_even_roi / adjusted_target_roi：
- 可投金额 = 售价 − 成本 − 运费 − 退费 − 佣金（金额一律「分」int，REC-融合-03）；
- 盈亏平衡 ROI（break_even）= 售价 / 可投金额（ROI 为浮点倍数）；
- 目标 ROI 建议：有系统推荐优先；无花费记录时按可投金额/毛利推算；
- 配置化：退费率默认 10%、佣金率默认 7%（与旧系统一致，可覆盖）。

数据口径（DA-001/REC-005）：金额分 int；ROI 浮点倍数（不走分）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PromotionConfig:
    """ROI 计算参数（环境变量前缀 ADS_，可配置化）。"""

    refund_rate: float = 0.10  # 退费率（默认 10%，旧系统口径）
    commission_rate: float = 0.07  # 平台佣金率（默认 7%）
    min_roi_floor: float = 1.0  # 建议目标 ROI 下限


@dataclass
class PromotionMetrics:
    """单个商品的可投金额分解（金额一律「分」int）。"""

    price_cents: int
    cost_cents: int
    freight_cents: int = 0
    # 派生
    refund_cents: int = 0
    commission_cents: int = 0
    investable_cents: int = 0  # 可投金额 = 售价 − 成本 − 运费 − 退费 − 佣金
    break_even_roi: float = 0.0

    @property
    def is_profitable(self) -> bool:
        return self.investable_cents > 0


def promotion_metrics(
    price_cents: int,
    cost_cents: int,
    freight_cents: int = 0,
    config: PromotionConfig | None = None,
) -> PromotionMetrics:
    """计算可投金额分解（REC-融合-03：金额分 int；退费=售价×退费率，佣金=售价×佣金率）。

    可投金额 = 售价 − 成本 − 运费 − 退费 − 佣金；
    可投金额 ≤ 0 → 无投放空间（is_profitable=False，break_even 无意义）。
    """
    cfg = config or PromotionConfig()
    refund = int(price_cents * cfg.refund_rate)
    commission = int(price_cents * cfg.commission_rate)
    investable = price_cents - cost_cents - freight_cents - refund - commission
    break_even = (
        round(price_cents / investable, 2) if investable > 0 else 0.0
    )
    return PromotionMetrics(
        price_cents=price_cents,
        cost_cents=cost_cents,
        freight_cents=freight_cents,
        refund_cents=refund,
        commission_cents=commission,
        investable_cents=investable,
        break_even_roi=break_even,
    )


def adjusted_target_roi(
    base_roi: float | None,
    metrics: PromotionMetrics,
    config: PromotionConfig | None = None,
) -> float:
    """目标 ROI 建议：系统推荐优先；无推荐 → 用 break_even 推算并加安全垫；
    结果不低于 min_roi_floor（避免负毛利投放）。"""
    cfg = config or PromotionConfig()
    if not metrics.is_profitable:
        return cfg.min_roi_floor  # 无可投空间 → 降到下限（由调用方决定是否投放）
    recommended = base_roi if base_roi and base_roi > 0 else metrics.break_even_roi
    candidate = max(recommended, metrics.break_even_roi * 1.05)  # 盈亏平衡 +5% 安全垫
    return round(max(candidate, cfg.min_roi_floor), 2)
