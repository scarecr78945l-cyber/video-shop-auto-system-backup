# -*- coding: utf-8 -*-
"""P0-2 批次 2（C2）：FeedbackRepository 测试（round-161 授权实现）。

覆盖：三固定黄金键、subject 合法化（UUID 规范化 / category NFC / case-sensitive / 无 trim）、
extra_explanation 五键 exact-set、类型门禁、SKU gate、scale6、以及 PG 隔离 fixture 下的
首写/完整重放/内容冲突/NULL-safe extra_explanation/注入错误 key 冲突。

运行：cd backend && $env:DATABASE_URL=... python -m pytest tests/test_report_feedback.py -q
"""
import datetime
import os
import sys
import uuid
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain.report import (  # noqa: E402
    FeedbackDraft,
    FeedbackContentConflict,
    FeedbackValidationError,
    FeedbackWriteResult,
    build_feedback_idempotency_key,
    normalize_subject_key,
)
from domain.report.feedback_repository import FeedbackRepository  # noqa: E402
from tests.test_snapshot_repository import Chain  # noqa: E402

DB_URL = os.environ.get("DATABASE_URL", "").strip()
UTC = datetime.timezone.utc
EMPTY_EV = {"version_selector": {"sorted_snapshot_ids": [], "selected_id": None,
                                 "selection_rule": None, "manual_reason": None,
                                 "null_time_candidates": []}}


# =====================================================================
# 纯函数：三固定黄金键（round-144 §四.1）
# =====================================================================
def test_golden_key_a():
    k = build_feedback_idempotency_key(
        7, "product_score", "product", "b7f6b8c0-1234-5678-9abc-def012345678", "aggr_v1")
    assert k == ("fb:v1:b45e40ca322be2d7c29d22fb344e2f67644ebb450131f9bf8eee41ff052ef43f")


def test_golden_key_b_category_nfc():
    """category 组合音标经 NFC 得到同一键。"""
    k = build_feedback_idempotency_key(
        8, "category_score", "category", normalize_subject_key("category_score", "分类Á"), "aggr_v1")
    assert k == ("fb:v1:ab235c2771ec14e2ab75a5ba123b8cbc37c941819126fc2d74131743208f4dd4")


def test_golden_key_c_escaping():
    k = build_feedback_idempotency_key(
        9, "material_score", "material", "a|b\\c", "aggr_v1")
    assert k == ("fb:v1:d0284d2061bbbc0eea8db93ddce30463e9410b687057f31b8bc5edeed32d175c")


def test_material_golden_key_round152():
    k = build_feedback_idempotency_key(
        7, "material_score", "material", "f0e1d2c3-4b5a-6978-8a9b-0c1d2e3f4a5b", "aggr_v1")
    assert k == ("fb:v1:38787dc866c0dd04de1becfeef18179116dd87381287a82885ac3fe2d13fd656")


# =====================================================================
# 纯函数：subject 合法化
# =====================================================================
def test_subject_uuid_canonicalized():
    raw = "B7F6B8C0-1234-5678-9ABC-DEF012345678"
    assert normalize_subject_key("product_score", raw) == "b7f6b8c0-1234-5678-9abc-def012345678"
    with pytest.raises(FeedbackValidationError):
        normalize_subject_key("product_score", "not-a-uuid")


def test_subject_category_nfc_case_sensitive_no_trim():
    decomposed = "分类A\u0301"
    composed = "分类Á"
    assert normalize_subject_key("category_score", decomposed) == \
        normalize_subject_key("category_score", composed)
    # case-sensitive、无 trim
    assert normalize_subject_key("category_score", "Cat") != normalize_subject_key("category_score", "cat")
    assert normalize_subject_key("category_score", " cat ") == " cat "


def test_subject_category_too_long_rejected():
    with pytest.raises(FeedbackValidationError):
        normalize_subject_key("category_score", "x" * 129)


def test_subject_empty_rejected():
    for ft in ("product_score", "category_score", "material_score", "shop_strategy"):
        with pytest.raises(FeedbackValidationError):
            normalize_subject_key(ft, "")


# =====================================================================
# 纯函数：draft 校验
# =====================================================================
def _base_kwargs(**over):
    kw = dict(
        tenant_id=1, account_id=1, shop_id=1, shop_listing_id=1, product_id=1, campaign_id=1,
        source_snapshot_id=1, window_start=datetime.datetime(2026, 1, 1, tzinfo=UTC),
        window_end=datetime.datetime(2026, 1, 2, tzinfo=UTC), attribution_mode="last_click",
        feedback_type="product_score", subject_key=str(uuid.uuid4()), value=Decimal("1.000000"),
        aggregation_version="aggr_v1",
        extra_explanation={"numerator_gmv": 100, "denominator_spend": 100,
                           "origin_snapshot_ids": [1], "selector_evidence": dict(EMPTY_EV),
                           "aggregation_version": "aggr_v1"})
    kw.update(over)
    return kw


def test_extra_explanation_exact_set():
    kw = _base_kwargs()
    kw["extra_explanation"] = dict(kw["extra_explanation"])
    kw["extra_explanation"]["extra"] = 1
    with pytest.raises(FeedbackValidationError):
        FeedbackDraft(**kw)
    kw2 = _base_kwargs()
    kw2["extra_explanation"] = {k: v for k, v in kw2["extra_explanation"].items()
                                if k != "selector_evidence"}
    with pytest.raises(FeedbackValidationError):
        FeedbackDraft(**kw2)


def test_extra_explanation_inner_validation():
    for bad in (
        {"origin_snapshot_ids": []},
        {"origin_snapshot_ids": ["x"]},
        {"numerator_gmv": -1},
        {"selector_evidence": "not-a-dict"},
        {"aggregation_version": "aggr_v2"},
    ):
        kw = _base_kwargs()
        extra = dict(kw["extra_explanation"])
        extra.update(bad)
        kw["extra_explanation"] = extra
        with pytest.raises(FeedbackValidationError):
            FeedbackDraft(**kw)


def test_value_scale6_required():
    with pytest.raises(FeedbackValidationError):
        FeedbackDraft(**_base_kwargs(value=Decimal("1.5")))
    with pytest.raises(FeedbackValidationError):
        FeedbackDraft(**_base_kwargs(value=Decimal("NaN")))


def test_window_and_attribution_validation():
    with pytest.raises(FeedbackValidationError):
        FeedbackDraft(**_base_kwargs(window_end=datetime.datetime(2026, 1, 1, tzinfo=UTC)))
    with pytest.raises(FeedbackValidationError):
        FeedbackDraft(**_base_kwargs(attribution_mode=""))
    with pytest.raises(FeedbackValidationError):
        FeedbackDraft(**_base_kwargs(window_start=datetime.datetime(2026, 1, 1)))


def test_subject_type_derived_and_pairing():
    d = FeedbackDraft(**_base_kwargs())
    assert d.subject_type == "product"
    # 传入错误 subject_type 会被派生覆盖（不接受调用方覆盖）
    d2 = FeedbackDraft(**_base_kwargs(subject_type="material"))
    assert d2.subject_type == "product"


def test_repository_type_gate_on_duck_object():
    with pytest.raises(FeedbackValidationError):
        FeedbackRepository(None).write(object())
    with pytest.raises(FeedbackValidationError):
        FeedbackRepository(None).write("not-a-draft")


def test_sku_gate_fixed_closed():
    """D1 选项 B：sku_margin 固定关闭 gate（repo 层拒绝）。"""
    kw = _base_kwargs(feedback_type="sku_margin", subject_key=str(uuid.uuid4()))
    from domain.report.feedback_repository import SKU_GATE_MESSAGE
    d = FeedbackDraft(**kw)
    with pytest.raises(FeedbackValidationError) as ei:
        FeedbackRepository(None).write(d)
    assert "sku_margin" in str(ei.value) or SKU_GATE_MESSAGE in str(ei.value)


# =====================================================================
# PG：真实写入 / 重放 / 冲突
# =====================================================================
@pytest.fixture()
def conn():
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过 C2 PG 验收")
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    c = eng.connect()
    try:
        yield c
    finally:
        c.rollback()
        c.close()
        eng.dispose()


def _tx():
    """显式事务连接（每次写/读用独立事务，避免 autobegin 冲突）。"""
    from contextlib import contextmanager
    from sqlalchemy import create_engine

    @contextmanager
    def _cm():
        eng = create_engine(DB_URL)
        try:
            with eng.begin() as c:
                yield c
        finally:
            eng.dispose()
    return _cm()


def _read(fn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    try:
        with eng.connect() as c:
            return fn(c)
    finally:
        eng.dispose()


# 清理登记表：即使用例在 `try` 之前失败，也保证本用例的 tenant 链被清除。
_PENDING = []


@pytest.fixture(autouse=True)
def _drain_pending():
    yield
    while _PENDING:
        ch = _PENDING.pop()
        try:
            _cleanup(ch)
        except Exception:  # noqa: BLE001
            pass


def _mk_chain_and_snapshot(*, gmv=100, spend=100, sku=True, asset=True, version="v1"):
    from sqlalchemy import create_engine
    from domain.report import SnapshotRepository

    eng = create_engine(DB_URL)
    with eng.begin() as c:
        ch = Chain(c)
        snap = SnapshotRepository(c).write_observation(
            ch.obs(version, gmv=gmv, spend=spend, sku=sku, asset=asset)).snapshot_id
    eng.dispose()
    _PENDING.append(ch)
    return ch, snap


def _cleanup(ch):
    from sqlalchemy import create_engine, text

    eng = create_engine(DB_URL)
    with eng.begin() as c:
        c.execute(text("DELETE FROM app.roi_feedback_events WHERE tenant_id=:t"), {"t": ch.t})
        c.execute(text("DELETE FROM app.audit_events WHERE tenant_id=:t"), {"t": ch.t})
    eng.dispose()
    ch.cleanup()


def _draft_for(conn, ch, snap, *, feedback_type="product_score", value=None,
               extra_over=None, subject_key=None):
    from domain.report import compute_contribution, load_source_context

    ctx = load_source_context(conn, tenant_id=ch.t, source_snapshot_id=snap,
                              feedback_type=feedback_type)
    outcome = compute_contribution(feedback_type, snapshot_id=snap, gmv=ctx.gmv,
                                   spend=ctx.spend, granularity=ctx.granularity)
    extra = {"numerator_gmv": outcome.numerator_gmv,
             "denominator_spend": outcome.denominator_spend,
             "origin_snapshot_ids": [snap],
             "selector_evidence": dict(EMPTY_EV),
             "aggregation_version": "aggr_v1"}
    if extra_over:
        extra.update(extra_over)
    return FeedbackDraft(
        tenant_id=ctx.tenant_id, account_id=ctx.account_id, shop_id=ctx.shop_id,
        shop_listing_id=ctx.shop_listing_id, shop_listing_sku_id=ctx.shop_listing_sku_id,
        product_id=ctx.product_id, campaign_id=ctx.campaign_id,
        asset_binding_id=ctx.asset_binding_id, source_snapshot_id=snap,
        window_start=ctx.window_start, window_end=ctx.window_end,
        attribution_mode=ctx.attribution_mode, feedback_type=feedback_type,
        subject_key=subject_key or ctx.subject_key,
        value=value if value is not None else outcome.value,
        aggregation_version="aggr_v1", extra_explanation=extra)


def test_pg_first_write_and_replay():
    ch, snap = _mk_chain_and_snapshot()
    try:
        with _tx() as c:
            d = _draft_for(c, ch, snap)
        with _tx() as c:
            r1 = FeedbackRepository(c).write(d)
        assert isinstance(r1, FeedbackWriteResult) and r1.created is True
        with _tx() as c:
            r2 = FeedbackRepository(c).write(d)
        assert r2.created is False and r2.ledger_id == r1.ledger_id
        from sqlalchemy import text
        n = _read(lambda c: c.execute(
            text("SELECT count(*) FROM app.roi_feedback_events WHERE tenant_id=:t"),
            {"t": ch.t}).scalar())
        assert n == 1
    finally:
        _cleanup(ch)


def test_pg_content_conflict_on_value():
    ch, snap = _mk_chain_and_snapshot()
    try:
        with _tx() as c:
            d = _draft_for(c, ch, snap)
            FeedbackRepository(c).write(d)
        with _tx() as c:
            d2 = _draft_for(c, ch, snap, value=Decimal("9.000000"))
        with pytest.raises(FeedbackContentConflict):
            with _tx() as c:
                FeedbackRepository(c).write(d2)
        from sqlalchemy import text
        v = _read(lambda c: c.execute(
            text("SELECT value FROM app.roi_feedback_events WHERE tenant_id=:t"),
            {"t": ch.t}).scalar())
        assert Decimal(v) == Decimal("1.000000")
    finally:
        _cleanup(ch)


def test_pg_extra_explanation_null_safe_conflict():
    """NULL ↔ 对象必须判为冲突（禁止先把 NULL 补成 {}）。"""
    ch, snap = _mk_chain_and_snapshot()
    try:
        with _tx() as c:
            d = _draft_for(c, ch, snap)
            FeedbackRepository(c).write(d)
        from sqlalchemy import text
        with _tx() as c:
            c.execute(text("UPDATE app.roi_feedback_events SET extra_explanation = NULL "
                           "WHERE tenant_id=:t"), {"t": ch.t})
        with pytest.raises(FeedbackContentConflict):
            with _tx() as c:
                FeedbackRepository(c).write(d)
    finally:
        _cleanup(ch)


def test_null_safe_comparator_internal_unit():
    """NULL-safe 内容比较器内部单元测试（round-160 §四）。

    公开 draft 入口要求 extra_explanation 为 dict，因此 NULL/NULL 与 NULL/对象组合只能在
    比较器层验证；不新增允许省略证据的业务入口。"""
    from domain.report.feedback_repository import _content_equal

    kw = _base_kwargs()
    d = FeedbackDraft(**kw)
    row = {c: getattr(d, c) for c in
           ("tenant_id", "account_id", "shop_id", "shop_listing_id", "shop_listing_sku_id",
            "product_id", "campaign_id", "asset_binding_id", "source_snapshot_id",
            "window_start", "window_end", "attribution_mode", "feedback_type", "subject_type",
            "subject_key", "value", "aggregation_version")}
    # 对象 vs 对象相等
    row["extra_explanation"] = dict(d.extra_explanation)
    assert _content_equal(d, row) is True
    # 对象 vs NULL → 不同
    row["extra_explanation"] = None
    assert _content_equal(d, row) is False
    # NULL vs NULL → 相同（仅比较器层可达；同一 draft 字段集）
    d_null = FeedbackDraft(**kw)
    object.__setattr__(d_null, "extra_explanation", None)
    assert _content_equal(d_null, row) is True
    # NULL(draft) vs 对象(row) → 不同
    row["extra_explanation"] = dict(d.extra_explanation)
    assert _content_equal(d_null, row) is False


def test_pg_injected_wrong_key_is_conflict():
    """人为灌入错误 idempotency_key：自然键无行但 tenant+key 有行 → FeedbackContentConflict。"""
    ch, snap = _mk_chain_and_snapshot()
    try:
        from sqlalchemy import text
        subject = str(uuid.uuid4())
        other_subject = str(uuid.uuid4())
        key_of_other = build_feedback_idempotency_key(snap, "product_score", "product",
                                                     other_subject, "aggr_v1")
        with _tx() as c:
            c.execute(text(
                "INSERT INTO app.roi_feedback_events (tenant_id, account_id, shop_id, "
                "shop_listing_id, shop_listing_sku_id, product_id, campaign_id, "
                "asset_binding_id, source_snapshot_id, window_start, "
                "window_end, attribution_mode, feedback_type, subject_type, subject_key, value, "
                "extra_explanation, aggregation_version, idempotency_key) VALUES "
                "(:t, :a, :s, :l, :lsku, :p, :cmp, :asb, :snap, :ws, :we, 'last_click', "
                "'product_score', 'product', :sk, 1.000000, NULL, 'aggr_v1', :key)"),
                {"t": ch.t, "a": ch.a, "s": ch.shop, "l": ch.listing, "lsku": ch.lsku,
                 "p": ch.p, "cmp": ch.camp, "asb": ch.asb, "snap": snap,
                 "ws": datetime.datetime(2026, 1, 1, tzinfo=UTC),
                 "we": datetime.datetime(2026, 1, 2, tzinfo=UTC), "sk": subject,
                 "key": key_of_other})
        with _tx() as c:
            d = _draft_for(c, ch, snap, subject_key=other_subject)
        with pytest.raises(FeedbackContentConflict):
            with _tx() as c:
                FeedbackRepository(c).write(d)
    finally:
        _cleanup(ch)
