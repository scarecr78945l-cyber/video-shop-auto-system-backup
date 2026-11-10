# -*- coding: utf-8 -*-
"""T7: auth/audit 基座验收（round-81）。

覆盖 auth-boundary.md §八四类必过 + 四补项：
  1. 伪造 actor_id 被拒绝；
  2. 跨 tenant membership 被拒绝；
  3. 停用用户被拒绝；
  4. 后台 worker 带正确租户上下文可执行；
  5. 双命中 actor（registry+users 同 UUID）被拒绝；
  6. 未知 tenant_public_id 被拒绝；
  7. role 越权被拒绝；
  8. request_id 贯通断言。

真实能力边界（auth-boundary.md §二 gate + round-17 T7 门禁）：
- actor_registry / tenants / audit_events 为真实 app schema 表（T3 建表 + t7seed000001 种子）；
- better-auth users/tenant_members（auth schema）**gate 未过未建表**；user 类 actor 经受控
  UserDirectory fixture 验证应用层校验逻辑，本包不宣称真实 IdP 能力（「未确认」）。

运行：cd backend && python -m pytest tests/test_auth_actor.py tests/test_auth_audit.py -q --basetemp=.pytest-tmp-t7
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infra.auth import (  # noqa: E402
    ActorAmbiguousError,
    ActorDirectoryUnavailableError,
    ActorDisabledError,
    ActorNotFoundError,
    ActorResolver,
    TenantForbiddenError,
    TenantNotFoundError,
    UserDirectory,
    WorkerScopeError,
)
from infra.auth.actor import UserRecord  # noqa: E402

DB_URL = os.environ.get("DATABASE_URL", "").strip()


@pytest.fixture()
def conn():
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过真实 PG 验收")
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


@pytest.fixture()
def tenant(conn):
    from sqlalchemy import text as sqltext

    row = conn.execute(sqltext(
        "INSERT INTO app.tenants (public_id, name, scope) VALUES "
        "(gen_random_uuid(), 't7_auth', 'internal') RETURNING id, public_id")).first()
    return {"id": row[0], "public_id": str(row[1])}


class FakeUserDirectory(UserDirectory):
    """受控 user 目录 fixture（better-auth gate 前，未确认；仅验收应用层校验逻辑）。"""

    def __init__(self, users=None, memberships=None):
        self._users = users or {}
        self._memberships = memberships or {}

    def lookup(self, actor_id: str):
        return self._users.get(actor_id)

    def membership(self, actor_id: str, tenant_public_id: str):
        return self._memberships.get((actor_id, tenant_public_id))


def _uid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 四类必过
# ---------------------------------------------------------------------------
def test_forged_actor_rejected(conn, tenant):
    """1. 伪造 actor_id（registry 与 users 均不存在）-> ActorNotFoundError。"""
    r = ActorResolver(conn, user_directory=FakeUserDirectory())
    with pytest.raises(ActorNotFoundError):
        r.assert_can_act(_uid(), tenant["public_id"])


def test_cross_tenant_rejected(conn, tenant):
    """2. user 在 tenant A 有 membership，操作 tenant B -> 跨租户拒绝。"""
    from sqlalchemy import text as sqltext

    other = conn.execute(sqltext(
        "INSERT INTO app.tenants (public_id, name, scope) VALUES "
        "(gen_random_uuid(), 't7_b', 'internal') RETURNING public_id")).first()
    other_pub = str(other[0])
    actor = _uid()
    directory = FakeUserDirectory(
        users={actor: UserRecord(actor_id=actor, email="u@example.com", status="active")},
        memberships={(actor, tenant["public_id"]): "viewer"},
    )
    r = ActorResolver(conn, user_directory=directory)
    with pytest.raises(TenantForbiddenError):
        r.assert_can_act(actor, other_pub)


def test_disabled_actor_rejected(conn, tenant):
    """3. 停用用户（users status=disabled）-> ActorDisabledError。"""
    actor = _uid()
    directory = FakeUserDirectory(
        users={actor: UserRecord(actor_id=actor, email="off@example.com", status="disabled")},
        memberships={(actor, tenant["public_id"]): "viewer"},
    )
    r = ActorResolver(conn, user_directory=directory)
    with pytest.raises(ActorDisabledError):
        r.assert_can_act(actor, tenant["public_id"])


def test_worker_with_tenant_context_ok(conn, tenant):
    """4. 后台 worker（actor_registry 种子）带正确租户上下文与可信 scope 可执行。"""
    # 种子 worker：a9a79363-609b-5848-a4b3-33982797cfb8（t7seed000001）
    worker = "a9a79363-609b-5848-a4b3-33982797cfb8"
    r = ActorResolver(conn, user_directory=FakeUserDirectory())  # users 无此 worker
    rec = r.assert_can_act(worker, tenant["public_id"],
                           worker_scope_tenant_public_id=tenant["public_id"])
    assert rec.kind == "worker" and rec.source == "registry" and rec.status == "active"


def test_worker_missing_scope_rejected(conn, tenant):
    """R82-3：worker 缺可信 scope -> WorkerScopeError。"""
    worker = "a9a79363-609b-5848-a4b3-33982797cfb8"
    r = ActorResolver(conn, user_directory=FakeUserDirectory())
    with pytest.raises(WorkerScopeError):
        r.assert_can_act(worker, tenant["public_id"])


def test_worker_scope_mismatch_rejected(conn, tenant):
    """R82-3：worker scope=租户A 但操作租户B -> WorkerScopeError（scope 与 tenant exact equality）。"""
    from sqlalchemy import text as sqltext

    worker = "a9a79363-609b-5848-a4b3-33982797cfb8"
    other = conn.execute(sqltext(
        "INSERT INTO app.tenants (public_id, name, scope) VALUES "
        "(gen_random_uuid(), 't7_scope_b', 'internal') RETURNING public_id")).first()
    other_pub = str(other[0])
    r = ActorResolver(conn, user_directory=FakeUserDirectory())
    with pytest.raises(WorkerScopeError):
        r.assert_can_act(worker, tenant["public_id"],
                         worker_scope_tenant_public_id=other_pub)


# ---------------------------------------------------------------------------
# 四补项
# ---------------------------------------------------------------------------
def test_ambiguous_actor_rejected(conn, tenant):
    """5. registry+users 同 UUID 双命中 -> ActorAmbiguousError。"""
    # 种子 system：699f543a-2540-5127-913e-8cca0148db9b，同时注册为 user -> 双来源歧义
    system_id = "699f543a-2540-5127-913e-8cca0148db9b"
    directory = FakeUserDirectory(
        users={system_id: UserRecord(actor_id=system_id, email="dup@example.com", status="active")},
        memberships={(system_id, tenant["public_id"]): "admin"},
    )
    r = ActorResolver(conn, user_directory=directory)
    with pytest.raises(ActorAmbiguousError):
        r.assert_can_act(system_id, tenant["public_id"])


def test_unknown_tenant_rejected(conn):
    """6. 未知 tenant_public_id -> TenantNotFoundError。"""
    worker = "a9a79363-609b-5848-a4b3-33982797cfb8"
    r = ActorResolver(conn, user_directory=FakeUserDirectory())
    with pytest.raises(TenantNotFoundError):
        r.assert_can_act(worker, _uid(), worker_scope_tenant_public_id=_uid())


def test_role_escalation_rejected(conn, tenant):
    """7. user role=viewer 但 required_role=admin -> role 越权拒绝。"""
    actor = _uid()
    directory = FakeUserDirectory(
        users={actor: UserRecord(actor_id=actor, email="v@example.com", status="active")},
        memberships={(actor, tenant["public_id"]): "viewer"},
    )
    r = ActorResolver(conn, user_directory=directory)
    with pytest.raises(TenantForbiddenError):
        r.assert_can_act(actor, tenant["public_id"], required_role="admin")


def test_request_id_through(conn, tenant):
    """8. 审计写入带 request_id，贯通断言（写后读取同一行）。"""
    from sqlalchemy import text as sqltext

    from domain.audit import write_audit_event

    worker = "a9a79363-609b-5848-a4b3-33982797cfb8"
    req_id = "req-" + uuid.uuid4().hex
    event_id = write_audit_event(
        conn,
        actor_id=worker,
        tenant_public_id=tenant["public_id"],
        action="t7.probe",
        target_type="tenant",
        target_public_id=tenant["public_id"],
        request_id=req_id,
        before={"k": 1},
        after={"k": 2},
        evidence_ref="ev:t7",
        worker_scope_tenant_public_id=tenant["public_id"],  # R82-3：worker 可信 scope
        user_directory=FakeUserDirectory(),                 # R82-2：目录显式注入
    )
    assert event_id is not None
    row = conn.execute(sqltext(
        "SELECT actor_id, action, target_type, target_public_id, request_id, evidence_ref "
        "FROM app.audit_events WHERE id = :i"), {"i": event_id}).first()
    assert row is not None
    assert str(row[0]) == worker
    assert row[1] == "t7.probe"
    assert str(row[3]) == tenant["public_id"]
    assert row[4] == req_id  # request_id 贯通
    assert row[5] == "ev:t7"


def test_forged_actor_audit_rejected(conn, tenant):
    """四类在审计写入入口同样拒绝（伪造 actor 不落库）。"""
    from sqlalchemy import text as sqltext

    from domain.audit import write_audit_event

    from infra.auth import ActorNotFoundError as ANF

    before = conn.execute(sqltext("SELECT count(*) FROM app.audit_events")).scalar()
    with pytest.raises(ANF):
        write_audit_event(
            conn, actor_id=_uid(), tenant_public_id=tenant["public_id"],
            action="t7.forged", target_type="tenant", target_public_id=tenant["public_id"],
            user_directory=FakeUserDirectory(),
        )
    after = conn.execute(sqltext("SELECT count(*) FROM app.audit_events")).scalar()
    assert after == before  # 零新增


# ---------------------------------------------------------------------------
# R82-2：双源规范化 UUID 与目录门禁
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("variant", [
    "699f543a-2540-5127-913e-8cca0148db9b",                    # canonical
    "699F543A-2540-5127-913E-8CCA0148DB9B",                    # uppercase
    "699f543a25405127913e8cca0148db9b",                        # 无连字符
])
def test_dual_source_ambiguous_all_forms(conn, tenant, variant):
    """R82-2：canonical/uppercase/无连字符同值输入，双命中均抛 ActorAmbiguousError。"""
    system_id = "699f543a-2540-5127-913e-8cca0148db9b"
    directory = FakeUserDirectory(
        users={system_id: UserRecord(actor_id=system_id, email="dup@example.com", status="active")},
        memberships={(system_id, tenant["public_id"]): "admin"},
    )
    r = ActorResolver(conn, user_directory=directory)
    with pytest.raises(ActorAmbiguousError):
        r.assert_can_act(variant, tenant["public_id"])


def test_directory_missing_audit_zero_insert(conn, tenant):
    """R82-2：目录未配置（UserDirectory 缺失）-> fail closed，审计零新增。"""
    from sqlalchemy import text as sqltext

    from domain.audit import write_audit_event

    from infra.auth import ActorDirectoryUnavailableError as ADU

    worker = "a9a79363-609b-5848-a4b3-33982797cfb8"
    before = conn.execute(sqltext("SELECT count(*) FROM app.audit_events")).scalar()
    with pytest.raises(ADU):
        write_audit_event(
            conn, actor_id=worker, tenant_public_id=tenant["public_id"],
            action="t7.nodir", target_type="tenant", target_public_id=tenant["public_id"],
            worker_scope_tenant_public_id=tenant["public_id"],
            user_directory=None,  # 目录缺失（完整双源校验显式依赖目录）
        )
    after = conn.execute(sqltext("SELECT count(*) FROM app.audit_events")).scalar()
    assert after == before  # 零新增


# ---------------------------------------------------------------------------
# R82-3：角色值集门禁与 worker 可信 scope
# ---------------------------------------------------------------------------
def test_unknown_membership_role_rejected(conn, tenant):
    """R82-3：membership role 未知值（未传 required_role 也拒绝）。"""
    actor = _uid()
    directory = FakeUserDirectory(
        users={actor: UserRecord(actor_id=actor, email="x@example.com", status="active")},
        memberships={(actor, tenant["public_id"]): "unregistered-role"},
    )
    r = ActorResolver(conn, user_directory=directory)
    with pytest.raises(TenantForbiddenError):
        r.assert_can_act(actor, tenant["public_id"])


def test_empty_membership_role_rejected(conn, tenant):
    """R82-3：membership role 空串（无论是否传 required_role）拒绝。"""
    actor = _uid()
    directory = FakeUserDirectory(
        users={actor: UserRecord(actor_id=actor, email="e@example.com", status="active")},
        memberships={(actor, tenant["public_id"]): ""},
    )
    r = ActorResolver(conn, user_directory=directory)
    with pytest.raises(TenantForbiddenError):
        r.assert_can_act(actor, tenant["public_id"])


def test_worker_scope_ok_and_mismatch(conn, tenant):
    """R82-3：worker 正确 scope 通过；错误 scope 拒绝；缺 scope 拒绝。"""
    from sqlalchemy import text as sqltext

    worker = "a9a79363-609b-5848-a4b3-33982797cfb8"
    other = conn.execute(sqltext(
        "INSERT INTO app.tenants (public_id, name, scope) VALUES "
        "(gen_random_uuid(), 't7_scope_ok', 'internal') RETURNING public_id")).first()
    other_pub = str(other[0])
    r = ActorResolver(conn, user_directory=FakeUserDirectory())
    # 正确 scope -> 通过
    rec = r.assert_can_act(worker, tenant["public_id"],
                           worker_scope_tenant_public_id=tenant["public_id"])
    assert rec.kind == "worker"
    # 错误 scope（任务属 other，操作 tenant）-> WorkerScopeError
    with pytest.raises(WorkerScopeError):
        r.assert_can_act(worker, tenant["public_id"], worker_scope_tenant_public_id=other_pub)
    # 缺 scope -> WorkerScopeError
    with pytest.raises(WorkerScopeError):
        r.assert_can_act(worker, tenant["public_id"])


# ---------------------------------------------------------------------------
# R84-2：UUID 规范化贯穿 membership/scope + UserRecord 身份核对
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("variant", [
    "canonical", "upper", "compact", "uuid_obj",
])
def test_membership_canonical_forms_accepted(conn, tenant, variant):
    """R84-2：同值 user 的 canonical/uppercase/无连字符/UUID 对象均有 membership -> 通过。"""
    actor = _uid()  # 规范小写
    if variant == "upper":
        input_actor = actor.upper()
    elif variant == "compact":
        input_actor = actor.replace("-", "")
    elif variant == "uuid_obj":
        input_actor = uuid.UUID(actor)
    else:
        input_actor = actor
    directory = FakeUserDirectory(
        users={actor: UserRecord(actor_id=actor, email="m@example.com", status="active")},
        memberships={(actor, tenant["public_id"]): "admin"},
    )
    r = ActorResolver(conn, user_directory=directory)
    rec = r.assert_can_act(input_actor, tenant["public_id"])
    assert rec.kind == "user"


def test_membership_upper_tenant_accepted(conn, tenant):
    """R84-2：tenant 大写表示同样命中 membership（入口规范化）。"""
    actor = _uid()
    directory = FakeUserDirectory(
        users={actor: UserRecord(actor_id=actor, email="t@example.com", status="active")},
        memberships={(actor, tenant["public_id"]): "operator"},
    )
    r = ActorResolver(conn, user_directory=directory)
    rec = r.assert_can_act(actor, tenant["public_id"].upper())
    assert rec.kind == "user"


def test_membership_no_membership_rejected(conn, tenant):
    """R84-2：无 membership 的 user（同值规范化输入）-> 跨租户拒绝。"""
    actor = _uid()
    directory = FakeUserDirectory(
        users={actor: UserRecord(actor_id=actor, email="n@example.com", status="active")},
        memberships={},
    )
    r = ActorResolver(conn, user_directory=directory)
    with pytest.raises(TenantForbiddenError):
        r.assert_can_act(actor, tenant["public_id"])


def test_directory_wrong_record_rejected_audit_zero(conn, tenant):
    """R84-2：目录返回其他用户记录（身份错位）-> fail closed，审计零新增。"""
    from sqlalchemy import text as sqltext

    from domain.audit import write_audit_event

    from infra.auth import ActorDirectoryMismatchError as ADM

    user = _uid()
    wrong = _uid()

    class WrongDirectory(FakeUserDirectory):
        def lookup(self, actor_id):
            return UserRecord(actor_id=wrong, email="wrong@example.com", status="active")

    before = conn.execute(sqltext("SELECT count(*) FROM app.audit_events")).scalar()
    with pytest.raises(ADM):
        write_audit_event(
            conn, actor_id=user, tenant_public_id=tenant["public_id"],
            action="t7.wrong", target_type="tenant", target_public_id=tenant["public_id"],
            user_directory=WrongDirectory(),
        )
    after = conn.execute(sqltext("SELECT count(*) FROM app.audit_events")).scalar()
    assert after == before  # 零新增


def test_directory_invalid_uuid_rejected(conn, tenant):
    """R84-2：目录返回非法 actor_id（非 UUID）-> ActorDirectoryMismatchError。"""
    from infra.auth import ActorDirectoryMismatchError as ADM

    user = _uid()

    class BadDirectory(FakeUserDirectory):
        def lookup(self, actor_id):
            return UserRecord(actor_id="not-a-uuid", email="bad@example.com", status="active")

    r = ActorResolver(conn, user_directory=BadDirectory())
    with pytest.raises(ADM):
        r.assert_can_act(user, tenant["public_id"])
