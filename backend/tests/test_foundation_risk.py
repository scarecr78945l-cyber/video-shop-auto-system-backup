"""M0 风控规则引擎测试：S7 预算三重 / S1 止损暂停 / S3 ROI 降档 / S5 余额 / S8 一键全停。

对齐 10 文档第一节四层防线与 M5 `backend/ads/stop_loss.py` 同口径（金额分/ROI 浮点/枚举英文）。
运行：python -m pytest tests -q --basetemp=".pytest-tmp-m0"（P-001/P-011，宪法第 12 节）
"""

from __future__ import annotations

import pytest

from foundation.risk import (
    ACTION_DEGRADE_MATERIAL,
    ACTION_HALT_ALL,
    ACTION_HALT_NEW,
    ACTION_PAUSE,
    BudgetVerdict,
    RiskEngine,
    check_budget_triple,
    kill_switch_enabled,
    normalize_diagnosis,
    rule_s1_stop_loss,
    rule_s3_roi_floor,
    rule_s5_balance,
)


def _snap(spend: int, gmv: int, impressions: int, recorded_at: str | None = None) -> dict:
    d = {"spend": spend, "gmv": gmv, "impressions": impressions}
    if recorded_at:
        d["recorded_at"] = recorded_at
    return d


# ---------------------------------------------------------------- normalize_diagnosis

def test_normalize_diagnosis_mapping() -> None:
    """中文诊断 → 英文枚举（对齐 M5 同口径）。"""
    assert normalize_diagnosis("优秀") == "excellent"
    assert normalize_diagnosis("良好") == "good"
    assert normalize_diagnosis("1项待优化") == "optimize_1"
    assert normalize_diagnosis("3项待优化") == "optimize_n"
    assert normalize_diagnosis("excellent") == "excellent"  # 英文幂等
    assert normalize_diagnosis("") == "unknown"
    assert normalize_diagnosis(None) == "unknown"
    assert normalize_diagnosis("随便写点什么") == "unknown"


# ---------------------------------------------------------------- S1

def test_s1_hits_when_spend_positive_no_gmv_and_exposure_threshold() -> None:
    """S1 命中：花费>0 且 成交=0 且 曝光≥阈值 → pause + 标签。"""
    v = rule_s1_stop_loss(_snap(spend=500, gmv=0, impressions=600))
    assert v is not None
    assert v.rule_id == "S1" and v.action == ACTION_PAUSE
    assert "换素材" in v.suggested_actions


def test_s1_not_hit_when_no_spend() -> None:
    """S1 不命中：花费=0。"""
    assert rule_s1_stop_loss(_snap(spend=0, gmv=0, impressions=9999)) is None


def test_s1_not_hit_when_has_gmv() -> None:
    """S1 不命中：有成交。"""
    assert rule_s1_stop_loss(_snap(spend=100, gmv=50, impressions=9999)) is None


def test_s1_not_hit_below_exposure_threshold() -> None:
    """S1 不命中：曝光不足阈值。"""
    assert rule_s1_stop_loss(_snap(spend=100, gmv=0, impressions=100)) is None


# ---------------------------------------------------------------- S3

def test_s3_hits_two_consecutive_low_roi_periods() -> None:
    """S3 命中：最近连续 2 周期 ROI 均 < 目标×80% → degrade_material。"""
    snaps = [
        _snap(spend=1000, gmv=100, impressions=0, recorded_at="2026-08-27T00:00:00Z"),  # roi=0.1
        _snap(spend=1000, gmv=150, impressions=0, recorded_at="2026-08-28T00:00:00Z"),  # roi=0.15
    ]
    v = rule_s3_roi_floor(snaps, target_roi=1.0)  # floor=0.8；0.1/0.15 < 0.8
    assert v is not None
    assert v.rule_id == "S3" and v.action == ACTION_DEGRADE_MATERIAL


def test_s3_not_hit_single_period() -> None:
    """S3 不判定：少于 2 周期。"""
    assert rule_s3_roi_floor([_snap(spend=1000, gmv=100, impressions=0)], target_roi=1.0) is None


def test_s3_not_hit_when_roi_meets_floor() -> None:
    """S3 不命中：ROI ≥ 止损线。"""
    snaps = [
        _snap(spend=1000, gmv=900, impressions=0),   # roi=0.9 ≥ 0.8
        _snap(spend=1000, gmv=1000, impressions=0),  # roi=1.0
    ]
    assert rule_s3_roi_floor(snaps, target_roi=1.0) is None


def test_s3_hit_boundary_when_no_spend() -> None:
    """S3 边界：花费=0 → ROI=0（命中止损线，对齐 M5 语义）。"""
    snaps = [
        _snap(spend=0, gmv=0, impressions=0),
        _snap(spend=0, gmv=0, impressions=0),
    ]
    v = rule_s3_roi_floor(snaps, target_roi=1.0)
    assert v is not None
    assert all(p["roi"] == 0.0 for p in v.evidence["periods"])


def test_s3_not_hit_at_exact_floor() -> None:
    """S3 不命中：ROI 等于止损线（严格小于）。"""
    snaps = [
        _snap(spend=1000, gmv=800, impressions=0),  # roi=0.8 == floor
        _snap(spend=1000, gmv=800, impressions=0),
    ]
    assert rule_s3_roi_floor(snaps, target_roi=1.0) is None


# ---------------------------------------------------------------- S5

def test_s5_hits_below_balance_threshold() -> None:
    """S5 命中：余额 < 阈值 → halt_new。"""
    v = rule_s5_balance(account_balance_fen=5000, min_balance_fen=10000)
    assert v is not None
    assert v.rule_id == "S5" and v.action == ACTION_HALT_NEW


def test_s5_not_hit_at_threshold() -> None:
    """S5 不命中：余额等于阈值（严格小于）。"""
    assert rule_s5_balance(account_balance_fen=10000, min_balance_fen=10000) is None
    assert rule_s5_balance(account_balance_fen=20000, min_balance_fen=10000) is None


# ---------------------------------------------------------------- S7

def test_budget_triple_single_over_limit() -> None:
    """S7 单笔超限。"""
    v = check_budget_triple(6000, 5000, 5000, budget_single_fen=5000, budget_daily_fen=10000, budget_plan_fen=10000)
    assert v.over_limit and v.rule == "single"


def test_budget_triple_daily_over_limit() -> None:
    """S7 日总超限（单笔未超）。"""
    v = check_budget_triple(4000, 12000, 5000, budget_single_fen=5000, budget_daily_fen=10000, budget_plan_fen=10000)
    assert v.over_limit and v.rule == "daily"


def test_budget_triple_plan_over_limit() -> None:
    """S7 计划总超限（单笔/日未超）。"""
    v = check_budget_triple(4000, 5000, 20000, budget_single_fen=5000, budget_daily_fen=10000, budget_plan_fen=15000)
    assert v.over_limit and v.rule == "plan"


def test_budget_triple_zero_means_unlimited() -> None:
    """S7 0=不限：预算为 0 时不超限。"""
    v = check_budget_triple(99999, 99999, 99999, 0, 0, 0)
    assert not v.over_limit and v.rule == "none"


def test_budget_triple_multiple_over_takes_first() -> None:
    """S7 多超限取首个（single 优先）。"""
    v = check_budget_triple(9000, 9000, 9000, budget_single_fen=5000, budget_daily_fen=5000, budget_plan_fen=5000)
    assert v.over_limit and v.rule == "single"


def test_budget_triple_ok() -> None:
    """S7 未超限。"""
    v = check_budget_triple(4000, 5000, 6000, budget_single_fen=5000, budget_daily_fen=10000, budget_plan_fen=20000)
    assert not v.over_limit and v.rule == "none"


# ---------------------------------------------------------------- S8

def test_kill_switch_true_forms() -> None:
    """S8 开启判定：bool/字符串开启形式。"""
    assert kill_switch_enabled(True) is True
    assert kill_switch_enabled(False, "1") is True
    assert kill_switch_enabled(False, "true") is True
    assert kill_switch_enabled(False, "on") is True
    assert kill_switch_enabled(False, "enabled") is True


def test_kill_switch_unknown_string_is_off() -> None:
    """S8 未识别字符串视为关（防误触发全停）。"""
    assert kill_switch_enabled(False, "maybe") is False
    assert kill_switch_enabled(False, None) is False
    assert kill_switch_enabled(False, "0") is False
    assert kill_switch_enabled(False, "off") is False


# ---------------------------------------------------------------- RiskEngine

def test_engine_kill_switch_short_circuits() -> None:
    """引擎：kill_switch=True → halt_all，只返回 S8。"""
    result = RiskEngine().evaluate(
        campaign={}, snapshots=[], account_balance_fen=0, kill_switch=True,
    )
    assert result.halt_all is True
    assert [v.rule_id for v in result.verdicts] == ["S8"]
    assert result.actions == {ACTION_HALT_ALL: 1}


def test_engine_budget_over_limit_verdict() -> None:
    """引擎：预算超限 → S7 verdict（不触发 halt_all，对齐 M5 语义）。"""
    bv = check_budget_triple(9000, 5000, 5000, budget_single_fen=5000, budget_daily_fen=10000, budget_plan_fen=20000)
    result = RiskEngine().evaluate(
        campaign={}, snapshots=[], account_balance_fen=999999, budget=bv,
    )
    assert result.halt_all is False
    assert any(v.rule_id == "S7" for v in result.verdicts)


def test_engine_balance_halt_all() -> None:
    """引擎：余额不足 → halt_all=True（S5）。"""
    result = RiskEngine().evaluate(
        campaign={}, snapshots=[], account_balance_fen=500, min_balance_fen=10000,
    )
    assert result.halt_all is True
    assert any(v.rule_id == "S5" for v in result.verdicts)


def test_engine_s1_and_s3_compose() -> None:
    """引擎：S1 命中 + S3 命中 同时输出（自动止损组合）。"""
    snaps = [
        _snap(spend=1000, gmv=0, impressions=600),   # S1 命中
        _snap(spend=1000, gmv=100, impressions=0),   # S3 周期1（roi=0.1）
        _snap(spend=1000, gmv=150, impressions=0),   # S3 周期2（roi=0.15）
    ]
    result = RiskEngine().evaluate(
        campaign={}, snapshots=snaps, account_balance_fen=999999, target_roi=1.0,
    )
    rules = {v.rule_id for v in result.verdicts}
    assert "S1" in rules and "S3" in rules
    assert result.actions.get(ACTION_PAUSE, 0) >= 1
    assert result.actions.get(ACTION_DEGRADE_MATERIAL, 0) >= 1


def test_engine_all_clear() -> None:
    """引擎：无任何命中 → 空 verdicts、halt_all=False。"""
    snaps = [_snap(spend=0, gmv=0, impressions=10)]
    result = RiskEngine().evaluate(
        campaign={}, snapshots=snaps, account_balance_fen=999999,
    )
    assert result.verdicts == []
    assert result.halt_all is False


def test_engine_budget_dict_input() -> None:
    """引擎：budget 支持 dict 输入（兼容调用方）。"""
    budget_dict = {"over_limit": True, "rule": "daily", "reason": "日总预算超限", "spend_fen": 12000, "budget_fen": 10000}
    result = RiskEngine().evaluate(
        campaign={}, snapshots=[], account_balance_fen=999999, budget=budget_dict,
    )
    assert any(v.rule_id == "S7" for v in result.verdicts)
