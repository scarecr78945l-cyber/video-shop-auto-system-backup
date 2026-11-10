# -*- coding: utf-8 -*-
"""P0-2 批次 1（B3）：SnapshotCollector(PG) 测试（round-133）。

覆盖 round-132-cdx §四（collect_missing 语义/单行 savepoint 隔离/失败清理）：
- run_once 计数（created/reused/conflicted/rejected）；
- collect_missing = 逐行 insert-or-select（无 legacy recorded_at 游标）；
- 单行 savepoint 隔离：坏行 rejected 不 abort 外层事务，其余行照常；
- 失败清理：finally 精确清理 + 新连接断言零残留；连续两次执行结果一致。

运行：cd backend && $env:DATABASE_URL=... python -m pytest tests/test_snapshot_collector.py -q
"""
import datetime
import os
import sys
import uuid
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.report import (  # noqa: E402
    CollectResult,
    ReportObservation,
    SnapshotCollector,
)

DB_URL = os.environ.get("DATABASE_URL", "").strip()
UTC = datetime.timezone.utc


def _aware(y, m, d, h=0, mi=0, s=0):
    return datetime.datetime(y, m, d, h, mi, s, tzinfo=UTC)


@pytest.fixture()
def conn():
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过 snapshot collector 验收")
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    c = eng.connect()
    tx = c.begin()
    try:
        yield c
    finally:
        tx.rollback()
        c.close()
        eng.dispose()


def _mk_chain(c):
    from tests.test_snapshot_repository import Chain  # 复用 fixture 链

    return Chain(c)


def _run_once_counts(conn, observations):
    collector = SnapshotCollector(conn)
    return collector.run_once(observations)


# =====================================================================
# run_once 计数
# =====================================================================
def test_run_once_created_then_reused(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = _mk_chain(c)
            r1 = _run_once_counts(c, [ch.obs("v1")])
            assert isinstance(r1, CollectResult)
            assert r1.created == 1 and r1.reused == 0
            assert r1.conflicted == 0 and r1.rejected == 0
            r2 = _run_once_counts(c, [ch.obs("v1")])  # 完全重放
            assert r2.created == 0 and r2.reused == 1
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_run_once_counts_conflicted_and_rejected(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = _mk_chain(c)
            r1 = _run_once_counts(c, [ch.obs("v1")])
            assert r1.created == 1
            # 同 (S,V) 不同内容 -> conflicted
            r2 = _run_once_counts(c, [ch.obs("v1", gmv=999)])
            assert r2.conflicted == 1
            # 校验失败 -> rejected（naive 时间）
            bad = ReportObservation(**{**ch.obs("v2").__dict__,
                                       "captured_at": datetime.datetime(2026, 1, 1)})
            r3 = _run_once_counts(c, [bad])
            assert r3.rejected == 1
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_run_once_multiple_rows_mixed(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = _mk_chain(c)
            rows = [ch.obs("v1"), ch.obs("v2"), ch.obs("v3")]
            r = _run_once_counts(c, rows)
            assert r.created == 3 and r.total == 3
            # 再跑：全 reused
            r2 = _run_once_counts(c, rows)
            assert r2.reused == 3 and r2.created == 0
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


# =====================================================================
# collect_missing = 逐行 insert-or-select
# =====================================================================
def test_collect_missing_reuses_existing_by_identity(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = _mk_chain(c)
            collector = SnapshotCollector(c)
            r1 = collector.run_once([ch.obs("m1")])
            assert r1.created == 1
            # collect_missing 对同 (S,V) 行复用（不再用 legacy recorded_at 游标）
            r2 = collector.collect_missing([ch.obs("m1")])
            assert r2.created == 0 and r2.reused == 1
            # 缺的新版本 -> created
            r3 = collector.collect_missing([ch.obs("m2")])
            assert r3.created == 1
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


# =====================================================================
# 单行 savepoint 隔离（坏行不 abort 外层事务）
# =====================================================================
def test_savepoint_isolation_bad_row_does_not_abort(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = _mk_chain(c)
            # 中间夹一条坏行（DB 层拒绝：cross-campaign 维度），前后是好行
            listing2 = ch.ins(
                "INSERT INTO app.shop_listings (public_id, tenant_id, account_id, shop_id, "
                "product_id, title_effective, idempotency_key) VALUES "
                "(gen_random_uuid(), :t, :a, :s, :p, 'L2', :ik) RETURNING id",
                {"t": ch.t, "a": ch.a, "s": ch.shop, "p": ch.p2,
                 "ik": "lk2-" + uuid.uuid4().hex[:8]})
            bad_db = ReportObservation(
                tenant_id=ch.t, account_id=ch.a, shop_id=ch.shop,
                shop_listing_id=listing2, shop_listing_sku_id=None,
                product_id=ch.p, campaign_id=ch.camp, asset_binding_id=None,
                granularity="campaign", window_start=_aware(2026, 2, 1),
                window_end=_aware(2026, 2, 2), attribution_mode="last_click",
                platform_version_id="bad-db", platform_updated_at=None,
                captured_at=_aware(2026, 2, 1, 12), raw_evidence=b"raw-bad-db")
            rows = [ch.obs("s1"), bad_db, ch.obs("s2")]
            r = _run_once_counts(c, rows)
            assert r.created == 2, f"两条好行应成功: {r.details}"
            assert r.rejected == 1, f"坏行应 rejected（DB 层）: {r.details}"
            # 外层事务仍可用
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 2
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


# =====================================================================
# 失败清理 + 连续两次执行
# =====================================================================
def test_failure_cleanup_and_repeatable(conn):
    from sqlalchemy import create_engine

    # 第一次执行：自建 fixture + 写入 + 清理
    eng1 = create_engine(DB_URL)
    ch1 = None
    try:
        with eng1.begin() as c:
            ch1 = _mk_chain(c)
            r = _run_once_counts(c, [ch1.obs("f1")])
            assert r.created == 1
    finally:
        if ch1 is not None:
            ch1.cleanup()
        eng1.dispose()
    # 第一次清理后零残留
    from sqlalchemy import create_engine as ce
    with ce(DB_URL).connect() as c:
        n1 = c.execute(ch1.sql(
            "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
            {"t": ch1.t}).scalar()
    assert int(n1) == 0

    # 第二次执行：完全一致（新 tenant、新链、写 1 行、清理）
    eng2 = create_engine(DB_URL)
    ch2 = None
    try:
        with eng2.begin() as c:
            ch2 = _mk_chain(c)
            r = _run_once_counts(c, [ch2.obs("f1")])
            assert r.created == 1
    finally:
        if ch2 is not None:
            ch2.cleanup()
        eng2.dispose()
    with ce(DB_URL).connect() as c:
        n2 = c.execute(ch2.sql(
            "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
            {"t": ch2.t}).scalar()
    assert int(n2) == 0


# =====================================================================
# R134-3：异常分类——allowlist 可隔离，基础设施/程序错误必须传播
# =====================================================================
def test_r1343_validation_conflict_sqlstate_isolated(conn):
    """R134-3 正向：validation/content-conflict/已知 SQLSTATE（ZT006）转业务结果，整批继续。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = _mk_chain(c)
            # 1) validation 拒绝（naive 时间）
            bad_naive = ReportObservation(**{**ch.obs("n1").__dict__,
                                              "captured_at": datetime.datetime(2026, 1, 1)})
            # 2) 内容冲突（同 (S,V) 不同 gmv）
            bad_conflict = ch.obs("n2", gmv=999)
            # 3) 已知 SQLSTATE：cross-listing 维度（ZT006）——同 tenant 下第二个 listing
            listing2 = ch.ins(
                "INSERT INTO app.shop_listings (public_id, tenant_id, account_id, shop_id, "
                "product_id, title_effective, idempotency_key) VALUES "
                "(gen_random_uuid(), :t, :a, :s, :p, 'L2', :ik) RETURNING id",
                {"t": ch.t, "a": ch.a, "s": ch.shop, "p": ch.p2,
                 "ik": "lk2-" + uuid.uuid4().hex[:8]})
            bad_dim = ReportObservation(
                tenant_id=ch.t, account_id=ch.a, shop_id=ch.shop,
                shop_listing_id=listing2, shop_listing_sku_id=None,
                product_id=ch.p, campaign_id=ch.camp, asset_binding_id=None,
                granularity="campaign", window_start=_aware(2026, 3, 1),
                window_end=_aware(2026, 3, 2), attribution_mode="last_click",
                platform_version_id="dim1", platform_updated_at=None,
                captured_at=_aware(2026, 3, 1, 12), raw_evidence=b"raw-dim1")
            # 先写一条正常行建立 (S,V) 供冲突用
            r0 = _run_once_counts(c, [ch.obs("n2")])
            assert r0.created == 1
            r = _run_once_counts(c, [bad_naive, ch.obs("n2", gmv=999), bad_dim])
            # validation -> rejected；内容冲突 -> conflicted；已知 SQLSTATE -> rejected
            assert r.rejected == 2, f"validation+SQLSTATE 应 rejected: {r.details}"
            assert r.conflicted == 1, f"内容冲突应 conflicted: {r.details}"
            assert r.created == 0
            # 整批未崩、外层事务可用
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 1
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


@pytest.mark.parametrize("exc_cls", [
    "OperationalError", "InterfaceError", "ProgrammingError", "RuntimeError",
], ids=["operational", "interface", "programming", "unknown"])
def test_r1343_infra_error_propagates(conn, exc_cls):
    """R134-3 负向：连接故障/编程错误/未知异常必须原样向上抛出（整批失败）。"""
    import sys

    from sqlalchemy import create_engine
    from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = _mk_chain(c)
            collector = SnapshotCollector(c)
            if exc_cls == "OperationalError":
                exc = OperationalError("stmt", {}, Exception("transport lost"))
            elif exc_cls == "InterfaceError":
                exc = InterfaceError("stmt", {}, Exception("connection closed"))
            elif exc_cls == "ProgrammingError":
                exc = ProgrammingError("stmt", {}, Exception("syntax error"))
            else:
                exc = RuntimeError("unknown bug")

            def boom(obs):
                raise exc

            # 注入失败到写入口：任何基础设施/未知异常都必须传播，不降级为 rejected
            from domain.report import SnapshotRepository
            import types
            original = SnapshotRepository.write_observation

            def patched(self, obs):
                raise exc

            SnapshotRepository.write_observation = patched
            try:
                with pytest.raises(type(exc)):
                    collector.run_once([ch.obs("p1")])
            finally:
                SnapshotRepository.write_observation = original
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


class _FakePgError(Exception):
    """合成 psycopg2 错误（仅携带 pgcode，供 DBAPIError.orig 使用）。"""

    def __init__(self, pgcode, message="synthetic"):
        super().__init__(message)
        self.pgcode = pgcode
        self.pgerror = message


def _make_dbapi_error(pgcode):
    from sqlalchemy.exc import DBAPIError

    return DBAPIError("stmt", {}, _FakePgError(pgcode))


@pytest.mark.parametrize("pgcode", ["23502", "23503", "23514", "23P01", "ZT006"],
                         ids=["23502-notnull", "23503-fk", "23514-check",
                              "23p01-exclusion", "zt006-dimension"])
def test_r1362_allowlist_sqlstate_isolated(conn, pgcode):
    """R136-2：五码 allowlist exact-set——任一码都转 rejected，不传播、整批继续。"""
    from sqlalchemy import create_engine

    from domain.report import SnapshotRepository

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = _mk_chain(c)
            collector = SnapshotCollector(c)
            error = _make_dbapi_error(pgcode)
            original = SnapshotRepository.write_observation

            def patched(self, obs):
                raise error

            SnapshotRepository.write_observation = patched
            try:
                r = collector.run_once([ch.obs("allow-" + pgcode)])
            finally:
                SnapshotRepository.write_observation = original
            assert r.rejected == 1, f"{pgcode} 应转 rejected: {r.details}"
            assert r.created == 0 and r.conflicted == 0
            # 外层事务可用（run_once 未抛）
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 0
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_r1362_non_allowlist_sqlstate_propagates(conn):
    """R136-2：非 allowlist 连接码 08006 必须传播（不降级为 rejected）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError

    from domain.report import SnapshotRepository

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = _mk_chain(c)
            collector = SnapshotCollector(c)
            error = _make_dbapi_error("08006")
            original = SnapshotRepository.write_observation

            def patched(self, obs):
                raise error

            SnapshotRepository.write_observation = patched
            try:
                with pytest.raises(DBAPIError):
                    collector.run_once([ch.obs("prop-08006")])
            finally:
                SnapshotRepository.write_observation = original
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()
