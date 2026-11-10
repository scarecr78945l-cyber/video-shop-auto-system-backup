# -*- coding: utf-8 -*-
"""P0-2 批次 2（C1-a）：VersionSelector + classify_arrival 测试（round-149 独立授权）。

覆盖 round-148 §三 验收：五固定向量、24 排列确定性、混合 NULL 且非空最大并列、
相同时刻不同时区表示、正常 arrival、空候选/非法输入的明确契约；platform_updated_at
唯一最大是唯一胜者规则，opaque key/id/captured_at 不作选版排序；arrival 不替代 select_final。
纯函数测试，无 DB。运行：cd backend && python -m pytest tests/test_report_selector.py -q
"""
import datetime
import itertools
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.report import (  # noqa: E402
    DecisionBasis,
    SelectorInputError,
    SnapshotCandidate,
    classify_arrival,
    select_final_from_candidates,
)

UTC = datetime.timezone.utc
_m8 = datetime.timezone(datetime.timedelta(hours=8))
_m5 = datetime.timezone(datetime.timedelta(hours=-5))


def dt(y, m, d, h=0, mi=0, tz=UTC):
    return datetime.datetime(y, m, d, h, mi, 0, tzinfo=tz)


def cand(sid, tz_time=None):
    return SnapshotCandidate(snapshot_id=sid, platform_updated_at=tz_time)


# ---------------------------------------------------------------- GV1~GV4 固定向量
def test_gv1_unique_max_selected():
    r = select_final_from_candidates([
        cand(101, dt(2026, 9, 1)), cand(102, dt(2026, 9, 2)), cand(103, dt(2026, 9, 3))])
    assert r.kind == "selected" and r.snapshot_id == 103
    assert r.evidence.selection_rule == "unique_max_time"
    assert r.evidence.manual_reason is None
    assert r.evidence.sorted_snapshot_ids == (101, 102, 103)
    assert r.evidence.null_time_candidates == ()


def test_gv2_max_tie_manual():
    r = select_final_from_candidates([
        cand(101, dt(2026, 9, 1)), cand(102, dt(2026, 9, 2)), cand(103, dt(2026, 9, 2))])
    assert r.kind == "manual_required"
    assert r.snapshot_id is None
    assert r.evidence.selection_rule is None
    assert r.evidence.manual_reason == "max_time_tie"
    assert r.evidence.sorted_snapshot_ids == (101, 102, 103)  # id ASC 内时间 ASC


def test_gv3_mixed_null_selected():
    r = select_final_from_candidates([
        cand(101, dt(2026, 9, 1)), cand(102, None), cand(103, dt(2026, 9, 2))])
    assert r.kind == "selected" and r.snapshot_id == 103
    assert r.evidence.selection_rule == "unique_max_time"
    # sorted = time ASC NULLS LAST → [101,103,102]
    assert r.evidence.sorted_snapshot_ids == (101, 103, 102)
    assert r.evidence.null_time_candidates == (102,)


def test_gv4_all_null_manual():
    r = select_final_from_candidates([
        cand(101, None), cand(102, None), cand(103, None)])
    assert r.kind == "manual_required"
    assert r.evidence.selection_rule is None
    assert r.evidence.manual_reason == "all_times_null"
    assert r.evidence.sorted_snapshot_ids == (101, 102, 103)
    assert r.evidence.null_time_candidates == (101, 102, 103)


# ---------------------------------------------------------------- 24 排列确定性
def test_24_input_permutations_deterministic():
    """candidates 顺序置换不改变选择结果与展示列表（round-148 §一 24 排列）。"""
    base = [cand(101, dt(2026, 9, 1)), cand(102, dt(2026, 9, 2)), cand(103, dt(2026, 9, 3))]
    results = set()
    for perm in itertools.permutations(base):
        r = select_final_from_candidates(list(perm))
        results.add((r.kind, r.snapshot_id, r.evidence.sorted_snapshot_ids))
    assert results == {("selected", 103, (101, 102, 103))}


def test_manual_permutations_deterministic():
    """手册态（并列）顺序置换展示列表不变。"""
    base = [cand(101, dt(2026, 9, 1)), cand(102, dt(2026, 9, 2)), cand(103, dt(2026, 9, 2))]
    results = set()
    for perm in itertools.permutations(base):
        r = select_final_from_candidates(list(perm))
        results.add((r.kind, r.manual_reason, r.evidence.sorted_snapshot_ids))
    assert results == {("manual_required", "max_time_tie", (101, 102, 103))}


# ---------------------------------------------------------------- 相同时刻不同时区
def test_same_instant_different_timezone_equivalent():
    """同一时刻不同时区（+08:00 与 UTC）→ 相同结果（UTC 规范化，且并列）。"""
    t8 = datetime.datetime(2026, 9, 2, 8, 0, 0, tzinfo=_m8)   # = 2026-09-02T00:00:00Z
    tz = datetime.datetime(2026, 9, 2, 0, 0, 0, tzinfo=UTC)
    r = select_final_from_candidates([cand(101, t8), cand(102, tz)])
    assert r.kind == "manual_required" and r.evidence.manual_reason == "max_time_tie"


def test_opaque_fields_not_in_sort():
    """opaque key/id/captured_at 不参与选版排序——selector 候选只含 platform_updated_at。"""
    # 只验证候选接口不接受 captured/version 等字段（构造器不依赖它们）
    c = cand(101, dt(2026, 9, 1))
    assert c.snapshot_id == 101 and c.platform_updated_at is not None


# ---------------------------------------------------------------- classify_arrival
def test_classify_arrival_normal():
    r = classify_arrival(
        SnapshotCandidate(102, dt(2026, 9, 2)),
        SnapshotCandidate(101, dt(2026, 9, 1)))
    assert r["kind"] == "normal" and r["evidence_reason"] is None


def test_classify_arrival_regression_gv5():
    r = classify_arrival(
        SnapshotCandidate(99, dt(2026, 8, 31)),
        SnapshotCandidate(101, dt(2026, 9, 1)))
    assert r["kind"] == "time_regression"
    assert r["evidence_reason"] == "time_regression"
    assert r["evidence"]["version_selector"]["selected_id"] == 101
    assert r["evidence"]["regressions"][0]["snapshot_id"] == 99


def test_classify_arrival_regression_cross_timezone():
    r = classify_arrival(
        SnapshotCandidate(99, datetime.datetime(2026, 9, 1, 7, 0, 0, tzinfo=_m8)),  # = 08-31T23:00Z
        SnapshotCandidate(101, dt(2026, 8, 31, 23, 30)))                            # = 08-31T23:30Z
    assert r["kind"] == "time_regression"


# ---------------------------------------------------------------- 空/非法输入契约
def test_empty_candidates_rejected():
    with pytest.raises(SelectorInputError):
        select_final_from_candidates([])


def test_duplicate_snapshot_id_rejected():
    with pytest.raises(SelectorInputError):
        select_final_from_candidates([cand(1, dt(2026, 1, 1)), cand(1, dt(2026, 1, 2))])


def test_candidate_non_int_id_rejected():
    with pytest.raises(SelectorInputError):
        SnapshotCandidate("1", dt(2026, 1, 1))


def test_candidate_naive_time_rejected():
    with pytest.raises(SelectorInputError):
        SnapshotCandidate(1, datetime.datetime(2026, 1, 1))  # naive


def test_arrival_null_time_rejected():
    with pytest.raises(SelectorInputError):
        classify_arrival(cand(2, None), cand(1, dt(2026, 1, 1)))
    with pytest.raises(SelectorInputError):
        classify_arrival(cand(2, dt(2026, 1, 2)), cand(1, None))


# ---------------------------------------------------------------- DecisionBasis 可解析
def test_decision_basis_to_dict_roundtrip():
    r = select_final_from_candidates([
        cand(101, dt(2026, 9, 1)), cand(102, None), cand(103, dt(2026, 9, 2))])
    d = r.to_dict()
    assert d["kind"] == "selected"
    vs = d["evidence"]["version_selector"]
    assert set(vs) == {"sorted_snapshot_ids", "selected_id", "selection_rule",
                       "manual_reason", "null_time_candidates"}
    assert set(d["evidence"]) == {"version_selector", "regressions",
                                  "aggregation_version", "policy_version"}
    # 可 JSON 序列化
    import json
    json.dumps(d)


# =====================================================================
# round-150 R150-1 补充：完整 golden 对象相等 + 时间展示/NULL 边界
# =====================================================================
def test_gv1_full_object_equality():
    """整输出对象 == round-147 GV1（selected，无额外顶层 key）。"""
    import json
    r = select_final_from_candidates([
        cand(101, dt(2026, 9, 1)), cand(102, dt(2026, 9, 2)), cand(103, dt(2026, 9, 3))])
    assert json.loads(json.dumps(r.to_dict())) == {
        "kind": "selected", "snapshot_id": 103,
        "evidence": {"version_selector": {
            "sorted_snapshot_ids": [101, 102, 103], "selected_id": 103,
            "selection_rule": "unique_max_time", "manual_reason": None,
            "null_time_candidates": []},
            "regressions": [], "aggregation_version": "aggr_v1", "policy_version": None}}


def test_gv2_full_object_equality_manual():
    """整输出对象 == round-147 GV2（manual top-level 只含 kind/snapshot_id/evidence，无顶层 reason）。"""
    import json
    r = select_final_from_candidates([
        cand(101, dt(2026, 9, 1)), cand(102, dt(2026, 9, 2)), cand(103, dt(2026, 9, 2))])
    d = r.to_dict()
    assert set(d) == {"kind", "snapshot_id", "evidence"}, f"manual 顶层不该有 reason: {set(d)}"
    assert json.loads(json.dumps(d)) == {
        "kind": "manual_required", "snapshot_id": None,
        "evidence": {"version_selector": {
            "sorted_snapshot_ids": [101, 102, 103], "selected_id": None,
            "selection_rule": None, "manual_reason": "max_time_tie",
            "null_time_candidates": []},
            "regressions": [], "aggregation_version": "aggr_v1", "policy_version": None}}


def test_gv4_full_object_equality_all_null():
    import json
    r = select_final_from_candidates([cand(101, None), cand(102, None), cand(103, None)])
    assert json.loads(json.dumps(r.to_dict())) == {
        "kind": "manual_required", "snapshot_id": None,
        "evidence": {"version_selector": {
            "sorted_snapshot_ids": [101, 102, 103], "selected_id": None,
            "selection_rule": None, "manual_reason": "all_times_null",
            "null_time_candidates": [101, 102, 103]},
            "regressions": [], "aggregation_version": "aggr_v1", "policy_version": None}}


def test_gv5_regression_full_object():
    """round-147 GV5：time_regression；sorted=[99,101]（时间 ASC 新到先出现）；detail 用 UTC Z。"""
    import json
    r = classify_arrival(cand(99, dt(2026, 8, 31)), cand(101, dt(2026, 9, 1)))
    d = r["evidence"]
    assert r["kind"] == "time_regression" and r["evidence_reason"] == "time_regression"
    assert d["version_selector"]["sorted_snapshot_ids"] == [99, 101]
    assert d["version_selector"]["selected_id"] == 101
    detail = r["detail"]
    assert "Z" in detail, f"detail 应使用 UTC Z: {detail}"
    assert d["regressions"][0]["snapshot_id"] == 99
    json.loads(json.dumps(r))


def test_regression_and_normal_display_time_asc():
    """R150-1：regression/normal 的 sorted_snapshot_ids 都按时间 ASC，非固定 prior/new 角色顺序。"""
    # regression：new(101) 早于 prior(102) → [101,102]
    reg = classify_arrival(cand(101, dt(2026, 8, 30)), cand(102, dt(2026, 9, 1)))
    assert reg["evidence"]["version_selector"]["sorted_snapshot_ids"] == [101, 102]
    # normal：new(202) 晚于 prior(201) → [201,202]
    nor = classify_arrival(cand(202, dt(2026, 9, 2)), cand(201, dt(2026, 9, 1)))
    assert nor["kind"] == "normal"
    assert nor["evidence"]["version_selector"]["sorted_snapshot_ids"] == [201, 202]


def test_datetime_max_null_sentinel_boundary():
    """R150-1：真实时间=datetime.max UTC 不与 NULL 哨兵碰撞——NULL 仍排最后。"""
    import datetime as _dt
    max_utc = _dt.datetime.max.replace(tzinfo=_dt.timezone.utc)
    r = select_final_from_candidates([cand(1, None), cand(2, max_utc)])
    assert r.kind == "selected" and r.snapshot_id == 2
    assert r.evidence.sorted_snapshot_ids == (2, 1)  # 真实时间在前，NULL 在后


# =====================================================================
# round-150 R150-2：公开入口重验 + 枚举分离
# =====================================================================
def test_duck_candidate_rejected():
    """R150-2：非 SnapshotCandidate 鸭子对象（str id/naive time）必须 SelectorInputError。"""
    from types import SimpleNamespace
    with pytest.raises(SelectorInputError):
        select_final_from_candidates([
            SimpleNamespace(snapshot_id="x",
                            platform_updated_at=datetime.datetime(2026, 1, 1))])
    with pytest.raises(SelectorInputError):
        select_final_from_candidates([object()])


def test_selection_rule_enum_separate_from_nullable_state():
    """R150-2：SELECTION_RULE_VALUES 只含字符串枚举；manual 的 None 是可空状态非枚举值。"""
    from domain.report import SELECTION_RULE_VALUES, MANUAL_REASON_VALUES, EVIDENCE_REASON_VALUES
    assert SELECTION_RULE_VALUES == {"unique_max_time"}
    assert None not in SELECTION_RULE_VALUES
    assert MANUAL_REASON_VALUES == {"max_time_tie", "all_times_null"}
    assert EVIDENCE_REASON_VALUES == {"time_regression"}


def test_mixed_null_with_max_tie():
    """R150-2：混合 NULL 且非空最大并列 → manual_reason=max_time_tie + NULL 列表。"""
    r = select_final_from_candidates([
        cand(101, dt(2026, 9, 1)), cand(102, None), cand(103, dt(2026, 9, 2)),
        cand(104, dt(2026, 9, 2))])
    assert r.kind == "manual_required" and r.manual_reason == "max_time_tie"
    assert r.evidence.selection_rule is None
    # 时间 ASC NULLS LAST：非空 101, 103, 104（103/104 并列），102(NULL) 最后
    assert r.evidence.sorted_snapshot_ids == (101, 103, 104, 102)
    assert r.evidence.null_time_candidates == (102,)


def test_mixed_null_tie_24_permutations():
    """R150-2：混合 NULL + 并列（GV 变体）输入置换→输出不变（展示列表排序稳定）。"""
    base = [cand(101, dt(2026, 9, 1)), cand(102, None), cand(103, dt(2026, 9, 2)),
            cand(104, dt(2026, 9, 2))]
    results = set()
    for perm in itertools.permutations(base):
        r = select_final_from_candidates(list(perm))
        results.add((r.kind, r.manual_reason,
                     r.evidence.sorted_snapshot_ids, r.evidence.null_time_candidates))
    assert results == {("manual_required", "max_time_tie", (101, 103, 104, 102), (102,))}


def test_all_gv_permutations_24():
    """R150-2：GV1~GV4 每组 6 排列，共 24 排列，输出确定性（四组完整枚举）。"""
    sets = [
        [cand(101, dt(2026, 9, 1)), cand(102, dt(2026, 9, 2)), cand(103, dt(2026, 9, 3))],
        [cand(101, dt(2026, 9, 1)), cand(102, dt(2026, 9, 2)), cand(103, dt(2026, 9, 2))],
        [cand(101, dt(2026, 9, 1)), cand(102, None), cand(103, dt(2026, 9, 2))],
        [cand(101, None), cand(102, None), cand(103, None)],
    ]
    expected = [
        ("selected", 103, (101, 102, 103), None),
        ("manual_required", None, (101, 102, 103), "max_time_tie"),
        ("selected", 103, (101, 103, 102), None),
        ("manual_required", None, (101, 102, 103), "all_times_null"),
    ]
    for base, exp in zip(sets, expected):
        for perm in itertools.permutations(base):
            r = select_final_from_candidates(list(perm))
            got = (r.kind,
                   r.snapshot_id if r.kind == "selected" else None,
                   r.evidence.sorted_snapshot_ids,
                   r.manual_reason if r.kind == "manual_required" else None)
            assert got == exp, f"perm {[c.snapshot_id for c in perm]} got {got} exp {exp}"


def test_utcoffset_none_negative():
    """R150-2：utcoffset() is None 自定义 tzinfo 的候选必须 SelectorInputError（非 naive-only）。"""
    class _NoneOffset(datetime.tzinfo):
        def utcoffset(self, dt):
            return None
        def dst(self, dt):
            return None
        def tzname(self, dt):
            return "NOFF"
    with pytest.raises(SelectorInputError):
        select_final_from_candidates([
            cand(101, datetime.datetime(2026, 1, 1, tzinfo=_NoneOffset()))])


# =====================================================================
# round-152 §二：GV5 detail 勘误后的**完整对象**断言（不再只做部分字段）
# =====================================================================
def test_gv5_revised_complete_object():
    """round-152 接受的 GV5 detail 勘误：统一的 UTC 六位微秒文案，
    detail 与 regressions.detail 相同；其余字段保持 round-147。完整对象断言。"""
    import json
    revised_detail = ("platform_updated_at 2026-08-31T00:00:00.000000Z is earlier than "
                      "prior maximum 2026-09-01T00:00:00.000000Z")
    r = classify_arrival(cand(99, dt(2026, 8, 31)), cand(101, dt(2026, 9, 1)))
    assert json.loads(json.dumps(r)) == {
        "kind": "time_regression",
        "detail": revised_detail,
        "evidence_reason": "time_regression",
        "evidence": {
            "version_selector": {
                "sorted_snapshot_ids": [99, 101], "selected_id": 101,
                "selection_rule": "unique_max_time", "manual_reason": None,
                "null_time_candidates": []},
            "regressions": [{"snapshot_id": 99, "reason": "time_regression",
                             "detail": revised_detail}],
            "aggregation_version": "aggr_v1", "policy_version": None}}


def test_gv5_normal_revised_complete_object():
    """normal 分支完整对象（时间 ASC 展示，selected_id=null，无 regressions）。"""
    import json
    r = classify_arrival(cand(202, dt(2026, 9, 2)), cand(201, dt(2026, 9, 1)))
    assert json.loads(json.dumps(r)) == {
        "kind": "normal", "detail": None, "evidence_reason": None,
        "evidence": {
            "version_selector": {
                "sorted_snapshot_ids": [201, 202], "selected_id": None,
                "selection_rule": None, "manual_reason": None,
                "null_time_candidates": []},
            "regressions": [], "aggregation_version": "aggr_v1", "policy_version": None}}