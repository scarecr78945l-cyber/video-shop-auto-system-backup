# -*- coding: utf-8 -*-
"""T5: CID 公式引擎 pytest 测试（round-65；round-67 R66-1~R66-4 聚焦回修）。

覆盖 cid-engine-spec.md §五 黄金样例、canonical serialization 不变量、envelope 用例与 .5 分边界；
round-67 新增：读写 adapter（R66-1）、quantize_ratio 冻结 context 与 numeric(12,6) 范围（R66-2）、
P_ZERO 真实可达输入（R66-3）、全入口 NaN/±Infinity 拒绝（R66-4）。
运行：cd backend && python -m pytest tests/test_cid_engine.py -q
"""
import os
import sys
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, getcontext

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.cid import (  # noqa: E402
    CIDError,
    canonical,
    compute,
    cost_snapshot_persist,
    cost_snapshot_to_compute,
    pricing_decision_persist,
    quantize_numeric18_6,
    quantize_ratio,
)

GOLDEN_INPUTS = {
    "K": "2199", "J": "13.194", "I": "153.930", "H": "180", "G": "130",
    "L": "83.562", "U": "0.5",
}
GOLDEN_RATES = {
    "roi_buffer": "0.1", "consumption_rebate_rate": "0.05",
    "tech_hi": "0.036", "tech_lo": "0.055",
}
GOLDEN_VALUES = {
    "M": "1638.314",
    "N": "1.34223354009060534183312844790436998035785569799196002719869",
    "O": "1.44223354009060534183312844790436998035785569799196002719869",
    "P": "1524.71838913263129988876904209077295993273155249248846108953",
    "Q": "76.2359194566315649944384521045386479966365776246244230544765",
    "R": "-41.781",
    "S": "231.612530324000265105669410013765688063905025132135961964947",
    "T": "0.151905120299465930780868549195949287016521859444202856705946",
    "V": "3049.43677826526259977753808418154591986546310498497692217906",
    "X": "0.721116770045302670916564223952184990178927848995980013599345",
}


@pytest.fixture(scope="module")
def golden():
    return compute(GOLDEN_INPUTS, **GOLDEN_RATES)


def test_golden_status_and_bid(golden):
    assert golden["status"] == "calculated"
    assert golden["blocking_error"] is None
    assert golden["bid_rounded_cents"] == 1525
    assert golden["values"]["S"].endswith("947")


@pytest.mark.parametrize("key,want", GOLDEN_VALUES.items())
def test_golden_values_exact(golden, key, want):
    assert golden["values"][key] == want


def test_canonical_invariants():
    assert canonical("1") == canonical("1.0") == canonical("1.00") == "1"
    assert canonical("-0.000") == "0"
    assert canonical("1E+3") == "1000"
    assert canonical("1525.0") == "1525"
    assert canonical("1638.314000") == "1638.314"


def test_compact_vs_db_scale_equal():
    def db_scale(v):
        d = Decimal(v)
        if v == "0.5":
            return "0.5000"
        return format(d.quantize(Decimal("0.000001")), "f")

    env_db = compute({k: db_scale(v) for k, v in GOLDEN_INPUTS.items()}, **GOLDEN_RATES)
    env_compact = compute(GOLDEN_INPUTS, **GOLDEN_RATES)
    assert env_db["values"] == env_compact["values"]
    assert env_db["bid_rounded_cents"] == env_compact["bid_rounded_cents"]


def test_blocking_cases():
    cases = [
        ({"K": "560.686"}, "M_NON_POSITIVE"),  # M = 0 精确零毛利
        ({"G": "2000"}, "M_NON_POSITIVE"),
        ({"K": "-1000", "J": "-11000", "I": "0", "H": "0", "G": "0", "L": "0"}, "O_ZERO"),
        ({"U": "0"}, "U_NON_POSITIVE"),
        ({"U": "-0.5"}, "U_NON_POSITIVE"),
    ]
    for mutate, block in cases:
        inp = dict(GOLDEN_INPUTS)
        inp.update(mutate)
        e = compute(inp, **GOLDEN_RATES)
        assert e["status"] == "insufficient_data"
        assert e["blocking_error"] == block
        assert e["values"] is None and e["bid_rounded_cents"] is None


def test_p_zero_real_reachable():
    """R66-3：P_ZERO 用真实可达输入独立命中（K=0,J=-1,其余成本=0,roi_buffer=0.1）。

    M=0-(-1)-0-0-0-0=1>0；N=0/1=0；O=0+0.1=0.1；P=0/0.1=0 -> P_ZERO。
    """
    e = compute({"K": "0", "J": "-1", "I": "0", "H": "0", "G": "0", "L": "0", "U": "0.5"},
                roi_buffer="0.1", consumption_rebate_rate="0.05",
                tech_hi="0.036", tech_lo="0.055")
    assert e["status"] == "insufficient_data"
    assert e["blocking_error"] == "P_ZERO"
    assert e["values"] is None and e["bid_rounded_cents"] is None


def test_l_missing_defaulted():
    inp = {k: v for k, v in GOLDEN_INPUTS.items() if k != "L"}
    e = compute(inp, **GOLDEN_RATES)
    assert e["status"] == "calculated"
    assert "FIELD_DEFAULTED" in e["quality_flags"]
    assert e["field_details"] == [{"field": "L", "source_state": "missing", "default_applied": True}]
    assert e["values"]["M"] == "1721.876"


def test_required_missing():
    e = compute({"K": "2199", "J": "13.194"})
    assert e["status"] == "insufficient_data"
    assert e["blocking_error"] == "REQUIRED_FIELD_MISSING"
    assert len(e["field_details"]) == 4


def test_rebate_not_applicable():
    e = compute(GOLDEN_INPUTS, roi_buffer="0.1", consumption_rebate_rate="0",
                tech_hi="0.036", tech_lo="0.055")
    assert e["status"] == "calculated"
    assert "REBATE_NOT_APPLICABLE" in e["business_flags"]
    assert e["values"]["Q"] == "0"


def test_rebate_source_missing():
    e = compute(GOLDEN_INPUTS, roi_buffer="0.1", consumption_rebate_rate=None,
                tech_hi="0.036", tech_lo="0.055")
    assert e["status"] == "calculated"
    assert "REBATE_SOURCE_MISSING" in e["quality_flags"]
    assert e["values"]["Q"] == "0"


def test_s_non_positive_business_flag():
    e = compute({"K": "100", "J": "50", "I": "20", "H": "15", "G": "14", "L": "0.5", "U": "0.5"},
                roi_buffer="0.1", consumption_rebate_rate="0.05",
                tech_hi="0.036", tech_lo="0.055")
    assert e["status"] == "calculated"
    assert "S_NON_POSITIVE" in e["business_flags"]
    assert e["blocking_error"] is None
    assert e["bid_rounded_cents"] is not None


@pytest.mark.parametrize("p_str,want", [("1.5", 2), ("2.5", 3), ("3.5", 4),
                                        ("1524.5", 1525), ("1525.5", 1526)])
def test_half_up_boundary(p_str, want):
    e = compute({"K": p_str, "J": "0", "I": "0", "H": "0", "G": "0", "L": "0", "U": "1"},
                roi_buffer="0.0", consumption_rebate_rate="0.05",
                tech_hi="0", tech_lo="0")
    assert e["bid_rounded_cents"] == want


def test_quantize_ratio_no_reflow():
    e = compute(GOLDEN_INPUTS, **GOLDEN_RATES)
    q = {k: quantize_ratio(e["values"][k]) for k in ("N", "O", "T", "X")}
    for v in q.values():
        assert str(v) == format(v, "f")
        assert v.as_tuple().exponent >= -6


def test_float_input_rejected():
    with pytest.raises(CIDError):
        compute({"K": 2199.0, "J": "13.194", "I": "153.930", "H": "180", "G": "130",
                 "L": "83.562", "U": "0.5"}, **GOLDEN_RATES)


# ---------------------------------------------------------------------------
# R66-1：cost_snapshots / pricing_decisions 读写 adapter
# ---------------------------------------------------------------------------
def _rates():
    return {"roi_buffer": "0.1", "consumption_rebate_rate": "0.05",
            "tech_hi": "0.036", "tech_lo": "0.055"}


def test_adapter_cost_snapshot_to_compute():
    row = {"k_price": "2199", "j_service_fee": "13.194", "i_refund_reserve": "153.930",
           "h_shipping": "180", "g_product_cost": "130", "l_tax": "83.562"}
    ad = cost_snapshot_to_compute(row, "0.5", _rates())
    assert ad["inputs"] == {"K": "2199", "J": "13.194", "I": "153.930", "H": "180",
                            "G": "130", "L": "83.562", "U": "0.5"}
    env = compute(ad["inputs"], roi_buffer=ad["roi_buffer"],
                  consumption_rebate_rate=ad["consumption_rebate_rate"],
                  tech_hi=ad["tech_hi"], tech_lo=ad["tech_lo"])
    assert env["bid_rounded_cents"] == 1525


def test_adapter_l_tax_missing_defaulted():
    row = {"k_price": "2199", "j_service_fee": "13.194", "i_refund_reserve": "153.930",
           "h_shipping": "180", "g_product_cost": "130"}
    ad = cost_snapshot_to_compute(row, "0.5", _rates())
    assert "L" not in ad["inputs"]
    env = compute(ad["inputs"], roi_buffer=ad["roi_buffer"],
                  consumption_rebate_rate=ad["consumption_rebate_rate"],
                  tech_hi=ad["tech_hi"], tech_lo=ad["tech_lo"])
    assert "FIELD_DEFAULTED" in env["quality_flags"]


def test_adapter_missing_required_raises():
    with pytest.raises(CIDError):
        cost_snapshot_to_compute({"k_price": "2199"}, "0.5", _rates())


def test_adapter_cost_snapshot_persist():
    env = compute(GOLDEN_INPUTS, **GOLDEN_RATES)
    proj = cost_snapshot_persist(env)
    assert set(proj) == {"ad_pre_margin", "consumption_rebate", "technical_rebate"}
    assert str(proj["ad_pre_margin"]) == "1638.314000"
    assert str(proj["consumption_rebate"]) == "76.235919"
    assert str(proj["technical_rebate"]) == "-41.781000"


def test_adapter_pricing_decision_persist():
    """R68-1：cid_inputs 12 键 exact-set + 数值 canonical + formula_version 原样。"""
    row = {"k_price": "2199", "j_service_fee": "13.194", "i_refund_reserve": "153.930",
           "h_shipping": "180", "g_product_cost": "130", "l_tax": "83.562"}
    ad = cost_snapshot_to_compute(row, "0.5", _rates())
    env = compute(ad["inputs"], roi_buffer=ad["roi_buffer"],
                  consumption_rebate_rate=ad["consumption_rebate_rate"],
                  tech_hi=ad["tech_hi"], tech_lo=ad["tech_lo"])
    proj = pricing_decision_persist(env, ad)
    assert set(proj) == {"bid_unrounded", "bid_rounded_cents", "rounding_mode",
                         "cid_inputs", "cid_results"}
    assert str(proj["bid_unrounded"]) == "1524.718389"
    assert proj["bid_rounded_cents"] == 1525
    assert proj["rounding_mode"] == "ROUND_HALF_UP"
    assert proj["cid_results"]["values"] == env["values"]
    # 12 键 exact-set（K/J/I/H/G/L/U + 4 费率 + formula_version）
    assert set(proj["cid_inputs"]) == {
        "K", "J", "I", "H", "G", "L", "U",
        "roi_buffer", "consumption_rebate_rate", "tech_hi", "tech_lo", "formula_version"}
    assert proj["cid_inputs"]["K"] == "2199"
    assert proj["cid_inputs"]["roi_buffer"] == "0.1"
    assert proj["cid_inputs"]["consumption_rebate_rate"] == "0.05"
    assert proj["cid_inputs"]["formula_version"] == "v5"


def test_adapter_persist_rebate_none():
    """R68-1：consumption_rebate_rate=None -> cid_inputs JSON null + REBATE_SOURCE_MISSING。"""
    row = {"k_price": "2199", "j_service_fee": "13.194", "i_refund_reserve": "153.930",
           "h_shipping": "180", "g_product_cost": "130", "l_tax": "83.562"}
    ad = cost_snapshot_to_compute(row, "0.5", {
        "roi_buffer": "0.1", "consumption_rebate_rate": None,
        "tech_hi": "0.036", "tech_lo": "0.055"})
    env = compute(ad["inputs"], roi_buffer=ad["roi_buffer"],
                  consumption_rebate_rate=ad["consumption_rebate_rate"],
                  tech_hi=ad["tech_hi"], tech_lo=ad["tech_lo"])
    proj = pricing_decision_persist(env, ad)
    assert proj["cid_inputs"]["consumption_rebate_rate"] is None
    assert "REBATE_SOURCE_MISSING" in env["quality_flags"]


def test_adapter_persist_non_calculated():
    e_p0 = compute({"K": "0", "J": "-1", "I": "0", "H": "0", "G": "0", "L": "0", "U": "0.5"},
                   roi_buffer="0.1", consumption_rebate_rate="0.05",
                   tech_hi="0.036", tech_lo="0.055")
    assert cost_snapshot_persist(e_p0) == {}
    row = {"k_price": "2199", "j_service_fee": "13.194", "i_refund_reserve": "153.930",
           "h_shipping": "180", "g_product_cost": "130", "l_tax": "83.562"}
    ad = cost_snapshot_to_compute(row, "0.5", _rates())
    # R68-1：非 calculated -> 空投影（不创建 pricing_decisions，避免违反 cid_inputs/cid_results NOT NULL）
    assert pricing_decision_persist(e_p0, ad) == {}


# ---------------------------------------------------------------------------
# R66-2：quantize_ratio 冻结 context + numeric(12,6) 范围
# ---------------------------------------------------------------------------
def test_quantize_ratio_ambient_context_isolated():
    old = getcontext().prec
    getcontext().prec = 6
    try:
        q = quantize_ratio("123456.1234567")
        assert str(q) == "123456.123457"
    finally:
        getcontext().prec = old


def test_quantize_ratio_rounding_frozen():
    old = getcontext().rounding
    getcontext().rounding = ROUND_DOWN
    try:
        q = quantize_ratio("0.0000005")
        assert str(q) == "0.000001"
    finally:
        getcontext().rounding = old


def test_quantize_ratio_range():
    assert str(quantize_ratio("999999.9999994")) == "999999.999999"
    with pytest.raises(CIDError):
        quantize_ratio("1000000.0")          # 7 位整数
    with pytest.raises(CIDError):
        quantize_ratio("999999.9999995")     # 舍入进位到 7 位整数


def test_quantize_numeric18_6():
    assert str(quantize_numeric18_6("1638.314")) == "1638.314000"


# ---------------------------------------------------------------------------
# R66-4：全入口拒绝 NaN/±Infinity
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_compute_rejects_non_finite_required(bad):
    inp = dict(GOLDEN_INPUTS)
    inp["K"] = bad
    with pytest.raises(CIDError):
        compute(inp, **GOLDEN_RATES)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_compute_rejects_non_finite_l(bad):
    inp = dict(GOLDEN_INPUTS)
    inp["L"] = bad
    with pytest.raises(CIDError):
        compute(inp, **GOLDEN_RATES)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_canonical_rejects_non_finite(bad):
    with pytest.raises(CIDError):
        canonical(bad)


@pytest.mark.parametrize("bad", ["NaN", "-Infinity"])
def test_quantize_rejects_non_finite(bad):
    with pytest.raises(CIDError):
        quantize_ratio(bad)


# ---------------------------------------------------------------------------
# R68-1：catalog 契约——pricing_decisions.cid_inputs/cid_results 必须 NOT NULL（jsonb）
# ---------------------------------------------------------------------------
def test_pricing_decisions_jsonb_not_null():
    """DB 存在时校验两 JSONB 列 NOT NULL（15-数据字典.md:579-580）；无 DB 时跳过。"""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("无 DATABASE_URL，跳过 catalog 契约检查")
    from sqlalchemy import create_engine, text

    with create_engine(url).connect() as c:
        rows = c.execute(text(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema='app' AND table_name='pricing_decisions' "
            "AND column_name IN ('cid_inputs','cid_results')"
        )).fetchall()
    nn = dict(rows)
    assert nn.get("cid_inputs") == "NO"
    assert nn.get("cid_results") == "NO"