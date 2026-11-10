# -*- coding: utf-8 -*-
"""P0-2 批次 2（C2）：FeedbackService 测试（round-161 授权实现）。

覆盖 round-160 R160-1（单 source 贡献与证据同源）、R160-2（身份先验/重放也验/租户绑定）、
R160-3（savepoint 原子回滚 + 外层提交语义）、审计同事务与 target/after、Service 并发。

运行：cd backend && $env:DATABASE_URL=... python -m pytest tests/test_report_feedback_service.py -q
"""
import datetime
import os
import sys
import threading
import uuid
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from domain.report import (  # noqa: E402
    FeedbackDraft,
    FeedbackRequestError,
    FeedbackService,
    FeedbackSkipped,
    FeedbackValidationError,
    load_source_context,
)
from domain.report.feedback_repository import FeedbackRepository  # noqa: E402
from tests.test_snapshot_repository import Chain  # noqa: E402

DB_URL = os.environ.get("DATABASE_URL", "").strip()
UTC = datetime.timezone.utc
SERVICE_ACTOR = "e57a6a59-da1d-5628-baef-e3b78f12f9e5"
WORKER_ACTOR = "a9a79363-609b-5848-a4b3-33982797cfb8"
SYSTEM_ACTOR = "699f543a-2540-5127-913e-8cca0148db9b"
EMPTY_EV = {"version_selector": {"sorted_snapshot_ids": [], "selected_id": None,
                                 "selection_rule": None, "manual_reason": None,
                                 "null_time_candidates": []}}


# ------------------------------------------------------------------ 基础设施
def _engine():
    from sqlalchemy import create_engine
    return create_engine(DB_URL)


# 清理登记表：即使测试在 `try` 之前（fixture 建立阶段）失败，也保证本用例的 tenant 链被清除。
_PENDING = []


@pytest.fixture(autouse=True)
def _drain_pending():
    yield
    while _PENDING:
        ch, uid = _PENDING.pop()
        try:
            if uid is not None:
                _cleanup_user_actor(ch, uid)
        except Exception:  # noqa: BLE001
            pass
        try:
            _cleanup(ch)
        except Exception:  # noqa: BLE001
            pass


def _req(method, sql, params=None):
    eng = _engine()
    try:
        with eng.begin() as c:
            from sqlalchemy import text
            return method(c, text(sql), params or {})
    finally:
        eng.dispose()


def _read(sql, params=None):
    from sqlalchemy import text
    eng = _engine()
    try:
        with eng.connect() as c:
            return c.execute(text(sql), params or {}).all()
    finally:
        eng.dispose()


def _scalar(sql, params=None):
    rows = _read(sql, params)
    return rows[0][0] if rows else None


def _mk_chain_and_snapshot(*, gmv=100, spend=100, version="v1", granularity="campaign"):
    from domain.report import SnapshotRepository

    eng = _engine()
    with eng.begin() as c:
        ch = Chain(c)
        obs = ch.obs(version, gmv=gmv, spend=spend, granularity=granularity)
        snap = SnapshotRepository(c).write_observation(obs).snapshot_id
    eng.dispose()
    # Chain 未设置 tenants.public_id；C2 需要真实租户 UUID（作为 tenant_public_id / scope）
    from sqlalchemy import text
    eng = _engine()
    with eng.begin() as c:
        c.execute(text("UPDATE app.tenants SET public_id = COALESCE(public_id, gen_random_uuid()) "
                       "WHERE id = :t"), {"t": ch.t})
    eng.dispose()
    ch.public = str(_scalar("SELECT public_id FROM app.tenants WHERE id=:t", {"t": ch.t}))
    ch.camp_public = str(_scalar("SELECT public_id FROM app.ad_campaigns WHERE id=:c",
                                 {"c": ch.camp}))
    ch.prod_public = str(_scalar("SELECT public_id FROM app.products WHERE id=:p", {"p": ch.p}))
    ch.shop_public = str(_scalar("SELECT public_id FROM app.shops WHERE id=:s", {"s": ch.shop}))
    ch.asset_public = str(_scalar("SELECT public_id FROM app.assets WHERE id=:a", {"a": ch.asset}))
    _PENDING.append((ch, None))
    return ch, snap


def _cleanup(ch):
    from sqlalchemy import text
    eng = _engine()
    with eng.begin() as c:
        c.execute(text("DELETE FROM app.roi_feedback_events WHERE tenant_id=:t"), {"t": ch.t})
        c.execute(text("DELETE FROM app.audit_events WHERE tenant_id=:t"), {"t": ch.t})
    eng.dispose()
    ch.cleanup()


def _draft(ch, snap, *, feedback_type="product_score", value=None, extra_over=None,
           subject_key=None, **ctx_over):
    """经 source 真源 + 冻结 calculator 构造合法 draft。"""
    eng = _engine()
    try:
        with eng.connect() as c:
            ctx = load_source_context(c, tenant_id=ch.t, source_snapshot_id=snap,
                                      feedback_type=feedback_type)
    finally:
        eng.dispose()
    from domain.report import compute_contribution
    outcome = compute_contribution(feedback_type, snapshot_id=snap, gmv=ctx.gmv, spend=ctx.spend,
                                   granularity=ctx.granularity)
    extra = {"numerator_gmv": getattr(outcome, "numerator_gmv", 0),
             "denominator_spend": getattr(outcome, "denominator_spend", 0),
             "origin_snapshot_ids": [snap],
             "selector_evidence": dict(EMPTY_EV),
             "aggregation_version": "aggr_v1"}
    if extra_over:
        extra.update(extra_over)
    kw = dict(
        tenant_id=ctx.tenant_id, account_id=ctx.account_id, shop_id=ctx.shop_id,
        shop_listing_id=ctx.shop_listing_id, shop_listing_sku_id=ctx.shop_listing_sku_id,
        product_id=ctx.product_id, campaign_id=ctx.campaign_id,
        asset_binding_id=ctx.asset_binding_id, source_snapshot_id=snap,
        window_start=ctx.window_start, window_end=ctx.window_end,
        attribution_mode=ctx.attribution_mode, feedback_type=feedback_type,
        subject_key=subject_key or ctx.subject_key,
        value=value if value is not None else getattr(outcome, "value", Decimal("0.000000")),
        aggregation_version="aggr_v1", extra_explanation=extra)
    kw.update(ctx_over)
    return FeedbackDraft(**kw)


_UNSET = object()


def _write(draft, *, ch, actor=SERVICE_ACTOR, tenant_public=None, request_id="req-1",
           scope=_UNSET, directory="real"):
    """在显式事务内通过 Service 写入。scope 省略→默认 tenant UUID；显式 None→字面 None。"""
    from infra.auth.pg_directory import PgUserDirectory

    resolved_scope = ch.public if scope is _UNSET else scope
    eng = _engine()
    try:
        with eng.begin() as c:
            users = PgUserDirectory(c) if directory == "real" else None
            svc = FeedbackService(c, user_directory=users)
            return svc.write_event(
                draft, actor_id=actor,
                tenant_public_id=tenant_public if tenant_public is not None else ch.public,
                request_id=request_id,
                worker_scope_tenant_public_id=resolved_scope)
    finally:
        eng.dispose()


def _mk_user_actor(ch, role="operator", status="active"):
    """真实 auth.user + auth.organization(slug=tenant public_id) + auth.member。"""
    from sqlalchemy import text
    uid = str(uuid.uuid4())
    eng = _engine()
    with eng.begin() as c:
        c.execute(text("INSERT INTO auth.user (id, name, email, email_verified, status, "
                       "created_at, updated_at) VALUES (:i, 'u', :e, true, :st, now(), now())"),
                  {"i": uid, "e": f"{uid[:8]}@example.com", "st": status})
        org = c.execute(text("INSERT INTO auth.organization (id, name, slug, created_at) "
                             "VALUES (gen_random_uuid(), 'o', :s, now()) RETURNING id"),
                        {"s": ch.public}).scalar()
        c.execute(text("INSERT INTO auth.member (id, organization_id, user_id, role, created_at) "
                       "VALUES (gen_random_uuid(), :o, :u, :r, now())"),
                  {"o": org, "u": uid, "r": role})
    eng.dispose()
    for i, (c, _u) in enumerate(_PENDING):
        if c is ch:
            _PENDING[i] = (ch, uid)
            break
    return uid


def _cleanup_user_actor(ch, uid):
    from sqlalchemy import text
    eng = _engine()
    with eng.begin() as c:
        c.execute(text("DELETE FROM auth.member WHERE user_id=:u"), {"u": uid})
        c.execute(text("DELETE FROM auth.organization WHERE slug::text = :s"), {"s": ch.public})
        c.execute(text("DELETE FROM auth.user WHERE id=:u"), {"u": uid})
    eng.dispose()


def _ledger_count(ch):
    return _scalar("SELECT count(*) FROM app.roi_feedback_events WHERE tenant_id=:t", {"t": ch.t})


def _audit_count(ch):
    return _scalar("SELECT count(*) FROM app.audit_events WHERE tenant_id=:t AND "
                   "action='p0_2.feedback_write'", {"t": ch.t})


# =====================================================================
# 正例：首写 + 重放 + 审计
# =====================================================================
def test_service_first_write_and_audit():
    ch, snap = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        r = _write(d, ch=ch)
        assert r.created is True
        assert _ledger_count(ch) == 1 and _audit_count(ch) == 1
        row = _read("SELECT action, target_type, target_public_id, request_id, before, after "
                    "FROM app.audit_events WHERE tenant_id=:t", {"t": ch.t})[0]
        assert row[0] == "p0_2.feedback_write" and row[1] == "ad_campaign"
        assert str(row[2]) == ch.camp_public and row[3] == "req-1"
        assert row[4] is None
        after = row[5]
        assert after["ledger_id"] == r.ledger_id
        assert after["source_snapshot_id"] == snap
        assert after["value"] == "1.000000"
        assert after["aggregation_version"] == "aggr_v1"
        assert after["subject_key"] == d.subject_key
    finally:
        _cleanup(ch)


def test_service_replay_no_new_audit():
    ch, snap = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        r1 = _write(d, ch=ch)
        r2 = _write(d, ch=ch, request_id="req-2")
        assert r1.created is True and r2.created is False
        assert r1.ledger_id == r2.ledger_id
        assert _ledger_count(ch) == 1 and _audit_count(ch) == 1
    finally:
        _cleanup(ch)


# =====================================================================
# R160-1 负例：单 source 贡献与证据同源
# =====================================================================
def test_r1601_cross_source_roi_misuse_rejected():
    """100/100 单源被传成跨源 ROI=2.5 → 拒绝。"""
    ch, snap = _mk_chain_and_snapshot(gmv=100, spend=100)
    try:
        d = _draft(ch, snap, value=Decimal("2.500000"))
        with pytest.raises(FeedbackValidationError):
            _write(d, ch=ch)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


def test_r1601_extra_origin_id_rejected():
    ch, snap = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap, extra_over={"origin_snapshot_ids": [snap, 999999]})
        with pytest.raises(FeedbackValidationError):
            _write(d, ch=ch)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


def test_r1601_forged_numerator_denominator_rejected():
    ch, snap = _mk_chain_and_snapshot(gmv=100, spend=100)
    try:
        d = _draft(ch, snap, extra_over={"numerator_gmv": 500})
        with pytest.raises(FeedbackValidationError):
            _write(d, ch=ch)
        d2 = _draft(ch, snap, extra_over={"denominator_spend": 1})
        with pytest.raises(FeedbackValidationError):
            _write(d2, ch=ch)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


def test_r1601_non_canonical_granularity_typed_skip():
    """material_score 的 canonical 是 campaign_asset；campaign 快照 → typed insufficient，零行。"""
    ch, snap = _mk_chain_and_snapshot(granularity="campaign")
    try:
        d = _draft(ch, snap, feedback_type="material_score",
                   subject_key=ch.asset_public)
        r = _write(d, ch=ch)
        assert isinstance(r, FeedbackSkipped) and r.outcome == "insufficient_inputs"
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


def test_r1601_roi_zero_spend_typed_skip():
    ch, snap = _mk_chain_and_snapshot(gmv=100, spend=0)
    try:
        d = _draft(ch, snap, value=Decimal("0.000000"),
                   extra_over={"denominator_spend": 0})
        r = _write(d, ch=ch)
        assert isinstance(r, FeedbackSkipped) and r.outcome == "zero_spend_skipped"
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


def test_r1601_subject_same_source_mismatch_rejected():
    ch, snap = _mk_chain_and_snapshot()
    try:
        other = _scalar("INSERT INTO app.products (public_id, tenant_id, title_base, category_id) "
                        "VALUES (gen_random_uuid(), :t, 'other', 'cat1') RETURNING public_id",
                        {"t": ch.t})
        d = _draft(ch, snap, subject_key=str(other))
        with pytest.raises(FeedbackValidationError):
            _write(d, ch=ch)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


def test_r1601_four_types_positive():
    """product/category/material/shop 四类同源正例（material 需 campaign_asset 快照）。"""
    cases = [
        ("product_score", "campaign", lambda ch: ch.prod_public),
        ("category_score", "campaign", lambda ch: "cat1"),
        ("material_score", "campaign_asset", lambda ch: ch.asset_public),
        ("shop_strategy", "campaign", lambda ch: ch.shop_public),
    ]
    for ft, gran, subject_of in cases:
        ch, snap = _mk_chain_and_snapshot(gmv=100, spend=100, granularity=gran)
        try:
            d = _draft(ch, snap, feedback_type=ft, subject_key=str(subject_of(ch)))
            r = _write(d, ch=ch)
            assert getattr(r, "created", False) is True, (ft, r)
            assert _ledger_count(ch) == 1 and _audit_count(ch) == 1
            v = _scalar("SELECT value FROM app.roi_feedback_events WHERE tenant_id=:t", {"t": ch.t})
            assert Decimal(v) == Decimal("1.000000")
        finally:
            _cleanup(ch)


def test_r1601_sku_gate_closed():
    """D1 选项 B：sku_margin 返回 typed gate-closed，零行零审计。"""
    ch, snap = _mk_chain_and_snapshot(gmv=100, spend=0)
    try:
        d = _draft(ch, snap, feedback_type="sku_margin", subject_key=str(uuid.uuid4()),
                   value=Decimal("100.000000"),
                   extra_over={"denominator_spend": 0})
        r = _write(d, ch=ch)
        assert isinstance(r, FeedbackSkipped) and r.outcome == "sku_gate_closed"
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


# =====================================================================
# R160-2：身份先验（含重放）
# =====================================================================
def test_r1602_forged_actor_rejected():
    ch, snap = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        with pytest.raises(Exception):
            _write(d, ch=ch, actor=str(uuid.uuid4()))
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


def test_r1602_missing_directory_fail_closed():
    ch, snap = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        with pytest.raises(Exception):
            _write(d, ch=ch, directory=None)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


def test_r1602_wrong_tenant_rejected():
    ch, snap = _mk_chain_and_snapshot()
    ch2, _ = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        with pytest.raises(Exception):
            _write(d, ch=ch, tenant_public=ch2.public)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)
        _cleanup(ch2)


def test_r1602_viewer_role_rejected():
    ch, snap = _mk_chain_and_snapshot()
    uid = _mk_user_actor(ch, role="viewer")
    try:
        d = _draft(ch, snap)
        with pytest.raises(Exception):
            _write(d, ch=ch, actor=uid)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup_user_actor(ch, uid)
        _cleanup(ch)


def test_r1602_operator_user_positive():
    ch, snap = _mk_chain_and_snapshot()
    uid = _mk_user_actor(ch, role="operator")
    try:
        d = _draft(ch, snap)
        r = _write(d, ch=ch, actor=uid)
        assert r.created is True
        assert _ledger_count(ch) == 1 and _audit_count(ch) == 1
    finally:
        _cleanup_user_actor(ch, uid)
        _cleanup(ch)


def test_r1602_worker_wrong_scope_rejected():
    ch, snap = _mk_chain_and_snapshot()
    ch2, _ = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        with pytest.raises(Exception):
            _write(d, ch=ch, actor=WORKER_ACTOR, scope=ch2.public)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)
        _cleanup(ch2)


def test_r1602_worker_correct_scope_positive():
    ch, snap = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        r = _write(d, ch=ch, actor=WORKER_ACTOR, scope=ch.public)
        assert r.created is True
    finally:
        _cleanup(ch)


def test_r1602_service_scope_missing_or_mismatch_rejected():
    """service/system 分支本身免 scope；Service 额外强制可信 scope == 实际 tenant。"""
    ch, snap = _mk_chain_and_snapshot()
    ch2, _ = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        with pytest.raises(FeedbackRequestError):
            _write(d, ch=ch, actor=SERVICE_ACTOR, scope=None)
        with pytest.raises(FeedbackRequestError):
            _write(d, ch=ch, actor=SERVICE_ACTOR, scope=ch2.public)
        with pytest.raises(FeedbackRequestError):
            _write(d, ch=ch, actor=SYSTEM_ACTOR, scope=None)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)
        _cleanup(ch2)


def test_r1602_empty_request_id_rejected():
    ch, snap = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        for bad in ("", None):
            with pytest.raises(FeedbackRequestError):
                _write(d, ch=ch, request_id=bad)
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


def test_r1602_replay_also_validates_identity():
    """已存在行 + 伪造 actor 的重放必须先被身份校验拒绝（不得直接返回 created=false）。"""
    ch, snap = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        r1 = _write(d, ch=ch)
        assert r1.created is True
        with pytest.raises(Exception):
            _write(d, ch=ch, actor=str(uuid.uuid4()), request_id="req-replay")
        # 原行不变、无新增 audit
        assert _ledger_count(ch) == 1 and _audit_count(ch) == 1
        # 合法重放仍返回同 id、created=false、不新增 audit
        r2 = _write(d, ch=ch, request_id="req-ok")
        assert r2.created is False and r2.ledger_id == r1.ledger_id
        assert _audit_count(ch) == 1
    finally:
        _cleanup(ch)


# =====================================================================
# R160-3：savepoint 原子回滚 + 外层提交语义
# =====================================================================
def test_r1603_audit_failure_savepoint_rollback_outer_commit_keeps_nothing(monkeypatch):
    """调用方捕获审计异常后仍提交外层事务：本次 ledger/audit 均 0，且此前无关合法操作保留。"""
    import domain.report.feedback_service as fs

    ch, snap = _mk_chain_and_snapshot()
    try:
        good = _draft(ch, snap)

        class Boom(RuntimeError):
            pass

        def _raise(*a, **k):
            raise Boom("audit fault injection")

        monkeypatch.setattr(fs, "_audit_writer", lambda: _raise)

        marker = "c2-r1603-marker-" + uuid.uuid4().hex[:8]
        from sqlalchemy import text
        from infra.auth.pg_directory import PgUserDirectory
        eng = _engine()
        try:
            with eng.begin() as c:
                # 此前无关的合法操作（同外层事务内；不依赖审计）
                c.execute(text("INSERT INTO app.products (public_id, tenant_id, title_base, "
                               "category_id) VALUES (gen_random_uuid(), :t, :m, 'cat1')"),
                          {"t": ch.t, "m": marker})
                svc = FeedbackService(c, user_directory=PgUserDirectory(c))
                raised = False
                try:
                    svc.write_event(good, actor_id=SERVICE_ACTOR,
                                    tenant_public_id=ch.public, request_id="req-boom",
                                    worker_scope_tenant_public_id=ch.public)
                except Boom:
                    raised = True
                assert raised is True, "审计注入异常必须传播到调用方"
                # 外层事务在捕获异常后仍然提交
        finally:
            eng.dispose()

        # 本次调用零 ledger / 零 audit；此前的无关合法行保留
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
        n = _scalar("SELECT count(*) FROM app.products WHERE tenant_id=:t AND title_base=:m",
                    {"t": ch.t, "m": marker})
        assert n == 1, "外层事务此前无关的合法操作必须保持"
    finally:
        _cleanup(ch)


def test_r1603_exception_propagates_and_rolls_back_savepoint():
    """校验异常发生在 savepoint 内 → 传播；外层若回滚则零残留。"""
    ch, snap = _mk_chain_and_snapshot(gmv=100, spend=100)
    try:
        bad = _draft(ch, snap, value=Decimal("9.000000"))
        from sqlalchemy import create_engine as _ce
        from infra.auth.pg_directory import PgUserDirectory
        eng = _ce(DB_URL)
        try:
            c = eng.connect()
            tx = c.begin()
            svc = FeedbackService(c, user_directory=PgUserDirectory(c))
            with pytest.raises(FeedbackValidationError):
                svc.write_event(bad, actor_id=SERVICE_ACTOR, tenant_public_id=ch.public,
                                request_id="req-bad", worker_scope_tenant_public_id=ch.public)
            tx.rollback()
            c.close()
        finally:
            eng.dispose()
        assert _ledger_count(ch) == 0 and _audit_count(ch) == 0
    finally:
        _cleanup(ch)


# =====================================================================
# Service 并发：恰一 ledger / 恰一成功审计 / 恰一 created=true
# =====================================================================
def test_service_concurrency_exactly_one_created():
    ch, snap = _mk_chain_and_snapshot()
    try:
        d = _draft(ch, snap)
        barrier = threading.Barrier(2)
        results, errors = [], []

        def worker():
            from infra.auth.pg_directory import PgUserDirectory
            eng = _engine()
            try:
                with eng.begin() as c:
                    svc = FeedbackService(c, user_directory=PgUserDirectory(c))
                    barrier.wait(timeout=10)
                    results.append(svc.write_event(
                        d, actor_id=SERVICE_ACTOR, tenant_public_id=ch.public,
                        request_id=f"req-{threading.get_ident()}",
                        worker_scope_tenant_public_id=ch.public))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                eng.dispose()

        ts = [threading.Thread(target=worker) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=20)

        assert errors == []
        created = [r for r in results if r.created]
        assert len(created) == 1, results
        assert len({r.ledger_id for r in results}) == 1
        assert _ledger_count(ch) == 1 and _audit_count(ch) == 1
    finally:
        _cleanup(ch)

