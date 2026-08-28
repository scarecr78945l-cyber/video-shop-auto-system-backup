"""五维打分测试：各维档位、权重折算、投放转化不生效、可解释 reasons。"""

from sourcing.config import SourcingConfig
from sourcing.scoring import ScoreInput, Scorer


def scorer(**overrides) -> Scorer:
    cfg = SourcingConfig(**overrides)
    return Scorer(cfg.scoring)


def test_trend_rank_band():
    s = scorer().score(ScoreInput(rank=2, sales=20000, board_count=1))
    assert s.dimensions["trend"].raw == 25.0 + 8.0  # 排名≤3 + 销量≥10000


def test_trend_cross_confirmation_bonus():
    s = scorer().score(ScoreInput(rank=5, sales=5000, board_count=3))
    assert "交叉确认" in "".join(s.dimensions["trend"].reasons)


def test_profit_high_margin():
    s = scorer().score(ScoreInput(real_cost=6.8, suggested_price=29.9))
    margin = (29.9 - 6.8) / 29.9
    assert s.dimensions["profit"].raw > 0
    assert f"{margin:.0%}" in "".join(s.dimensions["profit"].reasons)


def test_profit_unknown_uses_estimate():
    s = scorer().score(ScoreInput(platform_price=29.9, real_cost=None))
    assert s.dimensions["profit"].active
    assert "估算" in "".join(s.dimensions["profit"].reasons)


def test_after_sale_bands():
    assert scorer().score(ScoreInput(return_rate=0.02)).dimensions["after_sale"].raw == 20.0
    assert scorer().score(ScoreInput(return_rate=0.05)).dimensions["after_sale"].raw == 16.0
    assert scorer().score(ScoreInput(return_rate=0.10)).dimensions["after_sale"].raw == 8.0
    assert scorer().score(ScoreInput(return_rate=0.30)).dimensions["after_sale"].raw == 0.0


def test_supply_bands():
    assert scorer().score(ScoreInput(supplier_count=10)).dimensions["supply"].raw == 15.0
    assert scorer().score(ScoreInput(supplier_count=1)).dimensions["supply"].raw == 2.0


def test_ad_conversion_inactive_without_data_folds_weight():
    """无投放数据：ad_conversion 维度不生效，基础四维满分（和 100）。"""
    s = scorer().score(ScoreInput(rank=1, sales=10000, board_count=2, real_cost=5,
                                  suggested_price=29.9, return_rate=0.02, supplier_count=10))
    assert not s.dimensions["ad_conversion"].active
    assert s.dimensions["ad_conversion"].weight == 0
    assert s.total <= 100.0
    # 基础四维权重和 = 1
    w = sum(d.weight for d in s.dimensions.values() if d.active)
    assert abs(w - 1.0) < 1e-6
    # 满分场景：trend(25+8+2)=35 / profit=30 / supply=15 → 各自满分
    assert s.dimensions["trend"].weighted == 35.0
    assert s.dimensions["profit"].weighted == 30.0
    assert s.dimensions["supply"].weighted == 15.0
    assert s.total == 100.0


def test_ad_conversion_active_with_data():
    """有投放数据：基础四维按 (100-10)/100 折算，投放转化占 10 分。"""
    s = scorer().score(ScoreInput(rank=1, sales=10000, real_cost=5, suggested_price=29.9,
                                  return_rate=0.02, supplier_count=10, ad_roi=3.2))
    assert s.dimensions["ad_conversion"].active
    assert s.dimensions["ad_conversion"].raw == 10.0
    assert s.dimensions["ad_conversion"].weighted == 10.0
    # trend 权重 = 35/100 * 0.9 = 0.315
    assert abs(s.dimensions["trend"].weight - 0.315) < 1e-6
    assert s.total <= 100.0


def test_ad_roi_low_scores_low():
    s = scorer().score(ScoreInput(ad_roi=0.5))
    assert s.dimensions["ad_conversion"].raw == scorer().cfg.ad_roi_below


def test_reasons_present_for_every_active_dimension():
    s = scorer().score(ScoreInput(rank=3, sales=1000, real_cost=3, suggested_price=9.0,
                                  return_rate=0.05, supplier_count=5, ad_roi=2.0))
    for key, dim in s.dimensions.items():
        if dim.active:
            assert dim.reasons, f"维度 {key} 缺少打分理由"
    assert "ROI" in "".join(s.dimensions["ad_conversion"].reasons)


def test_total_is_sum_of_weighted():
    s = scorer().score(ScoreInput(rank=10, sales=2000, real_cost=8, suggested_price=19.9,
                                  return_rate=0.10, supplier_count=3, ad_roi=1.6))
    expected = round(sum(d.weighted for d in s.dimensions.values() if d.active), 1)
    assert s.total == expected
