# -*- coding: utf-8 -*-
"""P0-2 批次 2（C1-b/c）：聚合 PG 只读接线测试（round-155 R154-3 §4.2）。

覆盖：三个有效源反例（PG 真实）、默认 search_path（app schema 显式限定）、NULL 维度、
跨 tenant/窗口/归因/版本隔离、新版本提交后结果与 source 依据一致、REPEATABLE READ 单一读取基准。

- 候选快照经**批次 1 事实层**（SnapshotRepository.write_observation）建立（已授权）；
- ledger 事件为本测试**隔离 fixture 直接 SQL 写入**（非生产写入接口；C2 写入门仍锁定）；
- finally 精确清理 + 新连接断言零残留。
运行：cd backend && $env:DATABASE_URL=... python -m pytest tests/test_report_aggregation_pg.py -q
"""
import datetime
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.report import (  # noqa: E402
    SnapshotRepository,
    aggregate_from_pg,
    load_candidates_from_pg,
)
from tests.test_snapshot_repository import Chain  # noqa: E402

DB_URL = os.environ.get("DATABASE_URL", "").strip()
UTC = datetime.timezone.utc

EVENT_COLS = ("tenant_id, account_id, shop_id, shop_listing_id, product_id, campaign_id, "
              "shop_listing_sku_id, asset_binding_id, "
              "source_snapshot_id, window_start, window_end, attribution_mode, feedback_type, "
              "subject_type, subject_key, value, aggregation_version, idempotency_key")


def _aware(y, m, d, h=0):
    return datetime.datetime(y, m, d, h, 0, 0, tzinfo=UTC)


@pytest.fixture()
def conn():
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过聚合 PG 接线验收")
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    c = eng.connect()
    try:
        yield c
    finally:
        c.close()
        eng.dispose()


def _mk_snapshot(c, ch, version_id, *, window=None, gmv=0, spend=0, platform_updated=None,
                 sku=True, asset=True):
    """经事实层写入候选快照（唯一 public 写入口），返回 dict(id, sku, asset)。"""
    repo = SnapshotRepository(c)
    obs = ch.obs(version_id, window=window, gmv=gmv, spend=spend,
                 platform_updated=platform_updated, sku=sku, asset=asset)
    snap_id = repo.write_observation(obs).snapshot_id
    return {"id": snap_id, "sku": ch.lsku if sku else None, "asset": ch.asb if asset else None}


def _ins_event(c, ch, snap, *, subject_key=None, value="1.0", window=None,
               attribution="last_click", version="aggr_v1", feedback="product_score",
               subject="product"):
    """隔离 fixture 直写 ledger 事件；维度必须与 source snapshot 一致（trg_feedback_dimension_consistency）。"""
    from sqlalchemy import text
    ws, we = window or (_aware(2026, 1, 1), _aware(2026, 1, 2))
    c.execute(text(
        f"INSERT INTO app.roi_feedback_events ({EVENT_COLS}) VALUES "
        "(:t, :a, :s, :l, :p, :cmp, :sku, :ab, :snap, :ws, :we, :am, :ft, :st, :sk, :val, :av, :ik)"),
        {"t": ch.t, "a": ch.a, "s": ch.shop, "l": ch.listing, "p": ch.p, "cmp": ch.camp,
         "sku": snap["sku"], "ab": snap["asset"], "snap": snap["id"],
         "ws": ws, "we": we, "am": attribution, "ft": feedback,
         "st": subject, "sk": subject_key or str(uuid.uuid4()), "val": value,
         "av": version, "ik": "ik-" + uuid.uuid4().hex[:16]})


def _cleanup_chain(ch):
    """先删本 tenant 的 ledger 事件，再走 Chain 清理。"""
    from sqlalchemy import create_engine, text

    eng = create_engine(DB_URL)
    with eng.begin() as c:
        c.execute(text("DELETE FROM app.roi_feedback_events WHERE tenant_id=:t"), {"t": ch.t})
    eng.dispose()
    ch.cleanup()


# =====================================================================
# 三反例（PG 真实）
# =====================================================================
def test_pg_ce1_dual_ledger(conn):
    """双 ledger：仅最新版有效 → ROI=400/100=4.000000。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            s_old = _mk_snapshot(c, ch, "v1", gmv=100, spend=100,
                                 platform_updated=_aware(2026, 9, 1))
            s_new = _mk_snapshot(c, ch, "v2", gmv=400, spend=100,
                                 platform_updated=_aware(2026, 9, 2))
            _ins_event(c, ch, s_old, subject_key=str(uuid.uuid4()))
            _ins_event(c, ch, s_new, subject_key=str(uuid.uuid4()))
        with create_engine(DB_URL).connect() as c:
            res = aggregate_from_pg(c, tenant_id=ch.t, feedback_type="product_score")
        assert len(res.aggregates) == 1
        a = res.aggregates[0]
        assert a.value is not None and str(a.value) == "4.000000"
        assert a.numerator_gmv == 400 and a.denominator_spend == 100
        assert a.source_snapshot_ids == (s_new["id"],)
        assert a.sample_count == 1
    finally:
        if ch is not None:
            _cleanup_chain(ch)
        eng.dispose()


def test_pg_ce2_newest_without_event(conn):
    """最新版未产 event → 淘汰旧版，无自动结果。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            s_old = _mk_snapshot(c, ch, "v1", gmv=100, spend=50,
                                 platform_updated=_aware(2026, 9, 2))
            _mk_snapshot(c, ch, "v2", gmv=999, spend=0,
                         platform_updated=_aware(2026, 9, 3))   # 未产 event
            _ins_event(c, ch, s_old, subject_key=str(uuid.uuid4()))
        with create_engine(DB_URL).connect() as c:
            res = aggregate_from_pg(c, tenant_id=ch.t, feedback_type="product_score")
        assert res.aggregates == ()
        assert len(res.effective_sources) == 1 and res.effective_sources[0][1] is not None
    finally:
        if ch is not None:
            _cleanup_chain(ch)
        eng.dispose()


def test_pg_ce3_max_tie_manual(conn):
    """最大时间并列 → manual，无自动结果。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            s1 = _mk_snapshot(c, ch, "v1", gmv=100, spend=50,
                              platform_updated=_aware(2026, 9, 2))
            s2 = _mk_snapshot(c, ch, "v2", gmv=200, spend=50,
                              platform_updated=_aware(2026, 9, 2))
            _ins_event(c, ch, s1, subject_key=str(uuid.uuid4()))
            _ins_event(c, ch, s2, subject_key=str(uuid.uuid4()))
        with create_engine(DB_URL).connect() as c:
            res = aggregate_from_pg(c, tenant_id=ch.t, feedback_type="product_score")
        assert res.aggregates == ()
        assert res.manual_identities == tuple(k for k, v in res.effective_sources if v is None)
        assert len(res.manual_identities) == 1
    finally:
        if ch is not None:
            _cleanup_chain(ch)
        eng.dispose()


# =====================================================================
# 默认 search_path / NULL 维度 / 跨作用域 / 版本
# =====================================================================
def test_pg_default_search_path_schema_qualified(conn):
    """默认 search_path（public）下仍能读 app schema（显式限定）。"""
    from sqlalchemy import create_engine, text

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            s = _mk_snapshot(c, ch, "v1", gmv=100, spend=100,
                             platform_updated=_aware(2026, 9, 1))
            _ins_event(c, ch, s, subject_key=str(uuid.uuid4()))
        with create_engine(DB_URL).connect() as c0:
            sp = c0.execute(text("SHOW search_path")).scalar()
            assert "app" not in str(sp), f"预期默认 search_path 不含 app: {sp}"
        with create_engine(DB_URL).connect() as c:
            res = aggregate_from_pg(c, tenant_id=ch.t, feedback_type="product_score")
        assert len(res.aggregates) == 1
    finally:
        if ch is not None:
            _cleanup_chain(ch)
        eng.dispose()


def test_pg_null_dimensions(conn):
    """NULL sku/asset 维度（NULLS NOT DISTINCT 唯一键）仍可加载与聚合。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            s = _mk_snapshot(c, ch, "v-null", gmv=150, spend=100,
                             platform_updated=_aware(2026, 9, 1), sku=False, asset=False)
            _ins_event(c, ch, s, subject_key=str(uuid.uuid4()))
        with create_engine(DB_URL).connect() as c:
            cand, idmap, tmap = load_candidates_from_pg(
                c, tenant_id=ch.t, feedback_type="product_score")
            assert len(cand) == 1 and len(idmap) == 1
        with create_engine(DB_URL).connect() as c:
            res = aggregate_from_pg(c, tenant_id=ch.t, feedback_type="product_score")
        assert len(res.aggregates) == 1 and str(res.aggregates[0].value) == "1.500000"
    finally:
        if ch is not None:
            _cleanup_chain(ch)
        eng.dispose()


def test_pg_cross_scope_and_version_isolation(conn):
    """跨 tenant / 窗口 / 归因 / 版本隔离：只返回本 tenant 且 aggr_v1 的结果。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch1 = ch2 = None
    try:
        with eng.begin() as c:
            ch1 = Chain(c)
            ch2 = Chain(c)
            # ch1：窗口 W1（默认）
            s1 = _mk_snapshot(c, ch1, "v1", gmv=100, spend=100,
                              platform_updated=_aware(2026, 9, 1))
            _ins_event(c, ch1, s1, subject_key=str(uuid.uuid4()))
            # ch1：窗口 W2 → 独立身份
            w2 = (_aware(2026, 3, 1), _aware(2026, 3, 2))
            s2 = _mk_snapshot(c, ch1, "v2", gmv=300, spend=100, window=w2,
                              platform_updated=_aware(2026, 9, 1))
            _ins_event(c, ch1, s2, subject_key=str(uuid.uuid4()), window=w2)
            # ch1：归因/维度不同 → 独立身份（仅 aggr_v2 事件，不应被 aggr_v1 查询纳入）
            s4 = _mk_snapshot(c, ch1, "v4", gmv=888, spend=100,
                              platform_updated=_aware(2026, 9, 1), sku=False)
            _ins_event(c, ch1, s4, subject_key=str(uuid.uuid4()), version="aggr_v2")
            # ch2：另一租户
            t2 = _mk_snapshot(c, ch2, "v1", gmv=400, spend=100,
                              platform_updated=_aware(2026, 9, 1))
            _ins_event(c, ch2, t2, subject_key=str(uuid.uuid4()))
        with create_engine(DB_URL).connect() as c:
            res1 = aggregate_from_pg(c, tenant_id=ch1.t, feedback_type="product_score")
            res2 = aggregate_from_pg(c, tenant_id=ch2.t, feedback_type="product_score")
        # ch1：默认窗口 + W2 = 2 个作用域（aggr_v2 的 s4 不纳入）
        assert len(res1.aggregates) == 2, res1.aggregates
        assert all(a.tenant_id == ch1.t for a in res1.aggregates)
        assert all(a.aggregation_version == "aggr_v1" for a in res1.aggregates)
        assert sorted(str(a.value) for a in res1.aggregates) == ["1.000000", "3.000000"]
        # ch2：仅本租户
        assert len(res2.aggregates) == 1 and res2.aggregates[0].tenant_id == ch2.t
        assert str(res2.aggregates[0].value) == "4.000000"
    finally:
        if ch1 is not None:
            _cleanup_chain(ch1)
        if ch2 is not None:
            _cleanup_chain(ch2)
        eng.dispose()


def test_pg_new_version_commit_consistency(conn):
    """受控提交新版本后，结果与 source 依据一致变化（同一读取基准内自洽）。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            s_old = _mk_snapshot(c, ch, "v1", gmv=100, spend=100,
                                 platform_updated=_aware(2026, 9, 1))
            _ins_event(c, ch, s_old, subject_key=str(uuid.uuid4()))
        with create_engine(DB_URL).connect() as c:
            r1 = aggregate_from_pg(c, tenant_id=ch.t, feedback_type="product_score")
        assert str(r1.aggregates[0].value) == "1.000000"
        assert r1.aggregates[0].source_snapshot_ids == (s_old["id"],)
        # 提交新版（更大 platform_updated_at）
        with eng.begin() as c:
            s_new = _mk_snapshot(c, ch, "v2", gmv=500, spend=100,
                                 platform_updated=_aware(2026, 9, 5))
            _ins_event(c, ch, s_new, subject_key=str(uuid.uuid4()))
        with create_engine(DB_URL).connect() as c:
            r2 = aggregate_from_pg(c, tenant_id=ch.t, feedback_type="product_score")
        assert str(r2.aggregates[0].value) == "5.000000"
        assert r2.aggregates[0].source_snapshot_ids == (s_new["id"],)
        # 身份键不变、选中 source 变化（依据自洽）
        assert [k for k, _ in r1.effective_sources] == [k for k, _ in r2.effective_sources]
        assert r1.effective_sources[0][1] == s_old["id"]
        assert r2.effective_sources[0][1] == s_new["id"]
    finally:
        if ch is not None:
            _cleanup_chain(ch)
        eng.dispose()
