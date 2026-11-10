# -*- coding: utf-8 -*-
"""P0-2 批次 2（C1-b/c）：有效 source 集合与 scoped 聚合测试（round-153 实现；round-155 回修）。

覆盖 round-152 §三 + round-154 R154-1/3：
- 三有效源反例（双 ledger ROI=4 非 2.5 / 最新版无 event 淘汰旧版 / 最大并列无自动结果）；
- **R154-1 去重**：同 scoped 身份完整重放只贡献一次；同身份内容不同 → 确定性冲突；
- **R154-3 输入不变量**：bool/负金额/非法配对/未知算法版本/窗口非法 → AggregationInputError；
- 跨作用域与跨粒度隔离（各作用域独立真实 source）；
- 样本阈值、重复 source、来源依据一致、subject 过滤。
纯函数，无 DB。运行：cd backend && python -m pytest tests/test_report_aggregation.py -q
"""
import datetime
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.report import (  # noqa: E402
    AggregationInputError,
    SnapshotCandidate,
    SourceEvent,
    aggregate_events,
    effective_source_ids,
)

UTC = datetime.timezone.utc


def dt(d, h=0):
    return datetime.datetime(2026, 9, d, h, 0, 0, tzinfo=UTC)


def ev(source_id, *, ft="product_score", subject="product", key="p-1", gmv=0, spend=0,
       granularity="campaign", tenant=1, window=(dt(1), dt(2)), attribution="last_click",
       aggr="aggr_v1"):
    return SourceEvent(
        tenant_id=tenant, feedback_type=ft, subject_type=subject, subject_key=key,
        window_start=window[0], window_end=window[1], attribution_mode=attribution,
        aggregation_version=aggr, source_snapshot_id=source_id, granularity=granularity,
        gmv=gmv, spend=spend)


def cand(sid, t):
    return SnapshotCandidate(snapshot_id=sid, platform_updated_at=t)


# =====================================================================
# 三个有效源反例（round-148/152 §三.4；真实调用新实现）
# =====================================================================
def test_ce1_dual_ledger_roi_4_not_2_5():
    """双 ledger（旧新版均存在）→ 有效集仅最新版；ROI=400/100=4.000000（非 (100+400)/200=2.5）。"""
    candidates = {"S1": [cand(201, dt(1)), cand(202, dt(2))]}
    events = [ev(201, gmv=100, spend=100), ev(202, gmv=400, spend=100)]
    res = aggregate_events(events, candidates_by_identity=candidates,
                           feedback_type="product_score",
                           identity_of_source={201: "S1", 202: "S1"})
    assert res.effective_sources == (("S1", 202),)
    assert len(res.aggregates) == 1
    a = res.aggregates[0]
    assert a.outcome == "roi"
    assert a.value == Decimal("4.000000")
    assert a.numerator_gmv == 400 and a.denominator_spend == 100
    assert a.source_snapshot_ids == (202,)
    assert a.sample_count == 1


def test_ce2_newest_without_event_eliminates_old():
    """最新版（spend=0 未产 event）仍淘汰旧版有效性 → 无自动结果、旧 ROI 不再生效。"""
    candidates = {"S2": [cand(301, dt(3)), cand(302, dt(2))]}
    events = [ev(302, gmv=100, spend=50)]
    res = aggregate_events(events, candidates_by_identity=candidates,
                           feedback_type="product_score",
                           identity_of_source={301: "S2", 302: "S2"})
    assert res.effective_sources == (("S2", 301),)
    assert res.aggregates == ()
    assert res.manual_identities == ()


def test_ce3_max_tie_no_auto_result():
    """最大时间并列 → manual_required，不进有效集 → 无自动结果。"""
    candidates = {"S3": [cand(401, dt(2)), cand(402, dt(2))]}
    events = [ev(401, gmv=100, spend=50), ev(402, gmv=200, spend=50)]
    res = aggregate_events(events, candidates_by_identity=candidates,
                           feedback_type="product_score",
                           identity_of_source={401: "S3", 402: "S3"})
    assert res.effective_sources == (("S3", None),)
    assert res.manual_identities == ("S3",)
    assert res.aggregates == ()


# =====================================================================
# R154-1：同 scoped 身份去重（不重复累加金额）
# =====================================================================
def test_r1541_duplicate_identity_counts_once():
    """同身份完整重放只贡献一次：ROI 不变（修复前 gmv 累加到 600 → ROI=2.0）。"""
    candidates = {"A": [cand(1, dt(1))], "B": [cand(2, dt(1))]}
    idmap = {1: "A", 2: "B"}
    base = [ev(1, gmv=100, spend=100), ev(2, gmv=400, spend=100)]
    res_base = aggregate_events(base, candidates_by_identity=candidates,
                                feedback_type="product_score", identity_of_source=idmap)
    assert res_base.aggregates[0].value == Decimal("2.500000")
    assert res_base.aggregates[0].numerator_gmv == 500
    # 重复 A：应完全等价
    res_dup = aggregate_events([base[0], base[0], base[1]], candidates_by_identity=candidates,
                               feedback_type="product_score", identity_of_source=idmap)
    assert res_dup.aggregates[0].value == Decimal("2.500000")
    assert res_dup.aggregates[0].numerator_gmv == 500
    assert res_dup.aggregates[0].denominator_spend == 200
    assert res_dup.aggregates[0].source_snapshot_ids == (1, 2)
    assert res_dup.aggregates[0].sample_count == 2


def test_r1541_duplicate_different_content_conflict():
    """同身份内容不同（金额变化）→ 确定性冲突，不静默求和。"""
    candidates = {"A": [cand(1, dt(1))]}
    with pytest.raises(AggregationInputError):
        aggregate_events([ev(1, gmv=100, spend=100), ev(1, gmv=900, spend=100)],
                         candidates_by_identity=candidates,
                         feedback_type="product_score", identity_of_source={1: "A"})


def test_r1541_duplicate_sku_difference_idempotent():
    """SKU：同身份重放差额不变（修复前会重复累加）。"""
    candidates = {"K": [cand(11, dt(1))]}
    e = ev(11, ft="sku_margin", subject="sku", key="s-1", gmv=50, spend=100,
           granularity="shop_listing_sku")
    res = aggregate_events([e, e], candidates_by_identity=candidates,
                           feedback_type="sku_margin", identity_of_source={11: "K"})
    assert res.aggregates[0].value == Decimal("-50.000000")
    assert res.aggregates[0].numerator_gmv == 50 and res.aggregates[0].denominator_spend == 100


def test_r1541_duplicate_different_content_sku_conflict():
    """SKU 同身份但金额不同 → 冲突（不静默累加差额）。"""
    candidates = {"K": [cand(11, dt(1))]}
    e1 = ev(11, ft="sku_margin", subject="sku", key="s-1", gmv=50, spend=100,
            granularity="shop_listing_sku")
    e2 = ev(11, ft="sku_margin", subject="sku", key="s-1", gmv=500, spend=100,
            granularity="shop_listing_sku")
    with pytest.raises(AggregationInputError):
        aggregate_events([e1, e2], candidates_by_identity=candidates,
                         feedback_type="sku_margin", identity_of_source={11: "K"})


# =====================================================================
# R154-3：公开输入不变量
# =====================================================================
def test_r1543_bool_amount_rejected():
    with pytest.raises(AggregationInputError):
        ev(1, gmv=True, spend=100)


def test_r1543_negative_amount_rejected():
    with pytest.raises(AggregationInputError):
        ev(1, gmv=-100, spend=100)
    with pytest.raises(AggregationInputError):
        ev(1, gmv=100, spend=-1)


def test_r1543_subject_pairing_rejected():
    """五类 feedback ↔ subject 配对（对齐 ck_feedback_subject_map）。"""
    with pytest.raises(AggregationInputError):
        ev(1, ft="product_score", subject="material")
    with pytest.raises(AggregationInputError):
        ev(1, ft="sku_margin", subject="product", granularity="shop_listing_sku")


def test_r1543_unknown_aggregation_version_rejected():
    with pytest.raises(AggregationInputError):
        ev(1, aggr="aggr_unknown")


def test_r1543_bad_window_rejected():
    with pytest.raises(AggregationInputError):
        ev(1, window=(dt(2), dt(1)))          # 反向
    with pytest.raises(AggregationInputError):
        ev(1, window=(dt(1), dt(1)))          # 零长度
    with pytest.raises(AggregationInputError):
        ev(1, window=(datetime.datetime(2026, 9, 1), dt(2)))  # naive


def test_r1543_bad_ids_rejected():
    with pytest.raises(AggregationInputError):
        ev(1, tenant=0)
    with pytest.raises(AggregationInputError):
        ev(0)


def test_r1543_empty_subject_key_rejected():
    with pytest.raises(AggregationInputError):
        ev(1, key="")
    with pytest.raises(AggregationInputError):
        ev(1, attribution="")


# =====================================================================
# R156-1：公开入口元素运行时类型检查（字段访问前）
# =====================================================================
def test_r1561_duck_namespace_rejected():
    """字段齐全的非 SourceEvent（SimpleNamespace）→ AggregationInputError（不得被接受）。"""
    from dataclasses import asdict
    from types import SimpleNamespace
    duck = SimpleNamespace(**asdict(ev(1, gmv=100, spend=100)))
    with pytest.raises(AggregationInputError):
        aggregate_events([duck], candidates_by_identity={"A": [cand(1, dt(1))]},
                         feedback_type="product_score", identity_of_source={1: "A"})


def test_r1561_bare_object_rejected_not_attributeerror():
    """无字段 object() → AggregationInputError（精确：不得抛 AttributeError）。"""
    candidates = {"A": [cand(1, dt(1))]}
    with pytest.raises(AggregationInputError):
        aggregate_events([object()], candidates_by_identity=candidates,
                         feedback_type="product_score", identity_of_source={1: "A"})


def test_r1561_source_event_still_accepted():
    """正例：普通 SourceEvent 继续通过（类型门禁不影响合法输入）。"""
    candidates = {"A": [cand(1, dt(1))]}
    res = aggregate_events([ev(1, gmv=100, spend=100)], candidates_by_identity=candidates,
                           feedback_type="product_score", identity_of_source={1: "A"})
    assert res.aggregates[0].value == Decimal("1.000000")


# =====================================================================
# 跨作用域 / 跨粒度隔离（各作用域独立真实 source）
# =====================================================================
def test_cross_scope_isolation():
    """tenant/window/attribution 不同 → 各作用域独立真实 source，分开分组不混算。"""
    candidates = {"A": [cand(1, dt(1))], "B": [cand(2, dt(1))],
                  "C": [cand(3, dt(1))], "D": [cand(4, dt(1))]}
    idmap = {1: "A", 2: "B", 3: "C", 4: "D"}
    events = [
        ev(1, gmv=100, spend=100, tenant=1, window=(dt(1), dt(2)), attribution="last_click"),
        ev(2, gmv=400, spend=100, tenant=2, window=(dt(1), dt(2)), attribution="last_click"),
        ev(3, gmv=300, spend=100, tenant=1, window=(dt(3), dt(4)), attribution="last_click"),
        ev(4, gmv=200, spend=100, tenant=1, window=(dt(1), dt(2)), attribution="first_click"),
    ]
    res = aggregate_events(events, candidates_by_identity=candidates,
                           feedback_type="product_score", identity_of_source=idmap)
    assert len(res.aggregates) == 4
    assert sorted(a.value for a in res.aggregates) == [
        Decimal("1.000000"), Decimal("2.000000"), Decimal("3.000000"), Decimal("4.000000")]


def test_cross_scope_forged_source_negative():
    """伪造同源数据（同 source 声明他租户）→ tenant_of_source 不符 → 确定性拒绝。"""
    candidates = {"A": [cand(1, dt(1))]}
    events = [
        ev(1, gmv=100, spend=100, tenant=1, window=(dt(1), dt(2))),
        ev(1, gmv=400, spend=100, tenant=2, window=(dt(1), dt(2))),  # tenant 2 无该 S
    ]
    with pytest.raises(AggregationInputError):
        aggregate_events(events, candidates_by_identity=candidates,
                         feedback_type="product_score", identity_of_source={1: "A"},
                         tenant_of_source={1: 1})


def test_cross_granularity_filtered():
    candidates = {"A": [cand(1, dt(1))]}
    events = [ev(1, gmv=100, spend=100, granularity="campaign"),
              ev(1, gmv=999, spend=1, granularity="shop_listing")]  # 非 canonical → 过滤
    # 两条身份不同（granularity 属内容，不属身份），但非 canonical 的直接过滤
    res = aggregate_events(events, candidates_by_identity=candidates,
                           feedback_type="product_score", identity_of_source={1: "A"})
    assert len(res.aggregates) == 1
    assert res.aggregates[0].value == Decimal("1.000000")


def test_material_canonical_granularity():
    candidates = {"A": [cand(1, dt(1))]}
    res = aggregate_events(
        [ev(1, ft="material_score", subject="material", key="a-1", gmv=100, spend=50,
            granularity="campaign_asset")],
        candidates_by_identity=candidates, feedback_type="material_score",
        identity_of_source={1: "A"})
    assert res.aggregates[0].value == Decimal("2.000000")
    res2 = aggregate_events(
        [ev(1, ft="material_score", subject="material", key="a-1", gmv=100, spend=50,
            granularity="campaign")],
        candidates_by_identity=candidates, feedback_type="material_score",
        identity_of_source={1: "A"})
    assert res2.aggregates == ()


# =====================================================================
# SKU 跨 source 聚合 / 零消耗 / Decimal 上下文
# =====================================================================
def test_sku_cross_source_sum_difference():
    candidates = {"K": [cand(11, dt(1)), cand(12, dt(2))]}
    events = [
        ev(11, ft="sku_margin", subject="sku", key="s-1", gmv=100, spend=0,
           granularity="shop_listing_sku"),
        ev(12, ft="sku_margin", subject="sku", key="s-1", gmv=50, spend=100,
           granularity="shop_listing_sku"),
    ]
    res = aggregate_events(events, candidates_by_identity=candidates,
                           feedback_type="sku_margin",
                           identity_of_source={11: "K", 12: "K"})
    assert res.effective_sources == (("K", 12),)
    assert res.aggregates[0].outcome == "sku_margin"
    assert res.aggregates[0].value == Decimal("-50.000000")


def test_sku_large_int8_invariant_in_aggregation():
    """R154-2：聚合内 SKU 大额差额不受调用方 context 影响。"""
    import decimal
    candidates = {"K": [cand(11, dt(1))]}
    e = ev(11, ft="sku_margin", subject="sku", key="s-1", gmv=1234567890123456789,
           spend=0, granularity="shop_listing_sku")
    with decimal.localcontext() as ctx:
        ctx.prec = 10
        ctx.rounding = decimal.ROUND_DOWN
        res = aggregate_events([e], candidates_by_identity=candidates,
                               feedback_type="sku_margin", identity_of_source={11: "K"})
    assert res.aggregates[0].value == Decimal("1234567890123456789.000000")


def test_roi_zero_spend_typed_outcome():
    candidates = {"A": [cand(1, dt(1))]}
    res = aggregate_events([ev(1, gmv=100, spend=0)], candidates_by_identity=candidates,
                           feedback_type="product_score", identity_of_source={1: "A"})
    a = res.aggregates[0]
    assert a.outcome == "zero_spend_skipped" and a.value is None


# =====================================================================
# 样本 / 依据一致
# =====================================================================
def test_sample_count_distinct_sources():
    candidates = {"A": [cand(1, dt(1))], "B": [cand(2, dt(1))]}
    res = aggregate_events([ev(1, gmv=100, spend=100), ev(2, gmv=100, spend=100)],
                           candidates_by_identity=candidates,
                           feedback_type="product_score",
                           identity_of_source={1: "A", 2: "B"})
    a = res.aggregates[0]
    assert a.sample_count == 2 and a.source_snapshot_ids == (1, 2)


def test_effective_source_ids_manual_state():
    eff = effective_source_ids({
        "ok": [cand(1, dt(1)), cand(2, dt(2))],
        "tie": [cand(3, dt(1)), cand(4, dt(1))],
        "null": [cand(5, None)],
    })
    assert eff == {"ok": 2, "tie": None, "null": None}


def test_source_basis_consistency():
    candidates = {"A": [cand(1, dt(1))], "B": [cand(2, dt(1))]}
    events = [ev(1, gmv=100, spend=100, key="p1"), ev(2, gmv=300, spend=100, key="p1")]
    res = aggregate_events(events, candidates_by_identity=candidates,
                           feedback_type="product_score",
                           identity_of_source={1: "A", 2: "B"})
    a = res.aggregates[0]
    assert a.source_snapshot_ids == (1, 2)
    assert a.numerator_gmv == 400 and a.denominator_spend == 200
    assert a.value == Decimal("2.000000")
    assert dict(res.effective_sources) == {"A": 1, "B": 2}


def test_subject_filter_distinct_sources():
    """各 subject 用各自真实 source。"""
    candidates = {"A": [cand(1, dt(1))], "B": [cand(2, dt(1))]}
    events = [ev(1, key="p1", gmv=100, spend=100), ev(2, key="p2", gmv=200, spend=100)]
    res = aggregate_events(events, candidates_by_identity=candidates,
                           feedback_type="product_score",
                           identity_of_source={1: "A", 2: "B"}, subject_key="p2")
    assert len(res.aggregates) == 1 and res.aggregates[0].subject_key == "p2"


def test_unknown_feedback_type_rejected():
    with pytest.raises(AggregationInputError):
        aggregate_events([], candidates_by_identity={}, feedback_type="bogus",
                         identity_of_source={})
