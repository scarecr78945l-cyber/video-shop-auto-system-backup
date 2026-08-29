"""REC-融合 P1-5：投放 ROI 计算器 fixtures 测试。

旧系统 promotion.py 迁移验证：
① 可投金额 = 售价−成本−运费−退费−佣金（分 int）
② break_even_roi 正确（售价/可投金额）
③ adjusted_target_roi：无推荐时按 break_even 推算 + 安全垫
④ 无可投空间 → 降至下限（防负毛利投放）
⑤ 配置化：退费率/佣金率可覆盖
"""

from ads.roi import PromotionConfig, adjusted_target_roi, promotion_metrics


def test_investable_breakdown():
    """① 可投金额分解正确（金额分 int）。"""
    # 售价 2990 分，成本 800，运费 200，退费 10%=299，佣金 7%=209
    m = promotion_metrics(price_cents=2990, cost_cents=800, freight_cents=200)
    assert m.refund_cents == 299
    assert m.commission_cents == 209
    assert m.investable_cents == 2990 - 800 - 200 - 299 - 209
    assert m.is_profitable is True


def test_break_even_roi():
    """② break_even = 售价/可投金额。"""
    m = promotion_metrics(price_cents=1000, cost_cents=300, freight_cents=100)
    investable = 1000 - 300 - 100 - 100 - 70  # 退费 10% + 佣金 7%
    assert m.break_even_roi == round(1000 / investable, 2)


def test_adjusted_roi_without_recommendation():
    """③ 无系统推荐 → break_even +5% 安全垫，且不低于下限。"""
    m = promotion_metrics(price_cents=2000, cost_cents=500, freight_cents=100)
    assert adjusted_target_roi(None, m) > m.break_even_roi


def test_unprofitable_floors_to_min():
    """④ 无可投空间（成本+运费+退费+佣金 ≥ 售价）→ 降至下限。"""
    m = promotion_metrics(price_cents=1000, cost_cents=900, freight_cents=100)
    assert m.is_profitable is False
    assert adjusted_target_roi(None, m) == PromotionConfig().min_roi_floor


def test_custom_rates():
    """⑤ 退费率/佣金率配置化覆盖。"""
    cfg = PromotionConfig(refund_rate=0.05, commission_rate=0.10)
    m = promotion_metrics(price_cents=1000, cost_cents=400, freight_cents=0, config=cfg)
    assert m.refund_cents == 50
    assert m.commission_cents == 100
    assert m.investable_cents == 1000 - 400 - 0 - 50 - 100
