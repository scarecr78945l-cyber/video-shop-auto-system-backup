# -*- coding: utf-8 -*-
"""organization：租户绑定与成员角色保护（round-91；round-93 R92-2/R92-3 聚焦回修）。

定稿规则（auth-gate.md §三 + round-88 R88-1 + round-92 R92-2/R92-3）：
- 租户绑定：organization.slug = app.tenants.public_id（逻辑引用），**全链 canonical_uuid 规范化**
  （写入/查询/解绑统一小写规范形，round-92 §A 防止同一租户大小写双组织）；
- 创建/修改仅限 service/worker 服务端 actor（应用断言）；
- **首位 admin 流程（R92-2）**：service/worker 创建后由服务端显式指定首位用户管理员
  （first_admin_user_id，写 member role=admin）；未指定则创建时无 member（审计承载创建者）；
- slug 绑定后不可变（创建后禁止改 slug；重复绑定/大小写等价均拒绝）；
- 角色：member.role 业务白名单 admin/operator/viewer；'owner'/'member'/未知拒绝；
- 成员唯一性（R92-3）：auth.member (organization_id,user_id) 唯一约束（auth000002），
  目录读取多行抛歧义（ActorDirectoryMismatchError 语义）；
- 删除一致性：解绑含 member/invitation 时拒绝（须先清空成员）；CASCADE 清理后无悬空；
- **审计串联（R92-2）**：bind/set_role/unbind 在同一事务内写 audit_events
  （actor/action/target_type=organization/target_public_id/request_id/worker scope）。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from domain.audit import write_audit_event
from .actor import TENANT_ROLES, ActorResolver, canonical_uuid

ORG_SCHEMA = "auth"


class OrganizationError(Exception):
    """租户绑定/成员角色契约错误。"""


def _tenant_exists(conn: Connection, tenant_public_id: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM app.tenants WHERE public_id = :t"), {"t": tenant_public_id}
    ).first()
    return row is not None


def _organization_id_by_slug(conn: Connection, slug: str) -> Optional[str]:
    """slug 查询：入参已 canonical_uuid（调用方统一规范化）。"""
    row = conn.execute(
        text(f"SELECT id FROM {ORG_SCHEMA}.organization WHERE slug = :s"), {"s": slug}
    ).first()
    return str(row[0]) if row is not None else None


def _member_row(conn: Connection, org_id: str, user_id: str):
    return conn.execute(
        text(
            f"SELECT role FROM {ORG_SCHEMA}.member WHERE organization_id = :o AND user_id = :u"
        ),
        {"o": org_id, "u": user_id},
    ).first()


def bind_tenant_organization(
    conn: Connection,
    *,
    actor_id: str,
    tenant_public_id: str,
    organization_name: str,
    request_id: Optional[str] = None,
    first_admin_user_id: Optional[str] = None,
    worker_scope_tenant_public_id: Optional[str] = None,
    user_directory: Optional[object] = None,
) -> str:
    """创建 organization（slug=tenant_public_id 规范化）（round-90 §三.3 + R92-2/R92-3）。

    前置：actor 必须是 service/worker（服务端 actor）；tenant 存在；slug（规范形）未占用。
    首位 admin（可选）：first_admin_user_id 为 auth.user，写 member role=admin；
    否则创建时无 member（创建者身份由审计承载）。
    同事务写 audit_events（action='org.bind'）。
    返回 organization.id。
    """
    tid = canonical_uuid(tenant_public_id)
    scope = canonical_uuid(worker_scope_tenant_public_id) if worker_scope_tenant_public_id else None
    resolver = ActorResolver(conn, user_directory=user_directory)
    rec = resolver.resolve(actor_id)
    if rec.kind not in ("service", "worker"):
        raise OrganizationError(f"租户绑定仅限 service/worker actor: {rec.kind}（{actor_id}）")
    resolver.assert_can_act(actor_id, tid, worker_scope_tenant_public_id=scope)
    if not _tenant_exists(conn, tid):
        raise OrganizationError(f"tenant 不存在（拒绝悬空绑定）: {tid}")
    existing = _organization_id_by_slug(conn, tid)
    if existing is not None:
        raise OrganizationError(f"organization.slug 已占用（绑定不可重复创建）: {tid}")
    org_id = conn.execute(
        text(
            f"INSERT INTO {ORG_SCHEMA}.organization (name, slug, created_at) "
            "VALUES (:n, :s, now()) RETURNING id"
        ),
        {"n": organization_name, "s": tid},
    ).scalar()
    if first_admin_user_id is not None:
        # 首位 admin：服务端显式指定 user 管理员（R92-2）
        conn.execute(
            text(
                f"INSERT INTO {ORG_SCHEMA}.member (organization_id, user_id, role, created_at) "
                "VALUES (:o, :u, 'admin', now())"
            ),
            {"o": org_id, "u": canonical_uuid(first_admin_user_id)},
        )
    write_audit_event(
        conn, actor_id=actor_id, tenant_public_id=tid, action="org.bind",
        target_type="organization", target_public_id=tid, request_id=request_id,
        worker_scope_tenant_public_id=scope, user_directory=user_directory,
    )
    return str(org_id)


def set_member_role(
    conn: Connection,
    *,
    operator_actor_id: str,
    tenant_public_id: str,
    target_actor_id: str,
    new_role: str,
    request_id: Optional[str] = None,
    operator_scope_tenant_public_id: Optional[str] = None,
    user_directory: Optional[object] = None,
) -> None:
    """成员角色变更（白名单 admin/operator/viewer；拒绝 'member'/'owner'/未知值）。

    前置：operator 必须是该租户的 admin（required_role='admin'）；
    worker 需带可信 scope（R82-3）；目标 user 在 auth.user。
    成员唯一性由 auth.member (organization_id,user_id) UNIQUE 保证（auth000002）。
    同事务写 audit_events（action='org.member.role'）。
    """
    if new_role not in TENANT_ROLES:
        raise OrganizationError(
            f"成员角色必须在业务白名单内: {new_role!r}（允许 admin/operator/viewer）")
    tid = canonical_uuid(tenant_public_id)
    target = canonical_uuid(target_actor_id)
    scope = canonical_uuid(operator_scope_tenant_public_id) if operator_scope_tenant_public_id else None
    resolver = ActorResolver(conn, user_directory=user_directory)
    resolver.assert_can_act(
        operator_actor_id, tid, required_role="admin",
        worker_scope_tenant_public_id=scope,
    )
    org_id = _organization_id_by_slug(conn, tid)
    if org_id is None:
        raise OrganizationError(f"organization.slug 未绑定: {tid}")
    row = _member_row(conn, org_id, target)
    if row is None:
        conn.execute(
            text(
                f"INSERT INTO {ORG_SCHEMA}.member (organization_id, user_id, role, created_at) "
                "VALUES (:o, :u, :r, now())"
            ),
            {"o": org_id, "u": target, "r": new_role},
        )
    else:
        conn.execute(
            text(
                f"UPDATE {ORG_SCHEMA}.member SET role = :r "
                "WHERE organization_id = :o AND user_id = :u"
            ),
            {"r": new_role, "o": org_id, "u": target},
        )
    write_audit_event(
        conn, actor_id=operator_actor_id, tenant_public_id=tid, action="org.member.role",
        target_type="organization", target_public_id=tid, request_id=request_id,
        worker_scope_tenant_public_id=scope, user_directory=user_directory,
    )


def unbind_tenant_organization(
    conn: Connection,
    *,
    actor_id: str,
    tenant_public_id: str,
    request_id: Optional[str] = None,
    worker_scope_tenant_public_id: Optional[str] = None,
    user_directory: Optional[object] = None,
) -> None:
    """删除租户绑定（slug 不可变 + 删除一致性）。

    前置：actor 必须是 service/worker；**含 member/invitation 时拒绝解绑**
    （须先清空成员，避免悬空访问；R92-2）。
    删除后 organization 与 member/invitation 一并清理（CASCADE FK）。
    同事务写 audit_events（action='org.unbind'）。
    """
    tid = canonical_uuid(tenant_public_id)
    scope = canonical_uuid(worker_scope_tenant_public_id) if worker_scope_tenant_public_id else None
    resolver = ActorResolver(conn, user_directory=user_directory)
    rec = resolver.assert_can_act(actor_id, tid, worker_scope_tenant_public_id=scope)
    if rec.kind not in ("service", "worker"):
        raise OrganizationError(f"租户解绑仅限 service/worker actor: {rec.kind}（{actor_id}）")
    org_id = _organization_id_by_slug(conn, tid)
    if org_id is None:
        raise OrganizationError(f"organization.slug 未绑定（无可解绑）: {tid}")
    member_cnt = conn.execute(
        text(f"SELECT count(*) FROM {ORG_SCHEMA}.member WHERE organization_id = :o"),
        {"o": org_id}).scalar()
    if member_cnt and int(member_cnt) > 0:
        raise OrganizationError(
            f"解绑拒绝：organization 仍有 {member_cnt} 个 member（须先清空成员）: {tid}")
    inv_cnt = conn.execute(
        text(f"SELECT count(*) FROM {ORG_SCHEMA}.invitation WHERE organization_id = :o"),
        {"o": org_id}).scalar()
    if inv_cnt and int(inv_cnt) > 0:
        # R94-2 定稿：含 invitation 时同样拒绝（与声明一致，避免悬空邀请访问）
        raise OrganizationError(
            f"解绑拒绝：organization 仍有 {inv_cnt} 个 invitation（须先清空邀请）: {tid}")
    conn.execute(text(f"DELETE FROM {ORG_SCHEMA}.organization WHERE id = :o"), {"o": org_id})
    write_audit_event(
        conn, actor_id=actor_id, tenant_public_id=tid, action="org.unbind",
        target_type="organization", target_public_id=tid, request_id=request_id,
        worker_scope_tenant_public_id=scope, user_directory=user_directory,
    )
