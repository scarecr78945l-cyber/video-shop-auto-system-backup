# -*- coding: utf-8 -*-
"""P0-2 批次 2（C1-b/c）：单 source 数值贡献计算测试（round-153 授权实现）。

覆盖 round-152 §三：五类 formula、四 Decimal 向量、SKU 零消耗/亏损、
canonical granularity、typed outcome 分层、输入负例、manifest 完整对象/hash。
纯函数，无 DB。运行：cd backend && python -m pytest tests/test_report_calculator.py -q
"""
import os
import sys
import decimal
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.report import (  # noqa: E402
    CANONICAL_GRANULARITY,
    EXPECTED_MANIFEST_SHA256,
    InsufficientInputs,
    RoiContribution,
    SkuMarginContribution,
    ZeroSpendSkipped,
    CalculatorInputError,
    compute_contribution,
    manifest_sha256,
    canonical_payload,
    verify_manifest,
)


# ---------------------------------------------------------------- 五类 formula
@pytest.mark.parametrize("ft", ["product_score", "category_score", "material_score", "shop_strategy"])
def test_roi_types_contribution(ft):
    c = compute_contribution(ft, snapshot_id=7, gmv=150, spend=100)
    assert isinstance(c, RoiContribution)
    assert c.kind == "roi"
    assert c.numerator_gmv == 150 and c.denominator_spend == 100
    assert c.value == Decimal("1.500000")


def test_sku_margin_contribution():
    c = compute_contribution("sku_margin", snapshot_id=7, gmv=150, spend=100)
    assert isinstance(c, SkuMarginContribution)
    assert c.kind == "sku_margin"
    assert c.value == Decimal("50.000000")  # 分：gmv − spend


# ---------------------------------------------------------------- 四 Decimal 向量
@pytest.mark.parametrize("gmv,spend,expected", [
    (1, 3, "0.333333"),
    (10, 3, "3.333333"),
    (150, 100, "1.500000"),
    (0, 100, "0.000000"),
])
def test_decimal_vectors(gmv, spend, expected):
    c = compute_contribution("product_score", snapshot_id=1, gmv=gmv, spend=spend)
    assert c.value == Decimal(expected)
    # scale=6 canonical（恰 6 位小数）
    assert c.value.as_tuple().exponent == -6


# ---------------------------------------------------------------- SKU 零消耗/亏损（R150 冻结）
def test_sku_zero_spend_not_skipped():
    c = compute_contribution("sku_margin", snapshot_id=1, gmv=100, spend=0)
    assert isinstance(c, SkuMarginContribution)
    assert c.value == Decimal("100.000000")


def test_sku_negative_margin_allowed():
    c = compute_contribution("sku_margin", snapshot_id=1, gmv=50, spend=100)
    assert isinstance(c, SkuMarginContribution)
    assert c.value == Decimal("-50.000000")


def test_roi_zero_spend_typed_skip():
    c = compute_contribution("product_score", snapshot_id=9, gmv=100, spend=0)
    assert isinstance(c, ZeroSpendSkipped)
    assert c.kind == "zero_spend_skipped"
    assert c.snapshot_id == 9
    assert c.reason == "denominator_spend_zero"


# ---------------------------------------------------------------- canonical granularity
@pytest.mark.parametrize("ft,gran", [
    ("product_score", "campaign"),
    ("category_score", "campaign"),
    ("material_score", "campaign_asset"),
    ("shop_strategy", "campaign"),
    ("sku_margin", "shop_listing_sku"),
])
def test_canonical_granularity_accepted(ft, gran):
    c = compute_contribution(ft, snapshot_id=1, gmv=10, spend=10, granularity=gran)
    assert c.kind in ("roi", "sku_margin")


def test_non_canonical_granularity_insufficient():
    c = compute_contribution("material_score", snapshot_id=1, gmv=10, spend=10,
                             granularity="campaign")
    assert isinstance(c, InsufficientInputs)
    assert c.reason == "no_canonical_source"
    assert c.missing_fields == ("granularity",)


# ---------------------------------------------------------------- typed outcome 分层
def test_missing_fields_insufficient():
    c = compute_contribution("product_score", snapshot_id=5, gmv=None, spend=100)
    assert isinstance(c, InsufficientInputs)
    assert c.reason == "missing_numerator_or_denominator"
    assert c.missing_fields == ("gmv",)
    c2 = compute_contribution("product_score", snapshot_id=5, gmv=100, spend=None)
    assert c2.missing_fields == ("spend",)
    c3 = compute_contribution("product_score", snapshot_id=5, gmv=None, spend=None)
    assert set(c3.missing_fields) == {"gmv", "spend"}


def test_insufficient_reason_exact_set():
    with pytest.raises(CalculatorInputError):
        InsufficientInputs("product_score", 1, "bogus_reason")


# ---------------------------------------------------------------- 输入负例
def test_unknown_feedback_type_rejected():
    with pytest.raises(CalculatorInputError):
        compute_contribution("bogus", snapshot_id=1, gmv=1, spend=1)


@pytest.mark.parametrize("bad_id", [0, -1, "1", None, True])
def test_bad_snapshot_id_rejected(bad_id):
    with pytest.raises(CalculatorInputError):
        compute_contribution("product_score", snapshot_id=bad_id, gmv=1, spend=1)


def test_bool_and_negative_amounts_rejected():
    with pytest.raises(CalculatorInputError):
        compute_contribution("product_score", snapshot_id=1, gmv=True, spend=1)
    with pytest.raises(CalculatorInputError):
        compute_contribution("product_score", snapshot_id=1, gmv=1, spend=-5)


# ---------------------------------------------------------------- manifest 单一真源
def test_manifest_hash_and_verify():
    assert manifest_sha256() == EXPECTED_MANIFEST_SHA256
    assert verify_manifest() is True


def test_manifest_complete_object_and_serialization():
    import json
    payload = canonical_payload()
    obj = json.loads(payload)
    assert set(obj) == {"category_min_products", "decimal", "feedback_types",
                        "min_sample_snapshot", "version"}
    assert obj["version"] == "aggr_v1"
    assert obj["decimal"] == {"precision": 60, "rounding": "ROUND_HALF_UP", "storage_scale": 6}
    assert obj["min_sample_snapshot"] == 1 and obj["category_min_products"] == 1
    assert set(obj["feedback_types"]) == {"product_score", "category_score", "material_score",
                                          "sku_margin", "shop_strategy"}
    # canonical：递归键排序 + 紧凑分隔符（无空格）
    assert payload == json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"))
    assert " " not in payload


def test_manifest_canonical_granularity_map():
    assert CANONICAL_GRANULARITY == {
        "product_score": "campaign", "category_score": "campaign",
        "material_score": "campaign_asset", "shop_strategy": "campaign",
        "sku_margin": "shop_listing_sku"}


# =====================================================================
# round-155 R154-2：Decimal 不依赖调用方 context
# =====================================================================
@pytest.mark.parametrize("prec,rounding", [
    (28, decimal.ROUND_HALF_EVEN), (6, decimal.ROUND_DOWN), (9, decimal.ROUND_UP),
    (60, decimal.ROUND_HALF_UP),
], ids=["prec28-halfeven", "prec6-down", "prec9-up", "prec60-halfup"])
def test_roi_invariant_under_caller_context(prec, rounding):
    """调用方 context 的 prec/rounding 改变不影响 ROI 结果。"""
    with decimal.localcontext() as ctx:
        ctx.prec = prec
        ctx.rounding = rounding
        c = compute_contribution("product_score", snapshot_id=1, gmv=150, spend=100)
        assert c.value == Decimal("1.500000")
        c2 = compute_contribution("product_score", snapshot_id=1, gmv=1, spend=3)
        assert c2.value == Decimal("0.333333")


@pytest.mark.parametrize("prec,rounding", [
    (28, decimal.ROUND_HALF_EVEN), (10, decimal.ROUND_DOWN),
], ids=["prec28", "prec10-down"])
def test_sku_large_int8_invariant(prec, rounding):
    """R154-2：int8 范围最大金额的 SKU 差额不受调用方 context 影响（不在外部 context 丢失数字）。"""
    with decimal.localcontext() as ctx:
        ctx.prec = prec
        ctx.rounding = rounding
        c = compute_contribution("sku_margin", snapshot_id=1,
                                 gmv=1234567890123456789, spend=0)
        assert c.value == Decimal("1234567890123456789.000000")
        c2 = compute_contribution("sku_margin", snapshot_id=1,
                                  gmv=1234567890123456789, spend=1234567890123456788)
        assert c2.value == Decimal("1.000000")


def test_zero_value_invariant():
    with decimal.localcontext() as ctx:
        ctx.prec = 6
        c = compute_contribution("product_score", snapshot_id=1, gmv=0, spend=100)
        assert c.value == Decimal("0.000000")


def test_caller_context_not_polluted():
    """计算不污染调用方 Decimal context（prec/rounding 前后一致）。"""
    decimal.getcontext().prec = 28
    decimal.getcontext().rounding = decimal.ROUND_HALF_EVEN
    before = (decimal.getcontext().prec, decimal.getcontext().rounding)
    compute_contribution("product_score", snapshot_id=1, gmv=10, spend=3)
    compute_contribution("sku_margin", snapshot_id=1, gmv=50, spend=100)
    after = (decimal.getcontext().prec, decimal.getcontext().rounding)
    assert before == after == (28, decimal.ROUND_HALF_EVEN)


def test_scale6_representation_check():
    """scale 校验用指数/finite，不用数值相等（避免依赖调用方 context）。"""
    from domain.report import RoiContribution
    with pytest.raises(CalculatorInputError):
        RoiContribution("product_score", 1, 1, 1, Decimal("1.5"))       # 非 6 位
    with pytest.raises(CalculatorInputError):
        RoiContribution("product_score", 1, 1, 1, Decimal("NaN"))
    # 正确 scale 通过
    RoiContribution("product_score", 1, 1, 1, Decimal("1.500000"))
