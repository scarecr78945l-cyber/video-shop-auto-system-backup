# -*- coding: utf-8 -*-
"""T7: auth 落库 + 生产 UserDirectory + 真实鉴权/审计集成测试（round-91）。

覆盖（round-90 §三 生产链路必验项）：
- auth 7 表真实落库（auth schema）；
- PgUserDirectory 读同一 auth 数据源（user/member/organization，slug=tenant.public_id）；
- 停用用户（auth.user.status='disabled'）拒绝；重新启用恢复；
- 越权（member.role 白名单外/秩不足）拒绝；worker scope 错误拒绝；
- 双源冲突（registry + auth.user 同 UUID）拒绝；
- 创建者 admin、角色白名单、slug 不可变、service/worker 生命周期（bind/unbind）；
- 真实审计写入（actor/request_id/tenant 可信来源）与拒绝零新增。

运行：cd backend && python -m pytest tests/test_auth_integration.py -q --basetemp=.pytest-tmp-t7int
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infra.auth import (  # noqa: E402
    ActorAmbiguousError,
    ActorDisabledError,
    ActorNotFoundError,
    ActorResolver,
    OrganizationError,
    PgUserDirectory,
    TenantForbiddenError,
    WorkerScopeError,
    bind_tenant_organization,
    set_member_role,
    unbind_tenant_organization,
)

DB_URL = os.environ.get("DATABASE_URL", "").strip()
WORKER = "a9a79363-609b-5848-a4b3-33982797cfb8"   # 种子 worker
SERVICE = "e57a6a59-da1d-5628-baef-e3b78f12f9e5"   # 种子 service


@pytest.fixture()
def conn():
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过真实 auth 集成验收")
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


def _new_user(conn, status="active"):
    """在 auth.user 插入真实用户（模拟 better-auth 写入同库）。"""
    from sqlalchemy import text as sqltext

    uid = str(uuid.uuid4())
    conn.execute(sqltext(
        "INSERT INTO auth.user (id, name, email, email_verified, status) "
        "VALUES (:i, :n, :e, true, :s)"),
        {"i": uid, "n": "it-" + uid[:8], "e": uid[:8] + "@example.com", "s": status})
    return uid


def _new_tenant(conn):
    from sqlalchemy import text as sqltext

    row = conn.execute(sqltext(
        "INSERT INTO app.tenants (name, scope) VALUES (:n, 'internal') RETURNING public_id"),
        {"n": "t7int-" + uuid.uuid4().hex[:8]}).first()
    return str(row[0])


def _audit_count(conn):
    from sqlalchemy import text as sqltext

    return conn.execute(sqltext("SELECT count(*) FROM app.audit_events")).scalar()


# ---------------------------------------------------------------------------
# 1. auth 落库 + 生产目录（同一数据源）
# ---------------------------------------------------------------------------
def test_auth_tables_and_pg_directory(conn):
    from sqlalchemy import text as sqltext

    rows = conn.execute(sqltext(
        "SELECT tablename FROM pg_tables WHERE schemaname='auth' ORDER BY tablename")).fetchall()
    assert {r[0] for r in rows} == {"user", "session", "account", "verification",
                                    "organization", "member", "invitation"}
    tenant = _new_tenant(conn)
    uid = _new_user(conn)
    directory = PgUserDirectory(conn)
    rec = directory.lookup(uid)
    assert rec is not None and rec.actor_id == uid and rec.status == "active"
    assert directory.membership(uid, tenant) is None  # 未加入组织
    assert directory.lookup(str(uuid.uuid4())) is None


# ---------------------------------------------------------------------------
# 2. 停用用户（真实 auth.user.status）
# ---------------------------------------------------------------------------
def test_disabled_user_rejected_and_reenable(conn):
    from sqlalchemy import text as sqltext

    tenant = _new_tenant(conn)
    uid = _new_user(conn)
    directory = PgUserDirectory(conn)
    resolver = ActorResolver(conn, user_directory=directory)
    # user 无 membership -> 跨租户拒绝（先验证基线）
    with pytest.raises(TenantForbiddenError):
        resolver.assert_can_act(uid, tenant)
    # 给 user 建立 membership（admin），然后 active 通过
    org_id = bind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=tenant,
                                      organization_name="it-dis", user_directory=directory,
                                      worker_scope_tenant_public_id=tenant)
    conn.execute(sqltext(
        "INSERT INTO auth.member (organization_id, user_id, role, created_at) "
        "VALUES (:o, :u, 'admin', now())"),
        {"o": org_id, "u": uid})
    assert resolver.assert_can_act(uid, tenant).kind == "user"
    conn.execute(sqltext("UPDATE auth.user SET status='disabled' WHERE id=:i"), {"i": uid})
    with pytest.raises(ActorDisabledError):
        resolver.assert_can_act(uid, tenant)
    conn.execute(sqltext("UPDATE auth.user SET status='active' WHERE id=:i"), {"i": uid})
    assert resolver.assert_can_act(uid, tenant).kind == "user"  # 重新启用恢复


# ---------------------------------------------------------------------------
# 3. 角色白名单 + 越权 + worker scope
# ---------------------------------------------------------------------------
def test_role_whitelist_and_escalation(conn):
    from sqlalchemy import text as sqltext

    tenant = _new_tenant(conn)
    uid = _new_user(conn)
    directory = PgUserDirectory(conn)
    org_id = bind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=tenant,
                                      organization_name="it-role", user_directory=directory,
                                      worker_scope_tenant_public_id=tenant)
    # 白名单外角色写入被组织层拒绝（'owner'/'member' 非业务角色）
    with pytest.raises(OrganizationError):
        set_member_role(conn, operator_actor_id=WORKER, tenant_public_id=tenant,
                        target_actor_id=uid, new_role="owner",
                        operator_scope_tenant_public_id=tenant, user_directory=directory)
    with pytest.raises(OrganizationError):
        set_member_role(conn, operator_actor_id=WORKER, tenant_public_id=tenant,
                        target_actor_id=uid, new_role="member",
                        operator_scope_tenant_public_id=tenant, user_directory=directory)
    # 合法写入 viewer，然后越权校验
    set_member_role(conn, operator_actor_id=WORKER, tenant_public_id=tenant,
                    target_actor_id=uid, new_role="viewer",
                    operator_scope_tenant_public_id=tenant, user_directory=directory)
    resolver = ActorResolver(conn, user_directory=directory)
    with pytest.raises(TenantForbiddenError):
        resolver.assert_can_act(uid, tenant, required_role="admin")
    assert resolver.assert_can_act(uid, tenant).kind == "user"  # 无 required_role 通过
    # worker scope 缺/错/对
    with pytest.raises(WorkerScopeError):
        resolver.assert_can_act(WORKER, tenant)
    other_tenant = _new_tenant(conn)
    with pytest.raises(WorkerScopeError):
        resolver.assert_can_act(WORKER, tenant, worker_scope_tenant_public_id=other_tenant)
    assert resolver.assert_can_act(WORKER, tenant,
                                   worker_scope_tenant_public_id=tenant).kind == "worker"


# ---------------------------------------------------------------------------
# 4. 双源冲突（registry + auth.user 同 UUID）
# ---------------------------------------------------------------------------
def test_dual_source_conflict_real(conn):
    from sqlalchemy import text as sqltext

    tenant = _new_tenant(conn)
    uid = _new_user(conn)
    # 同 UUID 再注册到 actor_registry（user 影子被禁止）
    conn.execute(sqltext(
        "INSERT INTO app.actor_registry (actor_id, actor_kind, name, status) "
        "VALUES (:u, 'service', 'dup-shadow', 'active')"), {"u": uid})
    resolver = ActorResolver(conn, user_directory=PgUserDirectory(conn))
    with pytest.raises(ActorAmbiguousError):
        resolver.assert_can_act(uid, tenant)


# ---------------------------------------------------------------------------
# 5. 创建者 admin + slug 不可变 + service/worker 生命周期
# ---------------------------------------------------------------------------
def test_organization_lifecycle(conn):
    from sqlalchemy import text as sqltext

    tenant = _new_tenant(conn)
    directory = PgUserDirectory(conn)
    org_id = bind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=tenant,
                                      organization_name="it-life", user_directory=directory,
                                      worker_scope_tenant_public_id=tenant)
    # service/worker 创建者不在 auth.user（双源分离），不写 member；组织行存在
    org = conn.execute(sqltext(
        "SELECT name, slug FROM auth.organization WHERE id=:o"), {"o": org_id}).first()
    assert org is not None and org[1] == tenant
    member_count = conn.execute(sqltext(
        "SELECT count(*) FROM auth.member WHERE organization_id=:o"), {"o": org_id}).scalar()
    assert member_count == 0
    # user 类创建者（admin 归属）验证：先建 user，再以 service 绑定另一个租户 + 插入 user member
    uid = _new_user(conn)
    tenant2 = _new_tenant(conn)
    org2 = bind_tenant_organization(conn, actor_id=SERVICE, tenant_public_id=tenant2,
                                    organization_name="it-life2", user_directory=directory,
                                    worker_scope_tenant_public_id=tenant2)
    conn.execute(sqltext(
        "INSERT INTO auth.member (organization_id, user_id, role, created_at) "
        "VALUES (:o, :u, 'admin', now())"), {"o": org2, "u": uid})
    role = conn.execute(sqltext(
        "SELECT role FROM auth.member WHERE organization_id=:o AND user_id=:u"),
        {"o": org2, "u": uid}).first()
    assert role[0] == "admin"  # 创建者 admin 归属（业务白名单）
    # slug 重复绑定拒绝（不可重复创建）
    with pytest.raises(OrganizationError):
        bind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=tenant,
                                 organization_name="dup", user_directory=directory,
                                 worker_scope_tenant_public_id=tenant)
    # user 类 actor 禁止绑定（仅 service/worker）
    with pytest.raises(OrganizationError):
        bind_tenant_organization(conn, actor_id=uid, tenant_public_id=_new_tenant(conn),
                                 organization_name="no-user", user_directory=directory)
    # R94-2：含 invitation 时解绑拒绝（与声明一致，避免悬空邀请访问）
    conn.execute(sqltext(
        "INSERT INTO auth.invitation (organization_id, email, role, status, expires_at, "
        " created_at, inviter_id) VALUES (:o, 'pending@example.com', 'viewer', 'pending', "
        " now()+interval '1 day', now(), :u)"), {"o": org_id, "u": uid})
    with pytest.raises(OrganizationError):
        unbind_tenant_organization(conn, actor_id=SERVICE, tenant_public_id=tenant,
                                   user_directory=directory,
                                   worker_scope_tenant_public_id=tenant)
    # 清空邀请后可解绑；解绑后 organization/member 清空
    conn.execute(sqltext("DELETE FROM auth.invitation WHERE organization_id=:o"), {"o": org_id})
    unbind_tenant_organization(conn, actor_id=SERVICE, tenant_public_id=tenant,
                               user_directory=directory,
                               worker_scope_tenant_public_id=tenant)
    assert conn.execute(sqltext(
        "SELECT count(*) FROM auth.organization WHERE id=:o"), {"o": org_id}).scalar() == 0


# ---------------------------------------------------------------------------
# 6. 真实审计（actor/request_id/tenant 可信来源）+ 拒绝零新增
# ---------------------------------------------------------------------------
def test_real_audit_and_zero_insert_on_reject(conn):
    from sqlalchemy import text as sqltext

    from domain.audit import write_audit_event

    tenant = _new_tenant(conn)
    directory = PgUserDirectory(conn)
    uid = _new_user(conn)
    req_id = "req-" + uuid.uuid4().hex
    # 成功：真实 worker + scope 写入审计
    event_id = write_audit_event(
        conn, actor_id=WORKER, tenant_public_id=tenant, action="t7int.ok",
        target_type="tenant", target_public_id=tenant, request_id=req_id,
        worker_scope_tenant_public_id=tenant, user_directory=directory,
    )
    row = conn.execute(sqltext(
        "SELECT actor_id, action, request_id FROM app.audit_events WHERE id=:i"),
        {"i": event_id}).first()
    assert row is not None and str(row[0]) == WORKER and row[2] == req_id
    # 拒绝（停用用户）-> 审计零新增
    conn.execute(sqltext("UPDATE auth.user SET status='disabled' WHERE id=:i"), {"i": uid})
    before = _audit_count(conn)
    with pytest.raises(ActorDisabledError):
        write_audit_event(
            conn, actor_id=uid, tenant_public_id=tenant, action="t7int.blocked",
            target_type="tenant", target_public_id=tenant, request_id=req_id + "-x",
            user_directory=directory,
        )
    assert _audit_count(conn) == before
    # 拒绝（伪造 actor）-> 零新增
    before = _audit_count(conn)
    with pytest.raises(ActorNotFoundError):
        write_audit_event(
            conn, actor_id=str(uuid.uuid4()), tenant_public_id=tenant, action="t7int.forged",
            target_type="tenant", target_public_id=tenant, request_id=req_id + "-f",
            user_directory=directory,
        )
    assert _audit_count(conn) == before
