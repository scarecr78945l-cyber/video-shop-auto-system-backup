# -*- coding: utf-8 -*-
"""audit：审计写入基座（P0-1 T7，round-81）。

契约（auth-boundary.md §七/§八 + 15-数据字典.md v6 §6.4 audit_events）：
- 审计写入带 actor_id / target_type / target_public_id / request_id；
- 写审计前校验 actor 恰好命中一个来源（先 registry 后 users），伪造/双命中/停用拒绝；
- 事务内应用断言补足外部 schema 无 DB FK（auth-boundary §六）；
- request_id 贯通：同一请求链路复用（前端/API/worker）。

本包不创建表：audit_events 已在 T3（31tbl000001）落库；本模块为纯写入/校验逻辑。
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from infra.auth.actor import ActorResolver


class AuditError(Exception):
    """审计写入契约错误。"""


def write_audit_event(
    conn: Connection,
    *,
    actor_id: str,
    tenant_public_id: str,
    action: str,
    target_type: str,
    target_public_id: str,
    request_id: Optional[str] = None,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    evidence_ref: Optional[str] = None,
    required_role: Optional[str] = None,
    worker_scope_tenant_public_id: Optional[str] = None,
    user_directory: Optional[Any] = None,
) -> int:
    """写一条 audit_events（真实 PG 事务内）。

    流程：
    1. ActorResolver.assert_can_act 校验（伪造/停用/未知租户/跨租户/越权/worker 可信 scope）；
       完整双源校验显式依赖 UserDirectory（R82-2：目录缺失/异常 fail closed，零新增）；
    2. 由 tenant_public_id 解析 app.tenants.id（不存在抛 AuditError）；
    3. INSERT audit_events（带 request_id），返回新行 id。
    """
    if not (action and target_type and target_public_id):
        raise AuditError("action/target_type/target_public_id 均必填")
    resolver = ActorResolver(conn, user_directory=user_directory)
    resolver.assert_can_act(
        actor_id, tenant_public_id,
        required_role=required_role,
        worker_scope_tenant_public_id=worker_scope_tenant_public_id,
    )
    tenant_row = conn.execute(
        text("SELECT id FROM app.tenants WHERE public_id = :t"), {"t": tenant_public_id}
    ).first()
    if tenant_row is None:
        raise AuditError(f"tenant_public_id 不存在: {tenant_public_id}")
    tenant_id = tenant_row[0]
    row = conn.execute(
        text(
            "INSERT INTO app.audit_events "
            "(tenant_id, actor_id, action, target_type, target_public_id, before, after, "
            " evidence_ref, request_id) "
            "VALUES (:tenant_id, :actor_id, :action, :target_type, :target_public_id, "
            ":before, :after, :evidence_ref, :request_id) "
            "RETURNING id"
        ),
        {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_public_id": target_public_id,
            "before": _json_dumps(before),
            "after": _json_dumps(after),
            "evidence_ref": evidence_ref,
            "request_id": request_id,
        },
    )
    return row.scalar()


def _json_dumps(value: Optional[dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    import json

    return json.dumps(value, ensure_ascii=True)
