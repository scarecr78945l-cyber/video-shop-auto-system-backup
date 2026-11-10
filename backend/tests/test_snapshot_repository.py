# -*- coding: utf-8 -*-
"""P0-2 批次 1（B3）：append-only SnapshotRepository + Collector(PG) 测试（round-133；round-135 R134-1/2/4 加固）。

覆盖 round-132-cdx §四.2~§四.6 + round-134-cdx R134-1/R134-2/R134-4：
- append-only（首次创建/完全重放/captured_at 改变仍复用/比较字段变异触发冲突/旧行未变）；
- NULLS NOT DISTINCT（SKU/asset 两者空/单侧空/两者非空的重放与冲突）；
- 维度隔离：**八类交叉注入独立用例**（tenant/account/shop/listing/SKU/product/campaign/asset，
  每类验证确定错误、外层事务仍可用、事实与 fixture 最终归零）；
- 并发（同值 2 worker 仅一行同 id；异值竞争仅保留胜者，败者确定性领域异常）；
- 输入负例（bool ID/金额、naive 时间、反向/零长度窗口、负金额/计数、非 finite Decimal、
  非法枚举、空证据、非 str version ID）；
- R134-1：唯一 public 写入口 write_observation（受信边界 validate+hash+key+draft 重验）；
  白盒验证 _validate_draft 拒绝伪造 digest/错误 version key/类型穿透；
- R134-2：非 str version ID 与 utcoffset() is None 时间穿透拒绝；
- R134-4：完整 comparison set（排除唯一身份字段）逐字段变异冲突 + 旧行逐列保持。

fixture 链复用 assert_triggers_probes.py 模式，全部测试内自建；写入提交事务（worker/新连接可见），
预期失败的注入用 SAVEPOINT（begin_nested）隔离；finally 在事务提交后精确清理 + 新连接断言零残留。

运行：cd backend && $env:DATABASE_URL=... python -m pytest tests/test_snapshot_repository.py -q
"""
import datetime
import os
import sys
import threading
import uuid
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.report import (  # noqa: E402
    ObservationValidationError,
    ReportObservation,
    SnapshotCollector,
    SnapshotContentConflict,
    SnapshotRepository,
    SnapshotWriteResult,
)

DB_URL = os.environ.get("DATABASE_URL", "").strip()
UTC = datetime.timezone.utc


def _aware(y, m, d, h=0, mi=0, s=0, us=0):
    return datetime.datetime(y, m, d, h, mi, s, us, tzinfo=UTC)


@pytest.fixture()
def conn():
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过 snapshot repository 验收")
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


class Chain:
    """全维度 fixture 链（写入提交事务，worker/新连接可见）；finally 精确清理 + 新连接断言零残留。"""

    def __init__(self, conn):
        from sqlalchemy import text as sqltext

        self.sql = sqltext
        self.c = conn
        self._new_tenant()

    def ins(self, sql, params):
        return int(self.c.execute(self.sql(sql), params).scalar())

    # ------------------------------------------------------------ 建链（提交事务内）
    def _new_tenant(self):
        self.t = self.ins(
            "INSERT INTO app.tenants (name, scope) VALUES (:n, 'internal') RETURNING id",
            {"n": "p02-" + uuid.uuid4().hex[:8]})
        self.pol = self.ins(
            "INSERT INTO app.policy_versions (public_id, tenant_id, policy_type, version, "
            "scope_type, scope_id, content, content_hash, effective_from, effective_to, "
            "approved_by_actor_id) VALUES (gen_random_uuid(), :t, 'cid_breakeven', 'v1', "
            "'global', NULL, '{}', 'h', now(), now() + interval '30 days', "
            "'00000000-0000-0000-0000-000000000003') RETURNING id",
            {"t": self.t})
        self.a = self.ins(
            "INSERT INTO app.platform_accounts (public_id, tenant_id, platform, account_key) "
            "VALUES (gen_random_uuid(), :t, 'wechat_channels', :k) RETURNING id",
            {"t": self.t, "k": "acc-" + uuid.uuid4().hex[:8]})
        self.p = self.ins(
            "INSERT INTO app.products (public_id, tenant_id, title_base, category_id) "
            "VALUES (gen_random_uuid(), :t, 'P', 'cat1') RETURNING id",
            {"t": self.t})
        self.p2 = self.ins(
            "INSERT INTO app.products (public_id, tenant_id, title_base, category_id) "
            "VALUES (gen_random_uuid(), :t, 'P2', 'cat1') RETURNING id",
            {"t": self.t})
        self.sku = self.ins(
            "INSERT INTO app.product_skus (tenant_id, product_id, attributes) "
            "VALUES (:t, :p, '{}') RETURNING id",
            {"t": self.t, "p": self.p})
        self.shop = self.ins(
            "INSERT INTO app.shops (public_id, tenant_id, account_id, platform_shop_id, name) "
            "VALUES (gen_random_uuid(), :t, :a, :ps, 's') RETURNING id",
            {"t": self.t, "a": self.a, "ps": "shop-" + uuid.uuid4().hex[:8]})
        self.listing = self.ins(
            "INSERT INTO app.shop_listings (public_id, tenant_id, account_id, shop_id, product_id, "
            "title_effective, idempotency_key) VALUES (gen_random_uuid(), :t, :a, :s, :p, 'L', :ik) "
            "RETURNING id",
            {"t": self.t, "a": self.a, "s": self.shop, "p": self.p,
             "ik": "lk-" + uuid.uuid4().hex[:8]})
        self.lsku = self.ins(
            "INSERT INTO app.shop_listing_skus (tenant_id, shop_listing_id, sku_id, shop_price) "
            "VALUES (:t, :l, :k, 100) RETURNING id",
            {"t": self.t, "l": self.listing, "k": self.sku})
        self.asset = self.ins(
            "INSERT INTO app.assets (public_id, tenant_id, content_sha256, file_ref, mime_type, "
            "size_bytes, source_type, evidence_hash, captured_at, mode) VALUES "
            "(gen_random_uuid(), :t, repeat('a', 64), 'f1', 'image/png', 100, 'self_created', "
            "repeat('b', 64), now(), 'real') RETURNING id",
            {"t": self.t})
        self.asb = self.ins(
            "INSERT INTO app.asset_shop_bindings (tenant_id, asset_id, shop_id, purpose) "
            "VALUES (:t, :a, :s, 'ad_image') RETURNING id",
            {"t": self.t, "a": self.asset, "s": self.shop})
        self.camp = self.ins(
            "INSERT INTO app.ad_campaigns (public_id, tenant_id, account_id, shop_id, shop_listing_id, "
            "idempotency_key, approved_budget, approved_daily_budget, approved_target_roi, "
            "approved_stop_loss, current_budget, current_daily_budget, current_target_roi, "
            "current_stop_loss, feedback_coefficient, budget_policy_version_id, "
            "cid_policy_version_id) VALUES (gen_random_uuid(), :t, :a, :s, :l, :ik, 1000, 100, 2.0, "
            "0.5, 1000, 100, 2.0, 0.5, 1.0, :pol, :pol) RETURNING id",
            {"t": self.t, "a": self.a, "s": self.shop, "l": self.listing,
             "ik": "ak-" + uuid.uuid4().hex[:8], "pol": self.pol})

    # ------------------------------------------------------------ 观测构造
    def obs(self, version_id="v1", window=None, gmv=0, spend=0, sku=True, asset=True,
            captured=None, platform_updated=None, **kw):
        ws, we = window or (_aware(2026, 1, 1), _aware(2026, 1, 2))
        base = dict(
            tenant_id=self.t, account_id=self.a, shop_id=self.shop,
            shop_listing_id=self.listing,
            shop_listing_sku_id=self.lsku if sku else None,
            product_id=self.p, campaign_id=self.camp,
            asset_binding_id=self.asb if asset else None,
            granularity="campaign", window_start=ws, window_end=we,
            attribution_mode="last_click", platform_version_id=version_id,
            platform_updated_at=platform_updated,
            captured_at=captured or _aware(2026, 1, 1, 12, 0, 0),
            spend=spend, gmv=gmv, impressions=10, clicks=2, orders=1,
            diagnosis="good", status="active",
            raw_evidence=b"raw-" + version_id.encode(),
        )
        base.update(kw)
        return ReportObservation(**base)

    # ------------------------------------------------------------ 清理
    def cleanup(self):
        """finally 精确清理（反向依赖序）；返回 (残留快照数, 残留 campaign 数)。"""
        from sqlalchemy import create_engine

        eng = create_engine(DB_URL)
        with eng.begin() as c:
            c.execute(self.sql("DELETE FROM app.ad_report_snapshots WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.ad_campaign_assets WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.ad_campaigns WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.policy_versions WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.asset_shop_bindings WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.asset_product_bindings WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.assets WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.shop_listing_skus WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.shop_listings WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.shops WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.product_skus WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.products WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.platform_accounts WHERE tenant_id=:t"), {"t": self.t})
            c.execute(self.sql("DELETE FROM app.tenants WHERE id=:t"), {"t": self.t})
        with eng.connect() as c:
            snaps = c.execute(self.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"), {"t": self.t}).scalar()
            camps = c.execute(self.sql(
                "SELECT count(*) FROM app.ad_campaigns WHERE tenant_id=:t"), {"t": self.t}).scalar()
        eng.dispose()
        return {"snapshots": int(snaps), "campaigns": int(camps)}


def _write(conn, ch, version_id="v1", **kw):
    """提交事务内写一条快照（fixture 已提交，worker/新连接可见）；走唯一 public 写入口。"""
    repo = SnapshotRepository(conn)
    return repo.write_observation(ch.obs(version_id, **kw))


def _expect_conflict(conn, ch, obs):
    """SAVEPOINT 内预期 SnapshotContentConflict（冲突内容拒绝，不 abort 外层事务）。

    pytest.raises 包裹整个 begin_nested：异常从 with 块逸出 -> SQLAlchemy ROLLBACK TO SAVEPOINT
    -> 外层事务保持可用（若在块内吞掉异常，RELEASE 已中止的 savepoint 会报 transaction aborted）。"""
    repo = SnapshotRepository(conn)
    with pytest.raises(SnapshotContentConflict):
        with conn.begin_nested():
            repo.write_observation(obs)


def _expect_db_reject(conn, ch, obs):
    """SAVEPOINT 内预期 DB 层拒绝（FK/维度 trigger）；外层事务保持可用（同上理由）。"""
    repo = SnapshotRepository(conn)
    with pytest.raises(Exception):
        with conn.begin_nested():
            repo.write_observation(obs)


def _expect_sqlstate(conn, ch, obs, expected_pgcode, message_fragment=""):
    """R136-2：SAVEPOINT 内预期 DBAPIError 且 exc.orig.pgcode 精确等于 expected_pgcode。

    宽泛 Exception 改为 exact SQLSTATE 断言——语法错误/参数错误/代码缺陷不假通过；
    外层事务保持可用。message_fragment 可选进一步校验 trigger 消息（如 DIMENSION_MISMATCH 细分）。"""
    from sqlalchemy.exc import DBAPIError

    repo = SnapshotRepository(conn)
    with pytest.raises(DBAPIError) as ei:
        with conn.begin_nested():
            repo.write_observation(obs)
    pgcode = getattr(ei.value.orig, "pgcode", "")
    assert pgcode == expected_pgcode, \
        f"{expected_pgcode} 期望, got {pgcode!r}: {ei.value.orig}"
    if message_fragment:
        msg = str(getattr(ei.value.orig, "pgerror", "") or ei.value)
        assert message_fragment in msg, f"消息应含 {message_fragment!r}: {msg[:200]}"


# =====================================================================
# append-only（§四.2）
# =====================================================================
def test_first_insert_created(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            r = _write(c, ch)
            assert isinstance(r, SnapshotWriteResult) and r.created and r.snapshot_id > 0
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 1
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_full_replay_reuses_same_id(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            r1 = _write(c, ch, "v1")
            r2 = _write(c, ch, "v1")
            assert r1.created is True and r2.created is False
            assert r1.snapshot_id == r2.snapshot_id
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_captured_at_change_still_reuses(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            r1 = _write(c, ch, "v1", captured=_aware(2026, 1, 1, 12))
            r2 = _write(c, ch, "v1", captured=_aware(2026, 1, 1, 18))
            assert r1.snapshot_id == r2.snapshot_id and r2.created is False
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


@pytest.mark.parametrize("token", ["captured-v1", "CAPTURED", "recaptured", "CapturedAt"],
                         ids=["lower-captured", "upper-captured", "prefix-recaptured", "camel"])
def test_opaque_version_id_with_captured_text_is_valid(conn, token):
    """R136-1：opaque version ID 含 captured 字面量是合法 token（F132-3 case-sensitive，
    内部字符原样保留）；public ingress 必须接受并可创建/重放（不得被词法哨兵误杀）。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            r1 = _write(c, ch, token)
            assert r1.created is True
            r2 = _write(c, ch, token)  # 重放
            assert r2.created is False and r2.snapshot_id == r1.snapshot_id
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 1
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


# R134-4：完整 comparison set（排除唯一身份字段）逐字段变异冲突 + 旧行逐列保持。
# 唯一身份字段（uq 8 列）：campaign_id/granularity/shop_listing_sku_id/asset_binding_id/
# window_start/window_end/attribution_mode/report_version_key —— 变异这些字段改变 (S,V) 本身，
# 属新建行语义，不进"同 (S,V) 冲突"矩阵；其余 comparison 字段逐项覆盖。
# FK-bound 维度字段（account/shop/listing/product/campaign/sku/asset）由 trg_snapshots_dimension_consistency
# 在 INSERT 前拒绝（BEFORE trigger 先于 ON CONFLICT 判定，见 8 维度矩阵）；比较冲突矩阵覆盖
# 保持维度一致性的不可变事实字段 + tenant_id（不入维度 trigger 检查、保持 FK 一致的字段）。
_COMPARISON_NON_IDENTITY = [
    ("tenant_id", "ch2.t", "tenant"),
    ("platform_updated_at", "ts:set", "platform_updated_at"),
    ("spend", 777, "spend"),
    ("gmv", 999, "gmv"),
    ("roi", Decimal("2.5"), "roi"),
    ("impressions", 555, "impressions"),
    ("clicks", 44, "clicks"),
    ("orders", 3, "orders"),
    ("diagnosis", "excellent", "diagnosis"),
    ("status", "paused", "status"),
]


@pytest.mark.parametrize(
    "field,value_expr,case_id",
    _COMPARISON_NON_IDENTITY,
    ids=[c[2] for c in _COMPARISON_NON_IDENTITY],
)
def test_comparison_field_conflict(conn, field, value_expr, case_id):
    """R134-4：非身份 comparison 字段逐项变异——同 (S,V) 任一不可变事实差异均冲突、旧行逐列保持。

    ch2 引用链：tenant 字段取第二个同构链的合法 id（tenant 不入维度 trigger 检查，
    保持其余维度一致 → 命中唯一冲突 DO NOTHING → 比较集差异 → SnapshotContentConflict）；
    其余事实字段取与首行不同的值。
    """
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = ch2 = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            ch2 = Chain(c)
            r1 = _write(c, ch, "v1")
            value = value_expr
            if value_expr == "ch2.t":
                value = ch2.t
            elif value_expr == "ts:set":
                value = _aware(2026, 1, 1, 6)
            _expect_conflict(c, ch, ch.obs("v1", **{field: value}))
            # 旧行逐列保持（gmv 仍 0）
            gmv = c.execute(ch.sql(
                "SELECT gmv FROM app.ad_report_snapshots WHERE id=:i"),
                {"i": r1.snapshot_id}).scalar()
            assert int(gmv) == 0
            # 事实归零前的行数：仍 1
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id IN (:a,:b)"),
                {"a": ch.t, "b": ch2.t}).scalar()
            assert int(n) == 1
    finally:
        if ch is not None:
            ch.cleanup()
        if ch2 is not None:
            ch2.cleanup()
        eng.dispose()


def test_conflict_leaves_old_row_unchanged_all_cols(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            r1 = _write(c, ch, "v1", gmv=0)
            _expect_conflict(c, ch, ch.obs("v1", gmv=500))
            row = c.execute(ch.sql(
                "SELECT spend, gmv, impressions, clicks, orders, diagnosis, status FROM "
                "app.ad_report_snapshots WHERE id=:i"), {"i": r1.snapshot_id}).first()
            assert tuple(row) == (0, 0, 10, 2, 1, "good", "active")
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 1
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_raw_evidence_hash_conflict(conn):
    """同 (S,V) 但原始证据 bytes 不同（raw_evidence_hash 比较字段）-> 冲突拒绝，旧 hash 保持。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            r1 = _write(c, ch, "v1")  # raw=b"raw-v1" -> hash H1
            obs2 = ReportObservation(**{**ch.obs("v1").__dict__,
                                        "raw_evidence": b"raw-v1-CHANGED"})
            _expect_conflict(c, ch, obs2)
            h = c.execute(ch.sql(
                "SELECT raw_evidence_hash FROM app.ad_report_snapshots WHERE id=:i"),
                {"i": r1.snapshot_id}).scalar()
            from domain.report import hash_raw_evidence
            assert h == hash_raw_evidence(b"raw-v1")
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


# =====================================================================
# NULLS NOT DISTINCT（§四.3）
# =====================================================================
def test_nulls_not_distinct_both_null_reuse(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            r1 = _write(c, ch, "v1", sku=False, asset=False)
            r2 = _write(c, ch, "v1", sku=False, asset=False)
            assert r1.snapshot_id == r2.snapshot_id and r2.created is False
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_nulls_not_distinct_one_null_one_set_are_distinct(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            r1 = _write(c, ch, "v1", sku=False, asset=False)
            r2 = _write(c, ch, "v1", sku=True, asset=False)
            r3 = _write(c, ch, "v1", sku=False, asset=True)
            assert r2.created and r3.created
            assert len({r1.snapshot_id, r2.snapshot_id, r3.snapshot_id}) == 3
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_nulls_not_distinct_both_set_reuse(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            r1 = _write(c, ch, "v1", sku=True, asset=True)
            r2 = _write(c, ch, "v1", sku=True, asset=True)
            assert r1.snapshot_id == r2.snapshot_id and r2.created is False
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


# =====================================================================
# 维度隔离（§四.4；R134-4：八类交叉注入独立用例）
# =====================================================================
# 八维度：tenant/account/shop/listing/SKU/product/campaign/asset——每类把对应字段换成
# chain2（另一同构链）的 id，其余保持 chain1；断言确定错误（FK/维度 trigger，exact SQLSTATE）、
# 外层事务仍可用、事实与 fixture 最终归零。
# SQLSTATE 冻结（round-136 独立 PG 实测）：tenant=23503（fk_ad_report_snapshots_platform_accounts）；
# account/shop=ZT006 shop_id/account_id；listing/product=ZT006 shop_listing_id/shop_id/product_id；
# sku=ZT006 shop_listing_sku_id；campaign=ZT006 campaign_id/shop_listing_id；
# asset=ZT006 asset_binding_id/shop/product/listing。
_DIMENSION_INJECTIONS = [
    ("tenant", lambda ch2, ch1: {"tenant_id": ch2.t}, "23503"),
    ("account", lambda ch2, ch1: {"account_id": ch2.a}, "ZT006"),
    ("shop", lambda ch2, ch1: {"shop_id": ch2.shop}, "ZT006"),
    ("listing", lambda ch2, ch1: {"shop_listing_id": ch2.listing}, "ZT006"),
    ("sku", lambda ch2, ch1: {"shop_listing_sku_id": ch2.lsku}, "ZT006"),
    ("product", lambda ch2, ch1: {"product_id": ch2.p}, "ZT006"),
    ("campaign", lambda ch2, ch1: {"campaign_id": ch2.camp}, "ZT006"),
    ("asset", lambda ch2, ch1: {"asset_binding_id": ch2.asb}, "ZT006"),
]


@pytest.mark.parametrize("dim,mutate,expected_pgcode", _DIMENSION_INJECTIONS,
                         ids=[d[0] for d in _DIMENSION_INJECTIONS])
def test_dimension_injection_rejected(conn, dim, mutate, expected_pgcode):
    """R136-2：八类维度交叉注入——expected SQLSTATE exact-set 断言、外层事务可用、最终零残留。"""
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    chs = []
    try:
        with eng.begin() as c:
            ch1, ch2 = Chain(c), Chain(c)
            chs = [ch1, ch2]
            base = ch1.obs("d1", sku=False, asset=False)
            bad = ReportObservation(**{**base.__dict__, **mutate(ch2, ch1)})
            _expect_sqlstate(c, ch1, bad, expected_pgcode)
            # 外层事务仍可用
            n = c.execute(ch1.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id IN (:a,:b)"),
                {"a": ch1.t, "b": ch2.t}).scalar()
            assert int(n) == 0
    finally:
        for ch in chs:
            ch.cleanup()
        eng.dispose()
    # 新连接断言零残留
    from sqlalchemy import create_engine as ce
    with ce(DB_URL).connect() as c:
        n = c.execute(ch1.sql(
            "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id IN (:a,:b)"),
            {"a": ch1.t, "b": ch2.t}).scalar()
    assert int(n) == 0


# =====================================================================
# 并发（§四.5）——fixture 先提交，worker 用独立引擎
# =====================================================================
def _commit_chain():
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    with eng.begin() as c:
        ch = Chain(c)
    return eng, ch


def test_concurrent_same_value_single_row(conn):
    eng, ch = _commit_chain()
    results = []
    barrier = threading.Barrier(2)

    def worker():
        from sqlalchemy import create_engine

        weng = create_engine(DB_URL)
        with weng.begin() as c:
            repo = SnapshotRepository(c)
            barrier.wait()
            r = repo.write_observation(ch.obs("cv1"))
            results.append((r.snapshot_id, r.created))
        weng.dispose()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    try:
        assert all(not t.is_alive() for t in threads)
        ids = {x[0] for x in results}
        created_flags = [x[1] for x in results]
        assert len(ids) == 1, f"同值并发应只有一行同 id: {results}"
        assert created_flags.count(True) == 1, f"恰一 created=true: {created_flags}"
        with eng.begin() as c:
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 1
    finally:
        ch.cleanup()


def test_concurrent_conflict_content_only_winner(conn):
    eng, ch = _commit_chain()
    results = []
    barrier = threading.Barrier(2)

    def worker(gmv):
        from sqlalchemy import create_engine

        weng = create_engine(DB_URL)
        try:
            with weng.begin() as c:
                repo = SnapshotRepository(c)
                barrier.wait()
                r = repo.write_observation(ch.obs("cv2", gmv=gmv))
                results.append(("ok", r.snapshot_id, r.created))
        except SnapshotContentConflict as exc:
            results.append(("conflict", str(exc)))
        finally:
            weng.dispose()

    threads = [threading.Thread(target=worker, args=(g,)) for g in (100, 200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    try:
        assert all(not t.is_alive() for t in threads)
        oks = [x for x in results if x[0] == "ok"]
        conflicts = [x for x in results if x[0] == "conflict"]
        assert len(oks) == 1 and len(conflicts) == 1, f"恰一胜者+恰一冲突: {results}"
        with eng.begin() as c:
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 1
            gmv = c.execute(ch.sql(
                "SELECT gmv FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(gmv) in (100, 200)
    finally:
        ch.cleanup()


# =====================================================================
# 输入负例（§四.6）—— 经 Collector 校验
# =====================================================================
def test_input_negatives_rejected(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            repo = SnapshotRepository(c)

            def expect_reject(obs):
                # 走唯一 public 写入口：校验在受信边界内完成，任何非法观测必须拒绝
                with pytest.raises(Exception):
                    repo.write_observation(obs)

            base = ch.obs()
            expect_reject(ReportObservation(**{**base.__dict__, "tenant_id": True}))
            expect_reject(ReportObservation(**{**base.__dict__, "spend": True}))
            expect_reject(ReportObservation(**{**base.__dict__, "gmv": -1}))
            expect_reject(ReportObservation(**{**base.__dict__,
                                                "captured_at": datetime.datetime(2026, 1, 1)}))
            expect_reject(ReportObservation(**{**base.__dict__,
                                                "window_start": _aware(2026, 1, 3),
                                                "window_end": _aware(2026, 1, 1)}))
            expect_reject(ReportObservation(**{**base.__dict__,
                                                "window_start": _aware(2026, 1, 1),
                                                "window_end": _aware(2026, 1, 1)}))
            expect_reject(ReportObservation(**{**base.__dict__, "roi": Decimal("NaN")}))
            expect_reject(ReportObservation(**{**base.__dict__, "granularity": "bogus"}))
            expect_reject(ReportObservation(**{**base.__dict__, "diagnosis": "bogus"}))
            expect_reject(ReportObservation(**{**base.__dict__, "status": "bogus"}))
            expect_reject(ReportObservation(**{**base.__dict__, "attribution_mode": ""}))
            expect_reject(ReportObservation(**{**base.__dict__, "raw_evidence": b""}))
            expect_reject(ReportObservation(**{**base.__dict__, "platform_version_id": 123}))
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 0
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


# =====================================================================
# R134-2：非 str version ID 与 utcoffset() is None 时间穿透拒绝（public 写入口级）
# =====================================================================
import datetime as _dt


class _NoneOffsetTZ(_dt.tzinfo):
    """utcoffset() 返回 None 的自定义 tzinfo——必须按 naive 拒绝，防跨宿主时区破坏确定性。"""

    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return "NONE_OFFSET"


def test_version_id_non_str_rejected_via_ingress(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            repo = SnapshotRepository(c)
            base = ch.obs()
            for bad in (123, True, b"bytes-id", object()):
                with pytest.raises(ObservationValidationError):
                    repo.write_observation(
                        ReportObservation(**{**base.__dict__, "platform_version_id": bad}))
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 0
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_none_offset_tz_rejected_via_ingress(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            repo = SnapshotRepository(c)
            base = ch.obs()
            # 四个时间字段逐一注入 utcoffset() is None 的 tzinfo
            none_tz_dt = datetime.datetime(2026, 1, 1, tzinfo=_NoneOffsetTZ())
            for field in ("window_start", "window_end", "captured_at", "platform_updated_at"):
                with pytest.raises(ObservationValidationError):
                    repo.write_observation(
                        ReportObservation(**{**base.__dict__, field: none_tz_dt}))
            n = c.execute(ch.sql(
                "SELECT count(*) FROM app.ad_report_snapshots WHERE tenant_id=:t"),
                {"t": ch.t}).scalar()
            assert int(n) == 0
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


# =====================================================================
# R134-1：受信边界重验（白盒 _validate_draft）——伪造 digest / 错误 version key /
# 类型穿透必须在 INSERT 前被拒绝（对应"跳过 Repository 边界验证"变异 RC=1）
# =====================================================================
def test_draft_boundary_rejects_forged_digest(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            repo = SnapshotRepository(c)
            # 构造合法观测，得到合法 draft 后伪造 digest
            obs = ch.obs("v1")
            repo.write_observation(obs)
            valid_draft = None
            for f in ("shop_id",):  # 占位避免未使用告警
                pass
            # 通过 write_observation 的返回值路径不可伪造 digest；白盒构造内部 draft 验证边界
            from domain.report.repository import _SnapshotDraft
            v = obs
            draft = _SnapshotDraft(
                tenant_id=v.tenant_id, account_id=v.account_id, shop_id=v.shop_id,
                shop_listing_id=v.shop_listing_id, shop_listing_sku_id=v.shop_listing_sku_id,
                product_id=v.product_id, campaign_id=v.campaign_id,
                asset_binding_id=v.asset_binding_id, granularity=v.granularity,
                window_start=v.window_start, window_end=v.window_end,
                attribution_mode=v.attribution_mode, report_version_key="id:v1",
                platform_version_id="v1", platform_updated_at=v.platform_updated_at,
                captured_at=v.captured_at,
                spend=v.spend, gmv=v.gmv, roi=v.roi, impressions=v.impressions,
                clicks=v.clicks, orders=v.orders, diagnosis=v.diagnosis, status=v.status,
                raw_evidence_hash="x",  # 伪造 1 字符 digest
            )
            with pytest.raises(ObservationValidationError):
                repo._validate_draft(draft)
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()


def test_draft_boundary_rejects_wrong_version_key(conn):
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    ch = None
    try:
        with eng.begin() as c:
            ch = Chain(c)
            repo = SnapshotRepository(c)
            from domain.report.repository import _SnapshotDraft
            v = ch.obs("v1")
            draft = _SnapshotDraft(
                tenant_id=v.tenant_id, account_id=v.account_id, shop_id=v.shop_id,
                shop_listing_id=v.shop_listing_id, shop_listing_sku_id=v.shop_listing_sku_id,
                product_id=v.product_id, campaign_id=v.campaign_id,
                asset_binding_id=v.asset_binding_id, granularity=v.granularity,
                window_start=v.window_start, window_end=v.window_end,
                attribution_mode=v.attribution_mode, report_version_key="ts:9999-99-99T99:99:99.999999Z",
                platform_version_id=None, platform_updated_at=v.platform_updated_at,
                captured_at=v.captured_at,
                spend=v.spend, gmv=v.gmv, roi=v.roi, impressions=v.impressions,
                clicks=v.clicks, orders=v.orders, diagnosis=v.diagnosis, status=v.status,
                raw_evidence_hash="a" * 64,  # 合法 digest 但 version key 与三源不一致
            )
            with pytest.raises(ObservationValidationError):
                repo._validate_draft(draft)
    finally:
        if ch is not None:
            ch.cleanup()
        eng.dispose()
