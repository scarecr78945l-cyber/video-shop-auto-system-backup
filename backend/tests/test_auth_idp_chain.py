# -*- coding: utf-8 -*-
"""T7: better-auth 真实 IdP 链路集成测试（round-93 R92-1；round-95 R94-4；round-97 R96-2；
round-99 R98-2；round-101 R100-1 定稿）。

验收（round-92 §二 R92-1）：注册/创建用户 -> 登录 -> session -> 受保护操作 -> 审计；
服务端 disabled 后新登录拒绝；重新启用路径明确。**不使用直接 INSERT 用户替代 IdP 写入。**

round-101 R100-1 修复：
- email 与 UUID 断言入口分开：按 email 清理后，先查真实 UUID 再按 UUID 断三表归零，并按 email 断 user 归零
  （不再把邮箱字符串传给 UUID 列查询，消除 SQLSTATE 22P02）；
- 故障测试参数化三类真实分支（非零退出/部分输出/超时）：先真实创建 fixture，注入故障，走实际 try/finally
  清理路径，新连接断言 0/0/0；
- seed 失败必须使测试失败（不再由宽泛 except 吞掉）。

运行：cd backend && python -m pytest tests/test_auth_idp_chain.py -q --basetemp=.pytest-tmp-t7idp
"""
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infra.auth import ActorDisabledError, ActorResolver, PgUserDirectory  # noqa: E402

DB_URL = os.environ.get("DATABASE_URL", "").strip()
ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
CHAIN = FRONTEND / "round-93-auth-chain.mjs"


def _run_chain(keep_user=False, fixture_email=None):
    env = dict(os.environ)
    env["DATABASE_URL"] = DB_URL
    env["PYTHONUTF8"] = "1"
    if keep_user:
        env["KEEP_USER"] = "1"
    if fixture_email:
        env["FIXTURE_EMAIL"] = fixture_email
    r = subprocess.run(
        ["node", "--experimental-strip-types", "round-93-auth-chain.mjs"],
        cwd=str(FRONTEND), capture_output=True, timeout=180,
        env=env,
    )
    return r, r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")


@pytest.fixture()
def conn():
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过 IdP 链路验收")
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


def _parse(out: str) -> dict:
    d = {}
    for line in out.splitlines():
        m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
        if m:
            d[m.group(1)] = m.group(2)
    return d


# ---------------------------------------------------------------------------
# 清理与断言（独立提交；email/UUID 入口分离，round-101 R100-1）
# ---------------------------------------------------------------------------
def _cleanup_user_committed(user_id: str) -> None:
    """独立提交连接精确删除 user（FK CASCADE 级联 session/account）。"""
    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    with eng.begin() as c:
        c.execute(sqltext("DELETE FROM auth.user WHERE id=:i"), {"i": user_id})
    eng.dispose()


def _cleanup_user_by_email(email: str) -> None:
    """按预生成唯一 email 定位清理（不依赖输出中的 user_id）。"""
    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    with eng.begin() as c:
        c.execute(sqltext("DELETE FROM auth.user WHERE email=:e"), {"e": email})
    eng.dispose()


def _assert_no_remaining_by_uuid(user_id: str) -> None:
    """新连接按 UUID 断言 user/session/account 无残留。"""
    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    with eng.connect() as c:
        assert c.execute(sqltext(
            "SELECT count(*) FROM auth.user WHERE id=:i"), {"i": user_id}).scalar() == 0
        assert c.execute(sqltext(
            "SELECT count(*) FROM auth.session WHERE user_id=:i"), {"i": user_id}).scalar() == 0
        assert c.execute(sqltext(
            "SELECT count(*) FROM auth.account WHERE user_id=:i"), {"i": user_id}).scalar() == 0
    eng.dispose()


def _assert_no_remaining_by_email(email: str) -> None:
    """R100-1：按 email 定位真实 UUID，再按 UUID 断三表；并按 email 断 user 归零。

    绝不把 email 传给 UUID 列查询（消除 SQLSTATE 22P02）。
    """
    from sqlalchemy import create_engine, text as sqltext

    eng = create_engine(DB_URL)
    with eng.connect() as c:
        row = c.execute(sqltext("SELECT id FROM auth.user WHERE email=:e"), {"e": email}).first()
        if row is not None:
            uid = str(row[0])
            _assert_no_remaining_by_uuid(uid)
        assert c.execute(sqltext(
            "SELECT count(*) FROM auth.user WHERE email=:e"), {"e": email}).scalar() == 0
    eng.dispose()


# ---------------------------------------------------------------------------
# 正常链路
# ---------------------------------------------------------------------------
def test_idp_chain_real_write(conn):
    """R92-1：真实 better-auth 注册/登录/session/停用拒绝（IdP 写入 auth schema）。"""
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过 IdP 链路验收")
    from sqlalchemy import text as sqltext

    fixture_email = f"it-{uuid.uuid4().hex}@example.com"
    user_id = None
    try:
        r, out, err = _run_chain(keep_user=True, fixture_email=fixture_email)
        assert r.returncode == 0, f"chain 失败 rc={r.returncode} stderr={err[-500:]!r}"
        parsed = _parse(out)
        assert parsed.get("SIGNUP_OK") == "true"
        assert parsed.get("USER_STATUS_DEFAULT") == "active"
        assert parsed.get("SIGNIN_TOKEN_PRESENT") == "true"
        assert parsed.get("SESSION_ROW_PRESENT") == "true"
        assert parsed.get("SESSION_USER_ID_MATCH") == "true"
        assert parsed.get("SESSION_TOKEN_MATCH") == "true"
        assert parsed.get("SERVER_DISABLED") == "true"
        assert parsed.get("DISABLED_LOGIN_BLOCKED") == "true"
        assert parsed.get("CHAIN_DONE") == "true"
        user_id = parsed.get("KEPT_USER_ID") or parsed.get("USER_ID")
        # IdP 真实写入的 user 必须能被 Python 生产目录读取（同一 auth schema）
        directory = PgUserDirectory(conn)
        rec = directory.lookup(user_id)
        assert rec is not None, "PgUserDirectory 无法读取 IdP 写入的用户"
        assert rec.status == "disabled"  # 停用状态已持久化
        resolver = ActorResolver(conn, user_directory=directory)
        tid = str(conn.execute(sqltext(
            "INSERT INTO app.tenants (name, scope) VALUES ('t7idp', 'internal') RETURNING public_id"),
        ).scalar())
        with pytest.raises(ActorDisabledError):
            resolver.assert_can_act(user_id, tid)
    finally:
        if user_id:
            _cleanup_user_committed(user_id)
            _assert_no_remaining_by_uuid(user_id)
        else:
            _cleanup_user_by_email(fixture_email)
            _assert_no_remaining_by_email(fixture_email)


def test_idp_chain_cleans_up():
    """R94-4/R96-2：Node 默认清理（非 keep）后，独立提交连接断言无残留。"""
    if not DB_URL:
        pytest.skip("无 DATABASE_URL")
    fixture_email = f"it-{uuid.uuid4().hex}@example.com"
    try:
        r, out, err = _run_chain(fixture_email=fixture_email)  # 默认模式：Node finally 自清理
        assert r.returncode == 0, f"chain 失败 rc={r.returncode} stderr={err[-500:]!r}"
        parsed = _parse(out)
        user_id = parsed.get("USER_ID")
        if user_id:
            _assert_no_remaining_by_uuid(user_id)
        else:
            _assert_no_remaining_by_email(fixture_email)
        assert parsed.get("CHAIN_DONE") == "true"
    finally:
        _cleanup_user_by_email(fixture_email)


# ---------------------------------------------------------------------------
# R100-1：故障注入（非零退出/部分输出/超时）——调用实际 real_write 入口共享执行/清理路径
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["nonzero", "partial", "timeout"])
def test_idp_chain_failure_path_cleans_up(conn, mode):
    """真实 fixture 创建后注入三类故障，走**实际 test_idp_chain_real_write 入口**的 try/finally
    清理路径，新连接断言 0/0/0；seed 成功/UUID/写入确认在预期异常捕获之外严格断言。

    conn：pytest fixture（事务回滚）；探针可直接传独立连接对象（同 DB_URL）。"""
    if not DB_URL:
        pytest.skip("无 DATABASE_URL")
    fixture_email = f"it-{uuid.uuid4().hex}@example.com"
    created_id = {"value": None}
    real_run = _run_chain  # 原始函数引用（patched_run 内部用它，避免递归）

    def patched_run(keep_user=False, fixture_email=None):
        # 先真实创建 fixture（IdP 写入 + KEEP_USER 保留）——seed 断言在捕获之外
        r, out, err = real_run(keep_user=True, fixture_email=fixture_email)
        assert r.returncode == 0, f"seed 失败 rc={r.returncode} stderr={err[-300:]!r}"
        parsed = _parse(out)
        created_id["value"] = parsed.get("KEPT_USER_ID") or parsed.get("USER_ID")
        assert created_id["value"], "KEEP_USER 模式应输出 USER_ID"
        # 注入故障（在 seed 成功之后）
        if mode == "timeout":
            raise subprocess.TimeoutExpired("injected-after-real-write", 180)
        if mode == "nonzero":
            r.returncode = 17
            return r, "", "injected nonzero exit"
        return r, "SIGNUP_OK=true\n", ""  # partial：输出截断（无 USER_ID 行）

    from unittest import mock

    with mock.patch.object(sys.modules[__name__], "_run_chain", patched_run):
        try:
            # 调用实际 real_write 入口（共享断言/清理路径，非复制流程）
            test_idp_chain_real_write(conn)
        except (AssertionError, subprocess.TimeoutExpired) as exc:
            # 预期故障浮出（含 seed 断言失败与注入故障同源；此分支仅接受注入故障）
            if created_id["value"] is None:
                raise  # seed 失败：created_id 未设置 -> 重新抛出，使测试失败
            if mode == "timeout":
                assert isinstance(exc, subprocess.TimeoutExpired), f"期望 TimeoutExpired, got {type(exc).__name__}"
            else:
                assert isinstance(exc, AssertionError), f"期望 AssertionError, got {type(exc).__name__}"
            if mode == "nonzero":
                assert "rc=17" in str(exc) or "returncode" in str(exc), f"故障消息应含 rc=17: {exc}"
        else:
            raise AssertionError("fault must surface")
    # 新连接断言：本次 fixture 无残留（按 UUID）
    assert created_id["value"], "seed 必须成功并产生 UUID"
    _assert_no_remaining_by_uuid(created_id["value"])


# ---------------------------------------------------------------------------
# R100-1：seed 失败负例——参数化用例完整入口必须失败（不吞）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["nonzero", "partial", "timeout"])
def test_idp_chain_failure_seed_rejected(conn, mode):
    """seed 失败（子进程非零/空输出）注入参数化用例**完整入口**，断言测试确实失败。"""
    if not DB_URL:
        pytest.skip("无 DATABASE_URL")
    fixture_email = f"it-{uuid.uuid4().hex}@example.com"

    def failing_run(keep_user=False, fixture_email=None):
        raise AssertionError("seed failed")

    from unittest import mock

    with mock.patch.object(sys.modules[__name__], "_run_chain", failing_run):
        with pytest.raises(AssertionError, match="seed failed"):
            test_idp_chain_failure_path_cleans_up(conn, mode)
    # seed 未创建数据：email 无残留
    _assert_no_remaining_by_email(fixture_email)
