# -*- coding: utf-8 -*-
"""pg_directory：生产 UserDirectory（读 better-auth auth schema 表，round-91）。

映射（auth-gate.md §三 定稿）：
- lookup(actor_id)：auth.user WHERE id=:a -> UserRecord(actor_id, email, status)；
  status 为停用权威来源（auth.user.status，round-88 定稿，不借 registry）；
- membership(actor_id, tenant_public_id)：auth.member JOIN auth.organization
  ON member.organization_id = organization.id
  WHERE member.user_id=:a AND organization.slug=:t -> member.role；
  slug = app.tenants.public_id（租户绑定，round-89 定稿）。

生产路径：真实数据库 adapter（SQLAlchemy 直连同库同 schema），非注入 fixture。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .actor import UserDirectory, UserRecord, canonical_uuid


class PgUserDirectory(UserDirectory):
    """better-auth auth schema 生产目录（真实 PG 读取）。"""

    def __init__(self, conn: Connection):
        self._conn = conn

    def lookup(self, actor_id: str) -> Optional[UserRecord]:
        cid = canonical_uuid(actor_id)
        row = self._conn.execute(
            text("SELECT id, email, status FROM auth.user WHERE id = :a"), {"a": cid}
        ).mappings().first()
        if row is None:
            return None
        return UserRecord(actor_id=str(row["id"]), email=str(row["email"]),
                          status=str(row["status"]))

    def membership(self, actor_id: str, tenant_public_id: str) -> Optional[str]:
        cid = canonical_uuid(actor_id)
        tid = canonical_uuid(tenant_public_id)  # R92-3A：slug 查询统一规范 UUID
        rows = self._conn.execute(
            text(
                "SELECT m.role FROM auth.member m "
                "JOIN auth.organization o ON o.id = m.organization_id "
                "WHERE m.user_id = :a AND o.slug = :t"
            ),
            {"a": cid, "t": tid},
        ).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            # R92-3B：成员多行歧义失败闭合（不应取首行）
            from .actor import ActorDirectoryMismatchError

            raise ActorDirectoryMismatchError(
                f"成员多行歧义（auth.member 唯一约束缺失或数据损坏）: user={cid} tenant={tid} rows={len(rows)}")
        return str(rows[0][0])
