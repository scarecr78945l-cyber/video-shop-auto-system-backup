# -*- coding: utf-8 -*-
"""T8: workflow run/step + 最小队列测试（round-105；round-107 R106-1~R106-4 定稿）。

覆盖 docs/contracts/test-strategy.md §四（隐式租约机械断言，9 项）+ R106 回修：
- R106-1：首次 claim attempt=1；backoff 到期才可重领；熔断最短等待不被调用方覆盖；预算耗尽终态；
  错误分流（retryable→gate_retry / manual_takeover→manual_review / terminal→failed）；
- R106-2：幂等键黄金向量 V1/V2/V3 现场复算；真实 key 入库；run 并发同 key 返回原资源；
- R106-3：父 run 状态门禁（cancelled/paused/manual/done/failed 不可 claim/recover）；run 生命周期控制；
- R106-4：并发测试 finally 精确清理，连续两次新连接验证 fixture 归零。

运行：cd backend && python -m pytest tests/test_workflow_queue.py -q --basetemp=.pytest-tmp-t8
"""
import datetime
import os
import sys
import threading
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from domain.workflow import (  # noqa: E402
    ERROR_ENTRIES,
    HEARTBEAT_MAX_MINUTES,
    LEASE_MINUTES,
    RETRY_POLICIES,
    STALE_ATTEMPT_MSG,
    WorkflowQueue,
    WorkflowQueueError,
    _canonical_join,
    compute_run_key,
    compute_step_action_key,
)

DB_URL = os.environ.get("DATABASE_URL", "").strip()


@pytest.fixture()
def conn():
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过 workflow 队列验收")
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


def _new_tenant(conn):
    from sqlalchemy import text as sqltext

    row = conn.execute(sqltext(
        "INSERT INTO app.tenants (name, scope) VALUES (:n, 'internal') RETURNING id, public_id"),
        {"n": "t8-" + uuid.uuid4().hex[:8]}).first()
    return int(row[0]), str(row[1])


def _setup(conn):
    """创建 run + 一个 pending step；返回 (queue, tenant_id, run_id, step_id, action_key)。"""
    tid, tpub = _new_tenant(conn)
    q = WorkflowQueue(conn)
    run_id, created = q.ensure_run(
        tenant_id=tid, tenant_public_id=tpub, run_type="listing_flow",
        idempotency_key=compute_run_key(tpub, "manual", str(uuid.uuid4()), "w1", "p1"),
        trigger_type="manual", trigger_public_id=str(uuid.uuid4()),
        schedule_window="w1", policy_version_id="p1", input_ref="it:input",
    )
    assert created
    run_pub = str(conn.execute(
        __import__("sqlalchemy").text("SELECT public_id FROM app.workflow_runs WHERE id=:r"),
        {"r": run_id}).scalar())
    action_key = compute_step_action_key(tpub, run_pub, "listing_submit", "submit", None)
    step_id = q.enqueue_step(tenant_id=tid, run_id=run_id, step_type="listing_submit",
                             action_idempotency_key=action_key)
    return q, tid, tpub, run_id, step_id, action_key


# ---------------------------------------------------------------------------
# R106-2：幂等键黄金向量（idempotency.md §一 现场复算）
# ---------------------------------------------------------------------------
def test_golden_vectors_v1_v2_v3():
    t = "00000000-0000-0000-0000-000000000001"
    r = "00000000-0000-0000-0000-000000000002"
    assert compute_step_action_key(t, r, "listing_submit", "product_submit_audit",
                                   "00000000-0000-0000-0000-000000000003") == \
        "step:v1:5e47863b2530cda2957f894411abb214bbbf811e9c8ff42f274185c31954d614"
    assert compute_step_action_key(t, r, "campaign_start", "campaign_start", None) == \
        "step:v1:147949e3b728782d8bf9f784cb88d4228313458f1c0246d6e37c3f1967547deb"
    assert compute_step_action_key(t, r, "material_upload", "material_upload", "a|b\\c中") == \
        "step:v1:8fc40e4a65af1c77e59838cd2b04232b3165f404cd87f84c032f05ac17525245"


def test_canonical_join_escaping_order():
    # 转义顺序：先反斜杠后竖线（R106-2）；输入 a|b\c（单竖线+单反斜杠）
    assert _canonical_join(["a|b\\c"]) == "a\\|b\\\\c"
    # 分隔歧义消除：a:b|c vs a|b:c 不同 key（hash 后不同即消除）
    t = "t"; r = "r"
    assert compute_step_action_key(t, r, "a:b", "c", None) != compute_step_action_key(t, r, "a", "b:c", None)
    # NULL→nil 由黄金向量 V2 覆盖（idempotency.md §一）；此处验证 hash 长度
    assert len(compute_step_action_key(t, r, "s", "slot", None)) == len("step:v1:") + 64


def test_run_key_without_tenant():
    # idempotency.md 键 10：输入序 trigger_type|trigger_public_id|schedule_window|policy_version_id（不含 tenant）
    import hashlib
    expected = "run:v1:" + hashlib.sha256(b"manual|00000000-0000-0000-0000-000000000003|w1|p1").hexdigest()
    assert compute_run_key("ignored-tenant", "manual",
                           "00000000-0000-0000-0000-000000000003", "w1", "p1") == expected


def test_generated_key_insertable(conn):
    """R106-2：真实 run.public_id 生成 key 可入库（varchar(128) 不超长）。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    assert len(action_key) <= 128
    # 同一 key 幂等入队不超长/不新增
    step_id2 = q.enqueue_step(tenant_id=tid, run_id=run_id, step_type="listing_submit",
                              action_idempotency_key=action_key)
    assert step_id2 == step_id
    assert conn.execute(sqltext(
        "SELECT count(*) FROM app.workflow_steps WHERE run_id=:r"), {"r": run_id}).scalar() == 1


def test_concurrent_ensure_run_same_key(conn):
    """R106-2/R108-4：两连接并发 ensure_run 同 key -> 同 id，created 仅一 true，无 23505；
    fixture 从提交起进入 finally（worker 异常/超时也精确清理）。"""
    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    tid = tpub = None
    try:
        with eng.begin() as c:
            tid, tpub = _new_tenant(c)
        shared_key = compute_run_key(tpub, "manual", str(uuid.uuid4()), "w1", "p1")
        barrier = threading.Barrier(2)
        results = []

        def worker():
            with eng.connect() as c:
                tx = c.begin()
                try:
                    q = WorkflowQueue(c)
                    barrier.wait(timeout=10)
                    res = q.ensure_run(
                        tenant_id=tid, tenant_public_id=tpub, run_type="listing_flow",
                        idempotency_key=shared_key, trigger_type="manual",
                        trigger_public_id=str(uuid.uuid4()), schedule_window="w1",
                        policy_version_id="p1")
                    tx.commit()
                    results.append(res)
                except Exception as exc:  # noqa: BLE001
                    tx.rollback()
                    results.append(("error", type(exc).__name__))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=15)
        assert len(results) == 2
        ids = [r[0] for r in results]
        assert ids[0] == ids[1]  # 同一 id
        created_flags = [r[1] for r in results]
        assert created_flags.count(True) == 1  # 仅一个 true
    finally:
        # R108-4：finally 精确清理（worker 异常/超时也执行）
        with eng.begin() as c:
            c.execute(sqltext("DELETE FROM app.workflow_steps WHERE run_id IN "
                              "(SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
        eng.dispose()
    # 新连接断言 fixture 归零
    with create_engine(DB_URL).connect() as c:
        assert c.execute(sqltext(
            "SELECT count(*) FROM app.tenants WHERE id=:t"), {"t": tid}).scalar() == 0


# ---------------------------------------------------------------------------
# R106-1：attempt 语义 + backoff + 分流
# ---------------------------------------------------------------------------
def test_first_claim_attempt_kept_1(conn):
    """R106-1.1：首次 claim attempt 保持 1（test-strategy §四.3）。"""
    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    token = q.claim(run_id=run_id)
    assert token is not None
    got_id, attempt = token
    assert got_id == step_id
    assert attempt == 1  # 首次 claim 不递增


def test_recover_increments_attempt(conn):
    """回收后 attempt 恰增 1（45min 无 heartbeat -> pending + attempt+1）。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    assert attempt == 1
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET updated_at = now() - interval '46 minutes' "
        "WHERE id=:s"), {"s": got_id})
    assert q.recover_stale_attempts() == 1
    token2 = q.claim(run_id=run_id)
    assert token2 is not None
    assert token2[0] == got_id
    assert token2[1] == 2  # 回收后恰增 1


def test_gate_retry_increments_attempt(conn):
    """gate_retry 进入新 attempt 恰增 1；backoff 到期后 claim 保持该值。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    assert attempt == 1
    q.gate_retry(step_id=got_id, attempt=attempt, error_code="NO_MATCH", gate_result={})
    # 模拟 120s backoff 已过（NO_MATCH=120s；把 retry_at 置过去）
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET gate_result = "
        "jsonb_set(COALESCE(gate_result,'{}'), '{retry_at}', "
        "to_jsonb((now() - interval '2 minutes')::text)) WHERE id=:i"), {"i": got_id})
    token2 = q.claim(run_id=run_id)
    assert token2 is not None
    assert token2[0] == got_id
    assert token2[1] == 2  # gate_retry 后恰增 1（claim 保持）


def test_backoff_not_expired_blocks_claim(conn):
    """R106-1.2：backoff 未到期不可重领（TIMEOUT=60s）。"""
    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    q.gate_retry(step_id=got_id, attempt=attempt, error_code="TIMEOUT", gate_result={})
    assert q.claim(run_id=run_id) is None  # 60s 内不可重领


def test_backoff_expired_allows_claim(conn):
    """R106-1.2：backoff 到期可重领（SQL 把 retry_at 置过去模拟时间流逝）。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    q.gate_retry(step_id=got_id, attempt=attempt, error_code="TIMEOUT", gate_result={})
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET gate_result = "
        "jsonb_set(COALESCE(gate_result,'{}'), '{retry_at}', "
        "to_jsonb((now() - interval '2 minutes')::text)) WHERE id=:i"), {"i": got_id})
    token = q.claim(run_id=run_id)
    assert token is not None
    assert token[0] == got_id
    assert token[1] == 2


def test_caller_cannot_override_circuit_breaker(conn):
    """R106-1.2：RATE_LIMIT 熔断最短等待不被调用方覆盖（传入过去 retry_at 仍按 300s 熔断）。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    # attempt=1 < circuit_open_after=2：正常 backoff=180s；注入过去 retry_at 应被忽略
    q.gate_retry(step_id=got_id, attempt=attempt, error_code="RATE_LIMIT",
                 gate_result={"retry_at": "2000-01-01T00:00:00Z"})
    row = conn.execute(sqltext(
        "SELECT gate_result FROM app.workflow_steps WHERE id=:i"), {"i": got_id}).first()
    retry_at = row[0]["retry_at"] if row[0] else None
    # retry_at 由注册表 backoff 生成（未来 180s），非调用方 past 值
    assert retry_at is not None
    parsed = datetime.datetime.fromisoformat(retry_at)
    assert parsed > datetime.datetime.now(datetime.timezone.utc)
    assert q.claim(run_id=run_id) is None  # 未到期不可重领


def test_rate_limit_circuit_open_300s(conn):
    """R106-1.2：RATE_LIMIT 第 2 次（attempt=2 >= circuit_open_after=2）进入 300s 熔断。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, a1 = q.claim(run_id=run_id)
    q.gate_retry(step_id=got_id, attempt=a1, error_code="RATE_LIMIT", gate_result={})
    # 模拟 180s backoff 到期后第 2 次领取（attempt=2）
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET gate_result = "
        "jsonb_set(COALESCE(gate_result,'{}'), '{retry_at}', "
        "to_jsonb((now() - interval '4 minutes')::text)) WHERE id=:i"), {"i": got_id})
    got_id2, a2 = q.claim(run_id=run_id)
    assert a2 == 2
    q.gate_retry(step_id=got_id2, attempt=a2, error_code="RATE_LIMIT", gate_result={})
    row = conn.execute(sqltext(
        "SELECT gate_result FROM app.workflow_steps WHERE id=:i"), {"i": got_id}).first()
    retry_at = datetime.datetime.fromisoformat(row[0]["retry_at"])
    delta = (retry_at - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    assert delta >= 290  # ~300s 熔断


def test_gate_retry_budget_exhausted_terminal(conn):
    """R106-1.1：NO_MATCH max_attempts=2——首轮失败后仍有一次重试，耗尽才 failed。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, a1 = q.claim(run_id=run_id)
    assert a1 == 1
    q.gate_retry(step_id=got_id, attempt=a1, error_code="NO_MATCH", gate_result={})
    # 首轮失败后 status=gate_retry（不是 failed），attempt=2
    st = conn.execute(sqltext(
        "SELECT status, attempt FROM app.workflow_steps WHERE id=:i"), {"i": got_id}).first()
    assert st[0] == "gate_retry"
    assert st[1] == 2
    # 模拟 120s 到期后第 2 次执行
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET gate_result = "
        "jsonb_set(COALESCE(gate_result,'{}'), '{retry_at}', "
        "to_jsonb((now() - interval '2 minutes')::text)) WHERE id=:i"), {"i": got_id})
    got_id2, a2 = q.claim(run_id=run_id)
    assert a2 == 2
    q.gate_retry(step_id=got_id2, attempt=a2, error_code="NO_MATCH", gate_result={})
    st2 = conn.execute(sqltext(
        "SELECT status FROM app.workflow_steps WHERE id=:i"), {"i": got_id}).first()
    assert st2[0] == "failed"  # 预算耗尽 -> 终态
    assert q.claim(run_id=run_id) is None


# ---------------------------------------------------------------------------
# R106-1.3：错误分流（manual_takeover -> manual_review）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", ["AUTH_REQUIRED", "VERIFICATION_REQUIRED", "PAGE_CHANGED",
                                  "PLATFORM_REJECT"])
def test_manual_takeover_routes_to_manual_review(conn, code):
    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    target = q.handle_error(step_id=got_id, attempt=attempt, error_code=code)
    assert target == "manual_review"
    from sqlalchemy import text as sqltext

    st = conn.execute(sqltext(
        "SELECT status, error_code FROM app.workflow_steps WHERE id=:i"), {"i": got_id}).first()
    assert st[0] == "manual_review"
    assert st[1] == code
    assert q.claim(run_id=run_id) is None  # manual_review 不可 claim


def test_retryable_routes_to_gate_retry(conn):
    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    target = q.handle_error(step_id=got_id, attempt=attempt, error_code="TIMEOUT")
    assert target == "gate_retry"


def test_unknown_code_routes_to_failed(conn):
    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    target = q.handle_error(step_id=got_id, attempt=attempt, error_code="UNKNOWN_CODE")
    assert target == "failed"


def test_error_registry_entries_match_yaml():
    """R106-1：错误注册表逐码核对 entries 值（retryable/backoff/manual_takeover）。"""
    expected = {
        "RATE_LIMIT": (True, 180, False), "TIMEOUT": (True, 60, False),
        "NO_MATCH": (True, 120, False), "UNEXPECTED": (True, 60, False),
        "INSUFFICIENT_REFERENCES": (True, 120, False),
        "AUTH_REQUIRED": (False, 0, True), "VERIFICATION_REQUIRED": (False, 0, True),
        "PAGE_CHANGED": (False, 0, True), "PLATFORM_REJECT": (False, 0, True),
    }
    for code, (retry, backoff, manual) in expected.items():
        e = ERROR_ENTRIES[code]
        assert e["retryable"] == retry
        assert e["backoff_seconds"] == backoff
        assert e["manual_takeover"] == manual
    assert set(RETRY_POLICIES) == {"RATE_LIMIT", "TIMEOUT", "NO_MATCH",
                                   "INSUFFICIENT_REFERENCES", "UNEXPECTED"}


# ---------------------------------------------------------------------------
# 1/2/3（基础）: claim fencing / 并发 / stale attempt
# ---------------------------------------------------------------------------
def test_concurrent_claim_single_winner(conn):
    """两 worker 并发 claim 同一 run 的单个 step，仅一方成功（SKIP LOCKED）+ finally 精确清理。"""
    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    tid = tpub = None
    try:
        with eng.begin() as c:
            tid, tpub = _new_tenant(c)
            q = WorkflowQueue(c)
            run_id, _ = q.ensure_run(
                tenant_id=tid, tenant_public_id=tpub, run_type="listing_flow",
                idempotency_key=compute_run_key(tpub, "manual", str(uuid.uuid4()), "w1", "p1"),
                trigger_type="manual", trigger_public_id=str(uuid.uuid4()),
                schedule_window="w1", policy_version_id="p1")
            run_pub = str(c.execute(sqltext(
                "SELECT public_id FROM app.workflow_runs WHERE id=:r"), {"r": run_id}).scalar())
            action_key = compute_step_action_key(tpub, run_pub, "listing_submit", "submit", None)
            q.enqueue_step(tenant_id=tid, run_id=run_id, step_type="listing_submit",
                           action_idempotency_key=action_key)
        c1 = eng.connect(); c2 = eng.connect()
        tx1 = c1.begin(); tx2 = c2.begin()
        try:
            q1 = WorkflowQueue(c1); q2 = WorkflowQueue(c2)
            r1, r2 = {}, {}
            barrier = threading.Barrier(2)

            def worker(qq, res):
                barrier.wait(timeout=5)
                res["token"] = qq.claim(run_id=run_id)

            t1 = threading.Thread(target=worker, args=(q1, r1))
            t2 = threading.Thread(target=worker, args=(q2, r2))
            t1.start(); t2.start()
            t1.join(timeout=10); t2.join(timeout=10)
            winners = [r for r in (r1["token"], r2["token"]) if r is not None]
            assert len(winners) == 1  # 仅一方成功
            tx1.commit(); tx2.commit()
        finally:
            c1.close(); c2.close()
    finally:
        # R106-4：finally 精确清理（worker 异常/超时也清理）
        with eng.begin() as c:
            c.execute(sqltext("DELETE FROM app.workflow_steps WHERE run_id IN "
                              "(SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
        eng.dispose()
    # 新连接断言 fixture 归零
    with create_engine(DB_URL).connect() as c:
        assert c.execute(sqltext(
            "SELECT count(*) FROM app.tenants WHERE id=:t"), {"t": tid}).scalar() == 0
        assert c.execute(sqltext(
            "SELECT count(*) FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid}).scalar() == 0


def test_recover_stale_increments_attempt_basic(conn):
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET updated_at = now() - interval '46 minutes' "
        "WHERE id=:s"), {"s": got_id})
    assert q.recover_stale_attempts() == 1
    token2 = q.claim(run_id=run_id)
    assert token2 is not None
    assert token2[1] == attempt + 1


@pytest.mark.parametrize("action", ["heartbeat", "complete", "fail", "gate_retry"])
def test_stale_attempt_rejected(conn, action):
    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    stale_attempt = attempt + 999
    kwargs = {"step_id": got_id, "attempt": stale_attempt}
    if action == "heartbeat":
        fn = q.heartbeat
    elif action == "complete":
        fn = q.complete
    elif action == "fail":
        fn = q.fail
    else:
        fn = q.gate_retry
        kwargs["error_code"] = "TIMEOUT"
    with pytest.raises(WorkflowQueueError, match=STALE_ATTEMPT_MSG):
        fn(**kwargs)
    if action == "heartbeat":
        q.heartbeat(step_id=got_id, attempt=attempt)
    elif action == "complete":
        q.complete(step_id=got_id, attempt=attempt, evidence_ref="ev:t8")
    elif action == "fail":
        q.fail(step_id=got_id, attempt=attempt, error_code="PAGE_CHANGED")
    else:
        q.gate_retry(step_id=got_id, attempt=attempt, error_code="TIMEOUT", gate_result={})


def test_heartbeat_extends_lease(conn):
    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    q.heartbeat(step_id=got_id, attempt=attempt)
    assert q.recover_stale_attempts() == 0
    assert LEASE_MINUTES == 45
    assert HEARTBEAT_MAX_MINUTES == 15


@pytest.mark.parametrize("status", ["manual_review", "done", "failed"])
def test_unclaimable_states(conn, status):
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET status=:s WHERE id=:i"), {"s": status, "i": step_id})
    assert q.claim(run_id=run_id) is None


def test_failed_terminal_no_recover(conn):
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET status='failed', updated_at = now() - interval '46 minutes' "
        "WHERE id=:i"), {"i": step_id})
    assert q.recover_stale_attempts() == 0
    assert q.claim(run_id=run_id) is None


# ---------------------------------------------------------------------------
# R106-3：父 run 状态门禁 + 生命周期
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("run_status", ["cancelled", "paused", "waiting_manual", "done", "failed"])
def test_parent_run_gate_blocks_claim(conn, run_status):
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    q.set_run_status(run_id=run_id, status=run_status)
    assert q.claim(run_id=run_id) is None  # 非 running 父 run 不可 claim
    assert q.recover_stale_attempts() == 0  # 也不回收


def test_parent_run_cancelled_stops_recovery(conn):
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET updated_at = now() - interval '46 minutes' "
        "WHERE id=:i"), {"i": got_id})
    q.set_run_status(run_id=run_id, status="cancelled")
    assert q.recover_stale_attempts() == 0  # cancelled 父 run 不回收


def test_run_lifecycle_controls(conn):
    """R106-3：pause/resume/cancel/finalize + state/output_ref 持久化。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    q.set_run_status(run_id=run_id, status="paused", state="it:paused")
    st = conn.execute(sqltext(
        "SELECT status, state FROM app.workflow_runs WHERE id=:r"), {"r": run_id}).first()
    assert st[0] == "paused" and st[1] == "it:paused"
    q.set_run_status(run_id=run_id, status="running")
    assert q.claim(run_id=run_id) is not None  # resume 后可领
    q.set_run_status(run_id=run_id, status="done", output_ref="it:output")
    st2 = conn.execute(sqltext(
        "SELECT status, output_ref FROM app.workflow_runs WHERE id=:r"), {"r": run_id}).first()
    assert st2[0] == "done" and st2[1] == "it:output"


# ---------------------------------------------------------------------------
# 8. action_idempotency_key 恒定（不含 attempt）
# ---------------------------------------------------------------------------
def test_action_key_stable_across_attempts(conn):
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    q.gate_retry(step_id=got_id, attempt=attempt, error_code="TIMEOUT", gate_result={})
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET gate_result = "
        "jsonb_set(COALESCE(gate_result,'{}'), '{retry_at}', "
        "to_jsonb((now() - interval '2 minutes')::text)) WHERE id=:i"), {"i": got_id})
    token2 = q.claim(run_id=run_id)
    assert token2 is not None and token2[1] == 2
    rows = conn.execute(sqltext(
        "SELECT action_idempotency_key, attempt FROM app.workflow_steps WHERE id=:i"),
        {"i": got_id}).all()
    assert len(rows) == 1
    assert rows[0][0] == action_key  # 恒定
    assert "attempt" not in action_key
    assert action_key.startswith("step:v1:")


# ---------------------------------------------------------------------------
# 9. 索引覆盖（N1/N2）
# ---------------------------------------------------------------------------
def test_index_coverage(conn):
    from sqlalchemy import text as sqltext

    rows = conn.execute(sqltext(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='app' "
        "AND tablename IN ('workflow_steps','workflow_runs')")).all()
    defs = " ".join(r[1] for r in rows)
    assert "ix_steps_status_updated" in defs
    assert "ix_runs_status_updated" in defs


# ---------------------------------------------------------------------------
# R108-1：UUID/时间规范化 + 不同 action key 冲突显式拒绝
# ---------------------------------------------------------------------------
def test_uuid_case_normalized_step_key():
    """R108-1：已知 UUID 字段大小写等价表示生成同 key（idempotency.md 小写规范形式）。"""
    uid = "abcdefab-cdef-4abc-8abc-abcdefabcdef"
    assert compute_step_action_key(uid, uid, "listing_submit", "slot") == \
        compute_step_action_key(uid.upper(), uid, "listing_submit", "slot")


def test_uuid_case_normalized_run_key():
    uid = "abcdefab-cdef-4abc-8abc-abcdefabcdef"
    assert compute_run_key(uid, "manual", uid, "w1", "p1") == \
        compute_run_key(uid, "manual", uid.upper(), "w1", "p1")


def test_time_normalized_run_key():
    """R108-1：时间型字段 UTC ISO-8601 等价（同一时刻不同时区表示 -> 同 key）。"""
    uid = "abcdefab-cdef-4abc-8abc-abcdefabcdef"
    assert compute_run_key(uid, "manual", uid, "2026-09-06T00:00:00Z", "p1") == \
        compute_run_key(uid, "manual", uid, "2026-09-06T08:00:00+08:00", "p1")


def test_distinct_action_key_conflict_rejected(conn):
    """R108-1：同 run 同 step_type 不同 action key 入队 -> 显式拒绝（不合并/不返回其他动作）。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    # 第二动作不同 slot -> 不同 key -> 冲突拒绝
    run_pub = str(conn.execute(sqltext(
        "SELECT public_id FROM app.workflow_runs WHERE id=:r"), {"r": run_id}).scalar())
    other_key = compute_step_action_key(tpub, run_pub, "listing_submit", "other-slot", None)
    assert other_key != action_key
    with pytest.raises(WorkflowQueueError, match="拒绝合并"):
        q.enqueue_step(tenant_id=tid, run_id=run_id, step_type="listing_submit",
                       action_idempotency_key=other_key)
    # 原行不变（仍只有第一个动作）
    assert conn.execute(sqltext(
        "SELECT count(*) FROM app.workflow_steps WHERE run_id=:r"), {"r": run_id}).scalar() == 1
    # 同 key 重放仍幂等返回原 id
    step_id2 = q.enqueue_step(tenant_id=tid, run_id=run_id, step_type="listing_submit",
                              action_idempotency_key=action_key)
    assert step_id2 == step_id


# ---------------------------------------------------------------------------
# R108-2：handle_error 返回实际持久化状态（预算耗尽 -> failed）
# ---------------------------------------------------------------------------
def test_handle_error_returns_persisted_state_exhausted(conn):
    """R108-2：NO_MATCH 第二次 handle_error 预算耗尽返回 failed（与实际持久化一致）。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, a1 = q.claim(run_id=run_id)
    assert q.handle_error(step_id=got_id, attempt=a1, error_code="NO_MATCH") == "gate_retry"
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET gate_result = "
        "jsonb_set(COALESCE(gate_result,'{}'), '{retry_at}', "
        "to_jsonb('2000-01-01T00:00:00Z'::text)) WHERE id=:i"), {"i": got_id})
    got_id2, a2 = q.claim(run_id=run_id)
    assert a2 == 2
    result = q.handle_error(step_id=got_id2, attempt=a2, error_code="NO_MATCH")
    assert result == "failed"  # 返回实际持久化状态
    st = conn.execute(sqltext(
        "SELECT status FROM app.workflow_steps WHERE id=:i"), {"i": got_id}).first()
    assert st[0] == "failed"


@pytest.mark.parametrize("code,maxa", [
    ("RATE_LIMIT", 3), ("TIMEOUT", 3), ("UNEXPECTED", 3),
    ("INSUFFICIENT_REFERENCES", 2), ("NO_MATCH", 2),
])
def test_handle_error_five_retryable_codes(conn, code, maxa):
    """R108-2/T9/R112-5：五类 retryable 码完整预算逐轮执行——fixture 用独立提交连接建立
    （新连接可读），每轮**独立连接读取**持久化状态，返回值与 DB 一致；有界循环防死循环。"""
    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    tid = tpub = None
    try:
        # 独立提交连接建 fixture（R112-5：新连接读取的前提）
        with eng.begin() as c:
            tid, tpub = _new_tenant(c)
            q = WorkflowQueue(c)
            run_id, _ = q.ensure_run(
                tenant_id=tid, tenant_public_id=tpub, run_type="listing_flow",
                idempotency_key=compute_run_key(tpub, "manual", str(uuid.uuid4()), "w1", "p1"),
                trigger_type="manual", trigger_public_id=str(uuid.uuid4()),
                schedule_window="w1", policy_version_id="p1")
            run_pub = str(c.execute(sqltext(
                "SELECT public_id FROM app.workflow_runs WHERE id=:r"), {"r": run_id}).scalar())
            action_key = compute_step_action_key(tpub, run_pub, "listing_submit", "submit", None)
            got_id = q.enqueue_step(tenant_id=tid, run_id=run_id, step_type="listing_submit",
                                    action_idempotency_key=action_key)
        # claim 与 handle_error：每轮用独立事务连接（R112-5：逐轮提交 + 独立连接读取）
        seen = []
        for _ in range(maxa + 1):  # 有界：至多 maxa 次执行
            with eng.begin() as c1:
                q = WorkflowQueue(c1)
                token = q.claim(run_id=run_id)
                assert token is not None, f"应可领取: {seen}"
                got_id, attempt = token
                result = q.handle_error(step_id=got_id, attempt=attempt, error_code=code)
            # 事务已提交（eng.begin 自动 commit）
            with eng.connect() as c2:
                row = c2.execute(sqltext(
                    "SELECT status, attempt FROM app.workflow_steps WHERE id=:i"),
                    {"i": got_id}).first()
            assert row is not None, "step 行必须存在"
            seen.append((attempt, result, row[0]))
            assert result == row[0], f"返回值与持久化不一致: {seen}"
            if row[0] == "gate_retry":
                # R106-1：gate_retry 恰增 1（提交后新连接读 attempt=原+1）
                assert row[1] == attempt + 1, f"gate_retry 应恰增 1: {seen}"
            else:
                assert row[1] == attempt, f"failed 后 attempt 不变: {seen}"
            if row[0] == "failed":
                break
            # 预算内：模拟 backoff 到期（retry_at 置过去）
            with eng.begin() as c2:
                c2.execute(sqltext(
                    "UPDATE app.workflow_steps SET gate_result = "
                    "jsonb_set(COALESCE(gate_result,'{}'), '{retry_at}', "
                    "to_jsonb('2000-01-01T00:00:00Z'::text)) WHERE id=:i"), {"i": got_id})
        else:
            raise AssertionError(f"预算未耗尽（死循环防护）: {seen}")
        # 完整预算断言：恰 maxa 次执行（首轮 + maxa-1 次重试），最终 failed
        assert [s for _, _, s in seen].count("gate_retry") == maxa - 1
        assert seen[-1][2] == "failed"
        assert len(seen) == maxa
        with eng.connect() as c:
            assert c.execute(sqltext(
                "SELECT count(*) FROM app.workflow_steps WHERE run_id=:r"),
                {"r": run_id}).scalar() == 1
    finally:
        with eng.begin() as c:
            c.execute(sqltext("DELETE FROM app.workflow_steps WHERE run_id IN "
                              "(SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
        eng.dispose()


# ---------------------------------------------------------------------------
# R108-3：取消与 recover 并发——父 run 行锁协议
# ---------------------------------------------------------------------------
def test_cancel_wins_recover_race(conn):
    """R108-3：取消先提交后 recover 不回收（父行锁后按当前状态决定）。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET updated_at = now() - interval '46 minutes' "
        "WHERE id=:i"), {"i": got_id})
    q.set_run_status(run_id=run_id, status="cancelled")
    assert q.recover_stale_attempts() == 0  # cancelled 父 run 不回收
    st = conn.execute(sqltext(
        "SELECT status, attempt FROM app.workflow_steps WHERE id=:i"), {"i": got_id}).first()
    assert st[0] == "running"  # 原状态不变（不回收不递增）


def test_recover_wins_race_then_running(conn):
    """R108-3：回收先于取消——running 时回收生效（pending + attempt+1），后续取消仍持久化。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET updated_at = now() - interval '46 minutes' "
        "WHERE id=:i"), {"i": got_id})
    assert q.recover_stale_attempts() == 1  # 先回收（父 run 仍 running）
    q.set_run_status(run_id=run_id, status="cancelled")
    st = conn.execute(sqltext(
        "SELECT status, attempt FROM app.workflow_steps WHERE id=:i"), {"i": got_id}).first()
    assert st[0] == "pending" and st[1] == attempt + 1  # 回收已生效
    assert q.claim(run_id=run_id) is None  # cancelled 父 run 不可再领


@pytest.mark.parametrize("run_status", ["paused", "waiting_manual", "done", "failed"])
def test_recover_gate_matrix(conn, run_status):
    """R108-3：paused/waiting_manual/done/failed 父 run 均不回收过期 step。"""
    from sqlalchemy import text as sqltext

    q, tid, tpub, run_id, step_id, action_key = _setup(conn)
    got_id, attempt = q.claim(run_id=run_id)
    conn.execute(sqltext(
        "UPDATE app.workflow_steps SET updated_at = now() - interval '46 minutes' "
        "WHERE id=:i"), {"i": got_id})
    q.set_run_status(run_id=run_id, status=run_status)
    assert q.recover_stale_attempts() == 0


# ---------------------------------------------------------------------------
# R112-5：真实锁竞争（round-110 探针两种锁序迁入常规测试）
# ---------------------------------------------------------------------------
def test_real_lock_order_cancel_first(conn):
    """R112-5：真实锁竞争——取消先赢：B 的 recover 等待父行锁，A 提交 cancelled 后 B 跳过。"""
    import threading
    import time

    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    tid = tpub = None
    try:
        with eng.begin() as c:
            tid, tpub = _new_tenant(c)
            q = WorkflowQueue(c)
            run_id, _ = q.ensure_run(
                tenant_id=tid, tenant_public_id=tpub, run_type="listing_flow",
                idempotency_key=compute_run_key(tpub, "manual", str(uuid.uuid4()), "w1", "p1"),
                trigger_type="manual", trigger_public_id=str(uuid.uuid4()),
                schedule_window="w1", policy_version_id="p1")
            run_pub = str(c.execute(sqltext(
                "SELECT public_id FROM app.workflow_runs WHERE id=:r"), {"r": run_id}).scalar())
            action_key = compute_step_action_key(tpub, run_pub, "listing_submit", "submit", None)
            got_id = q.enqueue_step(tenant_id=tid, run_id=run_id, step_type="listing_submit",
                                    action_idempotency_key=action_key)
        # claim + 置旧（独立提交）
        with eng.begin() as c:
            q = WorkflowQueue(c)
            token = q.claim(run_id=run_id)
            assert token[0] == got_id
            c.execute(sqltext(
                "UPDATE app.workflow_steps SET updated_at = now() - interval '46 minutes' "
                "WHERE id=:i"), {"i": got_id})
        # 连接 A：锁父 run 行（模拟 set_run_status 持锁）
        holder = eng.connect()
        hold_tx = holder.begin()
        holder.execute(sqltext(
            "SELECT status FROM app.workflow_runs WHERE id=:r FOR UPDATE"), {"r": run_id})
        started = threading.Event()
        result = {}

        def recover_worker():
            with eng.connect() as c:
                c.execute(sqltext("SET LOCAL statement_timeout='10s'"))
                started.set()
                try:
                    result["recovered"] = WorkflowQueue(c).recover_stale_attempts()
                except Exception as exc:  # noqa: BLE001
                    result["error"] = type(exc).__name__

        worker = threading.Thread(target=recover_worker)
        try:
            worker.start()
            assert started.wait(5)
            # 等 B 到达父行锁（pg_blocking_pids 非空）
            blocked = False
            for _ in range(50):
                with eng.connect() as c:
                    pid = c.execute(sqltext("SELECT pg_backend_pid()")).scalar()
                    blk = c.execute(sqltext(
                        "SELECT count(*) FROM pg_stat_activity WHERE "
                        "pg_blocking_pids(pid) <> '{}'")).scalar()
                    if blk:
                        blocked = True
                        break
                time.sleep(0.05)
            assert blocked, "recover 未到达父行锁"
            # A 提交 cancelled
            WorkflowQueue(holder).set_run_status(run_id=run_id, status="cancelled")
            hold_tx.commit()
            worker.join(12)
            assert not worker.is_alive()
            # 取消先赢：recover 读到 cancelled 跳过
            assert result.get("recovered") == 0
            with eng.connect() as c:
                row = c.execute(sqltext(
                    "SELECT r.status, s.status, s.attempt FROM app.workflow_runs r "
                    "JOIN app.workflow_steps s ON s.run_id=r.id WHERE s.id=:i"),
                    {"i": got_id}).first()
            assert row == ("cancelled", "running", 1)  # step 未被回收
        finally:
            if hold_tx.is_active:
                hold_tx.rollback()
            holder.close()
            worker.join(12)
    finally:
        with eng.begin() as c:
            c.execute(sqltext("DELETE FROM app.workflow_steps WHERE run_id IN "
                              "(SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
        eng.dispose()


def test_real_lock_order_recover_first(conn):
    """R114-4：真实 recover-first 锁竞争（round-110 探针迁入）：
    holder 锁 step -> recover 线程持父锁并等待 step -> cancel 线程等待父锁 ->
    释放 holder 后按序提交（recover 先于 cancel），终态 pending+attempt=2 + cancelled。
    全程绑定参与者 PID 精确阻塞证据（pg_blocking_pids 含 holder/recover PID）。"""
    import threading
    import time

    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    tid = tpub = None
    holder = None
    try:
        with eng.begin() as c:
            tid, tpub = _new_tenant(c)
            q = WorkflowQueue(c)
            run_id, _ = q.ensure_run(
                tenant_id=tid, tenant_public_id=tpub, run_type="listing_flow",
                idempotency_key=compute_run_key(tpub, "manual", str(uuid.uuid4()), "w1", "p1"),
                trigger_type="manual", trigger_public_id=str(uuid.uuid4()),
                schedule_window="w1", policy_version_id="p1")
            run_pub = str(c.execute(sqltext(
                "SELECT public_id FROM app.workflow_runs WHERE id=:r"), {"r": run_id}).scalar())
            action_key = compute_step_action_key(tpub, run_pub, "listing_submit", "submit", None)
            got_id = q.enqueue_step(tenant_id=tid, run_id=run_id, step_type="listing_submit",
                                    action_idempotency_key=action_key)
        with eng.begin() as c:
            q = WorkflowQueue(c)
            token = q.claim(run_id=run_id)
            assert token[0] == got_id
            c.execute(sqltext(
                "UPDATE app.workflow_steps SET updated_at = now() - interval '46 minutes' "
                "WHERE id=:i"), {"i": got_id})
        # holder：锁 step 行（46min 过期 running step）
        holder = eng.connect()
        holder_tx = holder.begin()
        holder.execute(sqltext(
            "SELECT id FROM app.workflow_steps WHERE id=:i FOR UPDATE"), {"i": got_id})
        holder_pid = holder.execute(sqltext("SELECT pg_backend_pid()")).scalar()
        # recover 线程：锁父 run 后等待 step 锁
        recover_started = threading.Event()
        recover_result = {}
        recover_pid = {}

        def recover_worker():
            with eng.connect() as c:
                c.execute(sqltext("SET LOCAL statement_timeout='15s'"))
                recover_pid["pid"] = c.execute(sqltext("SELECT pg_backend_pid()")).scalar()
                recover_started.set()
                try:
                    recover_result["n"] = WorkflowQueue(c).recover_stale_attempts()
                    c.commit()  # 显式提交（eng.connect 隐式事务默认回滚）
                except Exception as exc:  # noqa: BLE001
                    recover_result["err"] = type(exc).__name__
                    c.rollback()

        rw = threading.Thread(target=recover_worker)
        rw.start()
        assert recover_started.wait(5)
        # cancel 线程：等待父 run 锁（recover 持有）
        cancel_done = threading.Event()
        cancel_state = {}
        cancel_pid = {}

        def cancel_worker():
            try:
                with eng.connect() as c:
                    cancel_pid["pid"] = c.execute(sqltext("SELECT pg_backend_pid()")).scalar()
                    WorkflowQueue(c).set_run_status(run_id=run_id, status="cancelled")
                    c.commit()  # 显式提交
                cancel_state["ok"] = True
            except Exception as exc:  # noqa: BLE001
                cancel_state["err"] = type(exc).__name__
                cancel_state["detail"] = str(exc)[:200]
            finally:
                cancel_done.set()

        cw = threading.Thread(target=cancel_worker)
        cw.start()
        # 验证 cancel 被 recover 的父行锁阻塞（PID 精确证据：cancel 的 blocking 含 recover PID）
        blocked_cancel = False
        for _ in range(150):
            if not cancel_pid.get("pid"):
                time.sleep(0.05)
                continue
            with eng.connect() as c:
                row = c.execute(sqltext(
                    "SELECT pid, pg_blocking_pids(pid) FROM pg_stat_activity WHERE pid=:p"),
                    {"p": cancel_pid["pid"]}).first()
                if row and row[1] and recover_pid.get("pid") in row[1]:
                    blocked_cancel = True
                    break
            time.sleep(0.05)
        assert blocked_cancel, "cancel 必须被 recover 阻塞（PID 精确证据）"
        # 释放 holder -> recover 先完成（父 run 仍 running）-> cancel 后完成
        holder_tx.commit()
        holder.close()
        holder = None
        rw.join(15)
        assert not rw.is_alive()
        assert recover_result.get("n") == 1  # recover 先赢
        cancel_done.wait(15)
        assert cancel_state.get("ok") is True  # cancel 后完成
        cw.join(15)
        with eng.connect() as c:
            row = c.execute(sqltext(
                "SELECT r.status, s.status, s.attempt FROM app.workflow_runs r "
                "JOIN app.workflow_steps s ON s.run_id=r.id WHERE s.id=:i"),
                {"i": got_id}).first()
        assert row == ("cancelled", "pending", 2)  # 回收先赢：pending + attempt=2
    finally:
        if holder is not None and holder_tx.is_active:
            holder_tx.rollback()
            holder.close()
        with eng.begin() as c:
            c.execute(sqltext("DELETE FROM app.workflow_steps WHERE run_id IN "
                              "(SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
        eng.dispose()


# ---------------------------------------------------------------------------
# R114-4：ensure_run worker 故障清理（错误/超时后 fixture 归零）
# ---------------------------------------------------------------------------
def _run_worker_fault(eng, tid, tpub, shared_key, fault="worker-error"):
    """R122-2 全生命周期负例探针：worker 真实写入 -> finally 三表清理 -> 独立连接零残留断言。

    与正向测试共用同一探针入口（负例同源）。worker 线程内完成：
      1. 真实并发入口 ensure_run 执行并提交（worker-error 模式写入 run/step fixture；
         seed-failure 模式 ensure_run 抛错，seed 错误传播并被捕获入 worker_error）；
      2. finally 三表清理（workflow_steps / workflow_runs / tenants 按 tenant_id 精确 DELETE）；
      3. 线程后独立连接零残留断言（run=0 且 tenant=0），失败即抛 AssertionError。

    返回 (worker_error 列表, cleanup ok 布尔)。负例 meta test 在调用前植入
    Connection.execute 补丁包裹真实清理，使目标 tenant DELETE 恰好命中 1 次且
    不再生效，触发零残留断言失败（pytest.raises 验证）。"""
    import threading

    from sqlalchemy import create_engine, text as sqltext

    worker_error = []
    cleanup_error = []

    def worker():
        with eng.connect() as c:
            tx = c.begin()
            try:
                q = WorkflowQueue(c)
                if fault == "seed-failure":
                    from unittest import mock
                    with mock.patch.object(WorkflowQueue, "ensure_run",
                                           side_effect=RuntimeError("seed-failed")):
                        q.ensure_run(
                            tenant_id=tid, tenant_public_id=tpub, run_type="listing_flow",
                            idempotency_key=shared_key, trigger_type="manual",
                            trigger_public_id=str(uuid.uuid4()), schedule_window="w1",
                            policy_version_id="p1")
                    tx.rollback()  # seed 失败：回滚空事务
                else:
                    # 实际并发入口：ensure_run 真实执行并提交（先写入 fixture）
                    run_id, created = q.ensure_run(
                        tenant_id=tid, tenant_public_id=tpub, run_type="listing_flow",
                        idempotency_key=shared_key, trigger_type="manual",
                        trigger_public_id=str(uuid.uuid4()), schedule_window="w1",
                        policy_version_id="p1")
                    assert created
                    tx.commit()
                    # 确认 fixture 已写入（run 行存在于独立连接）
                    with eng.connect() as c2:
                        assert c2.execute(sqltext(
                            "SELECT count(*) FROM app.workflow_runs WHERE tenant_id=:t"),
                            {"t": tid}).scalar() == 1
                raise RuntimeError("worker-fault")
            except RuntimeError as exc:
                worker_error.append(str(exc))
            finally:
                # R122-2：清理必须在 worker 内 finally 执行（真实入口后置清理），
                # 供负例补丁精确包裹目标 tenant DELETE。
                try:
                    with eng.begin() as cc:
                        cc.execute(sqltext(
                            "DELETE FROM app.workflow_steps WHERE run_id IN "
                            "(SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"), {"t": tid})
                        cc.execute(sqltext(
                            "DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
                        cc.execute(sqltext(
                            "DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
                except Exception as exc:  # noqa: BLE001
                    cleanup_error.append(f"{type(exc).__name__}: {exc}")

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=15)
    assert not t.is_alive(), "worker 线程应结束"
    # 独立连接零残留断言（清理后新连接；R122-2：清理被跳过必须使正向入口失败）
    with create_engine(DB_URL).connect() as c:
        nr = c.execute(sqltext(
            "SELECT count(*) FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid}).scalar()
        nt = c.execute(sqltext(
            "SELECT count(*) FROM app.tenants WHERE id=:t"), {"t": tid}).scalar()
        assert nr == 0 and nt == 0, \
            f"worker 故障后应零残留: run={nr} tenant={nt} cleanup_errors={cleanup_error}"
    return worker_error, not cleanup_error


def test_ensure_run_worker_fault_cleans_fixture(conn):
    """R116-4/R120-3/R122-2：ensure_run worker 抛错后 finally 精确清理 tenant/run/step，
    独立连接断言全零。与负例共用 _run_worker_fault 全生命周期探针。"""
    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    tid = tpub = None
    try:
        with eng.begin() as c:
            tid, tpub = _new_tenant(c)
        shared_key = compute_run_key(tpub, "manual", str(uuid.uuid4()), "w1", "p1")
        worker_error, cleanup_ok = _run_worker_fault(eng, tid, tpub, shared_key)
        assert worker_error == ["worker-fault"], f"worker 错误应捕获: {worker_error}"
        assert cleanup_ok, "finally 清理应无异常"
    finally:
        with eng.begin() as c:
            c.execute(sqltext("DELETE FROM app.workflow_steps WHERE run_id IN "
                              "(SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
        eng.dispose()
    # 独立连接断言 tenant/run/step 全零（R116-4：清理后新连接）
    with create_engine(DB_URL).connect() as c:
        assert c.execute(sqltext(
            "SELECT count(*) FROM app.tenants WHERE id=:t"), {"t": tid}).scalar() == 0
        assert c.execute(sqltext(
            "SELECT count(*) FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid}).scalar() == 0
        assert c.execute(sqltext(
            "SELECT count(*) FROM app.workflow_steps WHERE run_id IN "
            "(SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"),
            {"t": tid}).scalar() == 0


def test_ensure_run_worker_fault_cleanup_failure_fails(conn):
    """R122-2：清理被跳过必须使**实际正向入口**失败（meta test 用 pytest.raises 验证）。

    与正向共用 _run_worker_fault；补丁在调用前植入，且仅包裹**目标 tenant DELETE**——
    真实清理执行时 DELETE FROM app.tenants WHERE id=:t 恰好命中 1 次并 no-op，
    run/step 清理照常，故零残留断言因 tenant 残留而抛 AssertionError（pytest.raises 捕获）。"""
    from unittest import mock

    from sqlalchemy import create_engine, text as sqltext
    from sqlalchemy.engine import Connection

    eng = create_engine(DB_URL)
    tid = tpub = None
    try:
        with eng.begin() as c:
            tid, tpub = _new_tenant(c)
        shared_key = compute_run_key(tpub, "manual", str(uuid.uuid4()), "w1", "p1")
        # 补丁在**调用探针前**植入——包裹真实 worker 内 finally 的目标 tenant DELETE
        real_execute = Connection.execute
        target_delete_calls = {"n": 0}

        def poisoned_delete(self, statement, params=None):
            if str(statement).startswith("DELETE FROM app.tenants") and params and params.get("t") == tid:
                target_delete_calls["n"] += 1
                return None  # 跳过目标 tenant DELETE → 清理失败 → 零残留断言失败
            return real_execute(self, statement, params or {})

        with mock.patch.object(Connection, "execute", poisoned_delete):
            with pytest.raises(AssertionError):
                _run_worker_fault(eng, tid, tpub, shared_key)
        # 补丁必须真实命中目标 tenant DELETE 恰好 1 次（包裹真实清理，而非仅 SELECT）
        assert target_delete_calls["n"] == 1, \
            f"目标 tenant DELETE 应被包裹命中 1 次, got {target_delete_calls['n']}"
    finally:
        # 外层 finally 清理自有残留（负例因清理跳过残留了 tenant）
        with eng.begin() as c:
            c.execute(sqltext("DELETE FROM app.workflow_steps WHERE run_id IN "
                              "(SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
        eng.dispose()
    with create_engine(DB_URL).connect() as c:
        assert c.execute(sqltext(
            "SELECT count(*) FROM app.tenants WHERE id=:t"), {"t": tid}).scalar() == 0


def test_ensure_run_worker_seed_failure_propagates(conn):
    """R120-3：seed（ensure_run）失败必须使正向入口失败（共享生命周期 seed-failure 模式）。"""
    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    tid = tpub = None
    try:
        with eng.begin() as c:
            tid, tpub = _new_tenant(c)
        shared_key = compute_run_key(tpub, "manual", str(uuid.uuid4()), "w1", "p1")
        worker_error, cleanup_ok = _run_worker_fault(eng, tid, tpub, shared_key, fault="seed-failure")
        assert worker_error == ["seed-failed"], f"seed 失败应传播: {worker_error}"
        assert cleanup_ok, "seed 失败路径 finally 清理应无异常"
    finally:
        with eng.begin() as c:
            c.execute(sqltext("DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
            c.execute(sqltext("DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
        eng.dispose()
    with create_engine(DB_URL).connect() as c:
        assert c.execute(sqltext(
            "SELECT count(*) FROM app.tenants WHERE id=:t"), {"t": tid}).scalar() == 0
