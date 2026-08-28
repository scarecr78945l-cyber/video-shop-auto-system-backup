"""定价阶梯测试。"""

from sourcing.config import PricingConfig
from sourcing.pricing import profit_margin, suggested_price


def test_ladder_bands():
    cfg = PricingConfig()
    assert suggested_price(2.0, cfg) == 9.0      # ≤3
    assert suggested_price(3.0, cfg) == 9.0      # 边界含
    assert suggested_price(4.5, cfg) == 19.9     # ≤5
    assert suggested_price(8.0, cfg) == 29.9     # ≤10
    assert suggested_price(13.0, cfg) == 49.9    # ≤15


def test_above_cap_uses_markup():
    cfg = PricingConfig()
    price = suggested_price(50.0, cfg)
    assert price == 125.0  # 50 * 2.5


def test_profit_margin_positive():
    m = profit_margin(6.8, price=29.9)
    assert 0.7 < m < 0.8  # (29.9-6.8)/29.9 ≈ 0.7726
