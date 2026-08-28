"""M5 自动小店投放（商品托管）· 止损规则引擎测试（v0.4，纯数据驱动）。

覆盖：normalize_diagnosis 枚举化、S1~S8 规则命中/边界、预算三重硬约束（S7）、
一键全停（S8）、StopLossEngine 集成（kill_switch 短路 / S5+S6 halt_all /
verdicts 顺序稳定 / actions 汇总 / recommendations 聚合 / budget 与 subsidy 开关）。

fixtures 全部在测试文件内自建（dict 数据，不依赖 DB，不改写 conftest）。

运行（P-001/P-011：必须带独立 basetemp .pytest-tmp-m5）：
  python -m pytest tests/test_ads_stop_loss.py -q --basetemp=".pytest-tmp-m5"
"""

import json

from ads.stop_loss import (
    BudgetVerdict,
    EngineResult,
    RuleVerdict,
    StopLossEngine,
    check_budget_triple,
    kill_switch_enabled,
    normalize_diagnosis,
    rule_s1_stop_loss,
    rule_s2_optimize_diagnosis,
    rule_s3_roi_floor,
    rule_s4_subsidy,
    rule_s5_balance,
    rule_s6_active_cap,
)

# ---------------------------------------------------------------- 测试工具（自建 fixtures）


def _snap(
    impressions=0,
    spend=0,
    gmv=0,
    subsidy=0,
    diagnosis=None,
    recorded_at=None,
):
    """构造报表快照 dict（金额单位：分；字段对齐 AdReportSnapshot）。"""
    s = {
        "impressions": impressions,
        "spend": spend,
        "gmv": gmv,
        "platform_subsidy": subsidy,
        "diagnosis": diagnosis,
        "status": "投放中",
    }
    if recorded_at is not None:
        s["recorded_at"] = recorded_at
    return s


def _campaign(cid=1, target_roi=2.0, diagnosis=None, status="active"):
    """构造托管计划 dict（字段对齐 AdCampaign，仅引擎需要的字段）。"""
    return {
        "id": cid,
        "product_id": 100,
        "target_roi": target_roi,
        "diagnosis": diagnosis,
        "status": status,
    }


def _evaluate(snapshots=None, campaign=None, **kw):
    """引擎便捷调用：未显式传参的关键字用不触发止损的安全默认值。"""
    defaults = {
        "account_balance_fen": 50000,   # 充足
        "min_balance_fen": 10000,
        "active_count": 10,             # 未超限
        "active_cap": 40,
        "target_roi": 2.0,
        "roi_floor_ratio": 0.8,
        "threshold_impressions": 500,
        "kill_switch": False,
    }
    defaults.update(kw)
    return StopLossEngine().evaluate(
        campaign if campaign is not None else _campaign(),
        list(snapshots) if snapshots is not None else [],
        **defaults,
    )


# ---------------------------------------------------------------- normalize_diagnosis

def test_normalize_diagnosis_chinese_enums():
    assert normalize_diagnosis("优秀") == "excellent"
    assert normalize_diagnosis("良好") == "good"
    assert normalize_diagnosis("1项待优化") == "optimize_1"
    assert normalize_diagnosis("3项待优化") == "optimize_n"
    assert normalize_diagnosis("10项待优化") == "optimize_n"


def test_normalize_diagnosis_unknown_inputs():
    assert normalize_diagnosis(None) == "unknown"
    assert normalize_diagnosis("") == "unknown"
    assert normalize_diagnosis("   ") == "unknown"
    assert normalize_diagnosis("未知") == "unknown"
    assert normalize_diagnosis("N项待优化") == "unknown"  # N 为字面量，非数字
    assert normalize_diagnosis(123) == "unknown"          # 非字符串


def test_normalize_diagnosis_english_passthrough_and_whitespace():
    # 英文枚举幂等
    assert normalize_diagnosis("excellent") == "excellent"
    assert normalize_diagnosis("good") == "good"
    assert normalize_diagnosis("optimize_1") == "optimize_1"
    assert normalize_diagnosis("optimize_n") == "optimize_n"
    # 首尾空白容忍 + 数字与「项」之间空白容忍
    assert normalize_diagnosis(" 优秀 ") == "excellent"
    assert normalize_diagnosis(" 2 项待优化 ") == "optimize_n"


# ---------------------------------------------------------------- S1 止损暂停

def test_s1_hit_full_values():
    snap = _snap(impressions=500, spend=1200, gmv=0)
    v = rule_s1_stop_loss(snap, 500)
    assert v is not None
    assert isinstance(v, RuleVerdict)
    assert v.rule_id == "S1"
    assert v.action == "pause"
    assert "1200" in v.reason and "500" in v.reason  # reason 含实际值
    assert "换素材/调ROI" in v.reason                # 标签「换素材/调ROI」
    assert v.evidence == {"spend": 1200, "gmv": 0, "impressions": 500, "threshold_impressions": 500}
    assert "换素材" in v.suggested_actions and "调ROI" in v.suggested_actions
    assert isinstance(json.dumps(v.evidence), str)   # evidence 可 JSON 序列化
    # 默认阈值 500 / 阈值自定义
    assert rule_s1_stop_loss(_snap(impressions=500, spend=1, gmv=0)).rule_id == "S1"
    assert rule_s1_stop_loss(_snap(impressions=1000, spend=1, gmv=0), 2000) is None


def test_s1_no_hit_boundaries():
    assert rule_s1_stop_loss(_snap(impressions=500, spend=0, gmv=0), 500) is None      # 无花费
    assert rule_s1_stop_loss(_snap(impressions=500, spend=1200, gmv=100), 500) is None  # 有成交
    assert rule_s1_stop_loss(_snap(impressions=499, spend=1200, gmv=0), 500) is None    # 曝光不足
    assert rule_s1_stop_loss(_snap(impressions=0, spend=1200, gmv=0), 500) is None
    assert rule_s1_stop_loss({}, 500) is None                                            # 空快照


# ---------------------------------------------------------------- S2 诊断优化记录

def test_s2_hit_optimize_1_and_n():
    for raw in ("1项待优化", "optimize_1"):
        v = rule_s2_optimize_diagnosis(_snap(diagnosis=raw))
        assert v is not None and v.rule_id == "S2" and v.action == "record_optimization"
        assert v.evidence["diagnosis"] == "optimize_1"
        assert v.evidence["priority_retry"] is True   # 标记优先重投
    for raw in ("3项待优化", "5 项待优化", "optimize_n"):
        v = rule_s2_optimize_diagnosis(_snap(diagnosis=raw))
        assert v is not None and v.evidence["diagnosis"] == "optimize_n"


def test_s2_no_hit():
    for raw in ("优秀", "良好", "excellent", "good", None, "", "未知"):
        assert rule_s2_optimize_diagnosis(_snap(diagnosis=raw)) is None
    assert rule_s2_optimize_diagnosis({}) is None


# ---------------------------------------------------------------- S3 ROI 止损线

def test_s3_hit_two_consecutive_periods():
    snaps = [
        _snap(spend=10000, gmv=15000, recorded_at=1),  # roi 1.50 < 1.60
        _snap(spend=10000, gmv=12000, recorded_at=2),  # roi 1.20 < 1.60
    ]
    v = rule_s3_roi_floor(snaps, target_roi=2.0)
    assert v is not None and v.rule_id == "S3" and v.action == "degrade_material"
    assert v.evidence["roi_floor"] == 1.6
    assert len(v.evidence["periods"]) == 2
    assert [p["roi"] for p in v.evidence["periods"]] == [1.5, 1.2]
    assert "降素材优先级" in v.suggested_actions and "调ROI" in v.suggested_actions


def test_s3_insufficient_periods():
    assert rule_s3_roi_floor([_snap(spend=10000, gmv=1000)], 2.0) is None  # 仅 1 周期
    assert rule_s3_roi_floor([], 2.0) is None                              # 无快照


def test_s3_zero_spend_counts_as_zero_roi():
    snaps = [_snap(spend=0, gmv=0), _snap(spend=0, gmv=5000)]
    v = rule_s3_roi_floor(snaps, target_roi=2.0)
    assert v is not None  # 花费=0 → ROI=0 < 1.6，命中
    assert v.evidence["periods"][0]["roi"] == 0.0
    assert v.evidence["periods"][1]["roi"] == 0.0


def test_s3_floor_boundary_not_hit():
    # ROI == 止损线（1.6 == 1.6）：严格小于 → 不命中
    at_floor = [_snap(spend=10000, gmv=16000), _snap(spend=10000, gmv=16000)]
    assert rule_s3_roi_floor(at_floor, 2.0) is None
    # ROI 达标（2.0 / 1.7 ≥ 1.6）：不命中
    ok = [_snap(spend=10000, gmv=20000), _snap(spend=10000, gmv=17000)]
    assert rule_s3_roi_floor(ok, 2.0) is None


# ---------------------------------------------------------------- S4 平台补贴

def test_s4_subsidy_hit():
    v = rule_s4_subsidy(_snap(spend=100, gmv=500, subsidy=200))
    assert v is not None and v.rule_id == "S4" and v.action == "record_subsidy"
    assert v.evidence["platform_subsidy"] == 200
    assert v.evidence["post_subsidy_roi_separate"] is True
    assert "补贴" in v.reason


def test_s4_subsidy_zero_no_hit():
    assert rule_s4_subsidy(_snap(subsidy=0)) is None
    assert rule_s4_subsidy({}) is None
    assert rule_s4_subsidy(_snap(subsidy=None)) is None


# ---------------------------------------------------------------- S5 余额检测

def test_s5_balance_hit():
    v = rule_s5_balance(9999, 10000)
    assert v is not None and v.rule_id == "S5" and v.action == "halt_new"
    assert "9999" in v.reason and "10000" in v.reason
    assert v.evidence["shortfall_fen"] == 1
    assert "告警人工充值" in v.suggested_actions
    assert rule_s5_balance(0, 10000).rule_id == "S5"
    assert rule_s5_balance(9999).rule_id == "S5"  # 默认阈值 ¥100=10000 分


def test_s5_balance_boundary_equal_not_hit():
    assert rule_s5_balance(10000, 10000) is None   # = 阈值不命中
    assert rule_s5_balance(10001, 10000) is None


# ---------------------------------------------------------------- S6 活跃数上限

def test_s6_active_cap_hit():
    v = rule_s6_active_cap(41, 40)
    assert v is not None and v.rule_id == "S6" and v.action == "stop_new"
    assert v.evidence["excess"] == 1
    assert "等自然淘汰" in v.suggested_actions
    assert rule_s6_active_cap(45).rule_id == "S6"  # 默认上限 40


def test_s6_active_cap_boundary_equal_not_hit():
    assert rule_s6_active_cap(40, 40) is None      # = 上限不命中
    assert rule_s6_active_cap(39, 40) is None


# ---------------------------------------------------------------- S7 预算三重硬约束

def test_budget_triple_each_dimension_over():
    v = check_budget_triple(600, 100, 50, 500, 1000, 2000)
    assert isinstance(v, BudgetVerdict)
    assert v.over_limit is True and v.rule == "single"
    assert v.spend_fen == 600 and v.budget_fen == 500
    assert "单笔预算" in v.reason
    v = check_budget_triple(100, 1200, 50, 500, 1000, 2000)
    assert v.rule == "daily"
    v = check_budget_triple(100, 900, 2500, 500, 1000, 2000)
    assert v.rule == "plan"


def test_budget_triple_zero_unlimited():
    v = check_budget_triple(999999, 999999, 999999)  # 全部 0=不限
    assert v.over_limit is False and v.rule == "none"
    v = check_budget_triple(999999, 999999, 999999, 0, 0, 0)
    assert v.over_limit is False
    # 单个维度 0=不限 不参与超限判定，其他维度约束仍生效
    v = check_budget_triple(600, 1500, 50, 0, 1000, 2000)  # single 不限；daily 超限
    assert v.over_limit is True and v.rule == "daily"
    assert v.spend_fen == 1500 and v.budget_fen == 1000


def test_budget_triple_multiple_over_first_wins():
    v = check_budget_triple(600, 1500, 3000, 500, 1000, 2000)
    assert v.rule == "single"  # 单笔/日/计划同时超限 → 取首个（single）
    assert v.over_limit is True


def test_budget_triple_all_pass():
    v = check_budget_triple(400, 800, 1500, 500, 1000, 2000)
    assert v.over_limit is False and v.rule == "none"
    assert v.reason
    # 未超限：spend_fen=最大花费维度，budget_fen=其预算
    assert v.spend_fen == 1500 and v.budget_fen == 2000


# ---------------------------------------------------------------- S8 一键全停

def test_kill_switch_true_and_app_config_override():
    assert kill_switch_enabled(True) is True
    assert kill_switch_enabled(True, False) is True   # 配置值不能覆盖已开启的总开关
    assert kill_switch_enabled(False, True) is True   # app_config 覆盖值开启
    assert kill_switch_enabled(False, "true") is True
    assert kill_switch_enabled(False, "1") is True
    assert kill_switch_enabled(False, "on") is True
    assert kill_switch_enabled(False, 1) is True


def test_kill_switch_false_and_string_values():
    assert kill_switch_enabled(False) is False
    assert kill_switch_enabled(False, None) is False
    assert kill_switch_enabled(False, False) is False
    assert kill_switch_enabled(False, "false") is False
    assert kill_switch_enabled(False, "0") is False
    assert kill_switch_enabled(False, "") is False
    assert kill_switch_enabled(False, "off") is False
    assert kill_switch_enabled(False, 0) is False
    assert kill_switch_enabled(False, "garbage") is False  # 未识别字符串视为关


# ---------------------------------------------------------------- StopLossEngine 集成

def test_engine_all_clear():
    snaps = [_snap(impressions=100, spend=1000, gmv=3000, subsidy=0, diagnosis="优秀")]
    res = _evaluate(snapshots=snaps)
    assert isinstance(res, EngineResult)
    assert res.verdicts == []
    assert res.halt_all is False
    assert res.actions == {}
    assert res.recommendations == []


def test_engine_kill_switch_short_circuit():
    res = _evaluate(kill_switch=True, account_balance_fen=0, active_count=99)
    assert res.halt_all is True
    assert [v.rule_id for v in res.verdicts] == ["S8"]     # 只返回 S8 verdict
    assert res.verdicts[0].action == "halt_all"
    assert res.actions == {"halt_all": 1}
    assert res.recommendations == ["S8 一键全停：终止所有投放/托管/采集动作"]


def test_engine_s5_s6_halt_all():
    res = _evaluate(account_balance_fen=5000, min_balance_fen=10000, active_count=45, active_cap=40)
    assert res.halt_all is True                            # S5 或 S6 命中 → halt_all
    ids = [v.rule_id for v in res.verdicts]
    assert "S5" in ids and "S6" in ids
    assert res.actions["halt_new"] == 1
    assert res.actions["stop_new"] == 1


def test_engine_verdicts_order_and_actions_summary():
    """全规则命中场景：verdicts 顺序稳定 S1→S2→S3→S4→S5→S6→S7，actions 汇总正确。"""
    snaps = [
        _snap(impressions=1000, spend=20000, gmv=5000, subsidy=0, diagnosis="良好"),
        _snap(impressions=2000, spend=30000, gmv=0, subsidy=300, diagnosis="1项待优化"),
    ]
    budget = {
        "single_spend_fen": 500000, "daily_spend_fen": 2000, "plan_spend_fen": 3000,
        "budget_single_fen": 100000, "budget_daily_fen": 50000, "budget_plan_fen": 80000,
    }
    res = _evaluate(
        snapshots=snaps,
        account_balance_fen=5000,
        active_count=41,
        budget=budget,
    )
    assert [v.rule_id for v in res.verdicts] == ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
    assert res.halt_all is True
    assert res.actions == {
        "pause": 2,                      # S1 + S7
        "record_optimization": 1,
        "degrade_material": 1,
        "record_subsidy": 1,
        "halt_new": 1,
        "stop_new": 1,
    }
    assert res.recommendations == [
        "S1 暂停该托管：换素材/调ROI",
        "S2 记录优化项，标记优先重投",
        "S3 降素材优先级/建议调ROI",
        "S4 补贴计入报表（补贴后ROI单独统计）",
        "S5 余额不足：暂停新托管，人工充值后恢复",
        "S6 投放中商品数超限：停止新增，等自然淘汰",
        "S7 预算超限：立即停止相关花钱动作",
    ]
    # S7 命中：evidence 带预算规则与数值
    s7 = res.verdicts[-1]
    assert s7.evidence["budget_rule"] == "single"
    assert s7.evidence["spend_fen"] == 500000 and s7.evidence["budget_fen"] == 100000


def test_engine_budget_s7_and_subsidy_flag():
    # S7 单独命中：verdicts 含 S7，但不触发 halt_all（仅 S5/S6/kill_switch）
    snaps = [_snap(impressions=100, spend=1000, gmv=3000, subsidy=0, diagnosis="优秀")]
    res = _evaluate(
        snapshots=snaps,
        budget={
            "single_spend_fen": 500000, "daily_spend_fen": 0, "plan_spend_fen": 0,
            "budget_single_fen": 100000, "budget_daily_fen": 0, "budget_plan_fen": 0,
        },
    )
    assert [v.rule_id for v in res.verdicts] == ["S7"]
    assert res.halt_all is False
    # budget 传 BudgetVerdict 实例同样生效
    res2 = _evaluate(snapshots=snaps, budget=check_budget_triple(600, 0, 0, 500, 0, 0))
    assert [v.rule_id for v in res2.verdicts] == ["S7"]
    # subsidy_only_report=False：不产出 S4 verdict（补贴由调用方另行处理）
    snaps_subsidy = [_snap(impressions=50, spend=100, gmv=200, subsidy=500, diagnosis="良好")]
    res3 = _evaluate(snapshots=snaps_subsidy, subsidy_only_report=False)
    assert "S4" not in [v.rule_id for v in res3.verdicts]
    # 无快照：S1/S2/S3/S4 跳过，S5/S6 仍评估
    res4 = _evaluate(account_balance_fen=5000, active_count=41)
    ids4 = [v.rule_id for v in res4.verdicts]
    assert "S1" not in ids4 and "S2" not in ids4 and "S3" not in ids4 and "S4" not in ids4
    assert "S5" in ids4 and "S6" in ids4
    assert res4.halt_all is True
