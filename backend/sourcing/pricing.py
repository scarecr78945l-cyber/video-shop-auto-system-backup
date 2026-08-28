"""定价阶梯（复用半成品 pricing.py 口径）。

成本 ≤3 → 9；≤5 → 19.9；≤10 → 29.9；≤15 → 49.9；超出上限按倍率兜底。
"""

from __future__ import annotations

from .config import PricingConfig


def suggested_price(cost: float, config: PricingConfig | None = None) -> float:
    config = config or PricingConfig()
    for cap, price in config.ladder:
        if cost <= cap:
            return price
    return round(cost * config.default_markup, 1)


def profit_margin(cost: float, price: float | None = None, config: PricingConfig | None = None) -> float:
    """毛利率 = (建议售价 - 成本) / 建议售价。"""
    config = config or PricingConfig()
    p = price if price is not None else suggested_price(cost, config)
    if p <= 0:
        return 0.0
    return (p - cost) / p
