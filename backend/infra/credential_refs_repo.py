# -*- coding: utf-8 -*-
"""credential_refs 持久化 adapter/repository + 集成 service（P0-1 T6，round-73 R72-1；round-75 R74-1；round-77 R76-1）。

契约：15-数据字典.md v6 §1.5 `credential_refs.secret_store_key varchar(256)` 为 secret store 定位符，
业务库只存定位符，凭证本体只进 secret store。

round-77 回修（Codex round-76 R76-1）：
- `CredentialRefsRepo.insert(store=...)` 的 store 改为**必传且非空**（不再允许 store=None 绕过）：
  无条件 `store.get(locator)` 来源核对（伪造 locator -> SecretNotFoundError）+ meta 四元组复核；
- display 由 `store.get` 返回的 secret 经 `_redact_display` 内部计算（调用方不再传任意字符串，
  形状合法但内容不匹配的 `FULL_SECRET_LEAK***` 不可能进入业务表）；
- `store_credential()` 集成 service：`SecretStore.put` + `repo.insert(store=store)` 单一入口。
"""
from __future__ import annotations

import datetime
from typing import Any, Mapping, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .secret_store import (
    MAX_LOCATOR_LEN,
    SecretStore,
    SecretStoreError,
    redacted_display as _redact_display,
    validate_locator,
)

_VALID_STATUSES = {"valid", "expired", "rotating", "revoked"}


class CredentialRefsRepo:
    """app.credential_refs 持久化 adapter（只存定位符，不经 ORM 模型，避免无谓耦合）。"""

    def insert(
        self,
        conn: Connection,
        *,
        store: SecretStore,
        tenant_id: int,
        account_id: int,
        purpose: str,
        rotation_seq: int,
        locator: str,
        status: str = "valid",
        expires_at: Optional[str] = None,
    ) -> int:
        """真实 INSERT 一行 credential_refs，返回新行 id（round-77 R76-1）。

        R76-1 强制来源与 display 绑定（不再允许 store=None 绕过）：
        1. store 必传且非空（无默认 None）——「只接收 SecretStore 产生的 locator」成为方法级契约；
        2. 无条件执行 store.get(locator)：语法合法但 store 不存在的伪造 locator -> SecretNotFoundError；
        3. 解密 meta 的 tenant/account/purpose/rotation_seq 与调用方 4 元组 exact equality；
        4. display 由 store.get 返回的 secret 经 _redact_display 内部计算（调用方不再传任意字符串），
           FULL_SECRET_LEAK*** 等形状合法但内容不匹配的输入不再可能进入业务表。
        """
        if store is None:
            raise SecretStoreError("repo.insert 必须提供 store（SecretStore 来源保证）")
        if not isinstance(locator, str) or len(locator) > MAX_LOCATOR_LEN:
            raise SecretStoreError("credential_refs.secret_store_key 必须为 secret store 定位符（<=256）")
        l_tenant, l_account, l_purpose, l_seq, _ = validate_locator(locator)
        if (l_tenant, l_account, l_purpose, l_seq) != (tenant_id, account_id, purpose, rotation_seq):
            raise SecretStoreError(
                f"locator 上下文与业务列不一致: locator=({l_tenant},{l_account},{l_purpose},{l_seq}) "
                f"!= row=({tenant_id},{account_id},{purpose},{rotation_seq})"
            )
        # 来源保证：locator 必须由该 SecretStore 产生且可解密；meta 四元组复核
        secret, meta = store.get(locator)
        m = (meta.get("tenant_id"), meta.get("account_id"), meta.get("purpose"), meta.get("rotation_seq"))
        if m != (tenant_id, account_id, purpose, rotation_seq):
            raise SecretStoreError(f"store meta 与业务列不一致: meta={m}")
        display = _redact_display(secret)  # display 由 secret 内部计算（exact 绑定）
        if status not in _VALID_STATUSES:
            raise SecretStoreError(f"credential_refs.status 非法: {status!r}")
        if expires_at is not None:
            expires_at = str(expires_at)
        res = conn.execute(
            text(
                "INSERT INTO app.credential_refs "
                "(tenant_id, account_id, purpose, rotation_seq, secret_store_key, status, "
                " expires_at, redacted_display) "
                "VALUES (:tenant_id, :account_id, :purpose, :rotation_seq, :secret_store_key, "
                ":status, CAST(:expires_at AS timestamptz), :redacted_display) "
                "RETURNING id"
            ),
            {
                "tenant_id": tenant_id,
                "account_id": account_id,
                "purpose": purpose,
                "rotation_seq": rotation_seq,
                "secret_store_key": locator,
                "status": status,
                "expires_at": expires_at,
                "redacted_display": display,
            },
        )
        return res.scalar()

    def select_by(
        self,
        conn: Connection,
        *,
        tenant_id: int,
        account_id: int,
        purpose: str,
        rotation_seq: Optional[int] = None,
    ) -> list[Mapping[str, Any]]:
        """按 (tenant_id, account_id, purpose[, rotation_seq]) 读取行（仅定位符，无凭证）。"""
        sql = (
            "SELECT id, tenant_id, account_id, purpose, rotation_seq, secret_store_key, "
            "       status, expires_at, redacted_display, created_at, updated_at "
            "FROM app.credential_refs "
            "WHERE tenant_id=:tenant_id AND account_id=:account_id AND purpose=:purpose"
        )
        params: dict[str, Any] = {"tenant_id": tenant_id, "account_id": account_id, "purpose": purpose}
        if rotation_seq is not None:
            sql += " AND rotation_seq=:rotation_seq"
            params["rotation_seq"] = rotation_seq
        sql += " ORDER BY rotation_seq"
        return [dict(r) for r in conn.execute(text(sql), params).mappings()]

    @staticmethod
    def now_iso() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()


def store_credential(
    conn: Connection,
    store: SecretStore,
    *,
    tenant_id: int,
    account_id: int,
    purpose: str,
    secret: bytes,
    rotation_seq: int = 1,
    expires_at: Optional[str] = None,
    status: str = "valid",
) -> tuple[str, int]:
    """R74-1 + R76-1 集成 service：SecretStore.put + repo.insert 单一入口。

    - repo.insert 内部无条件 store.get 来源核对 + meta 四元组复核 + display 由 secret 内部计算；
    - 返回 (locator, row_id)。全程不经 float/明文日志。
    """
    locator = store.put(
        tenant_id=tenant_id, account_id=account_id, purpose=purpose, secret=secret,
        rotation_seq=rotation_seq, expires_at=expires_at,
    )
    repo = CredentialRefsRepo()
    row_id = repo.insert(
        conn, store=store,
        tenant_id=tenant_id, account_id=account_id, purpose=purpose,
        rotation_seq=rotation_seq, locator=locator,
        status=status, expires_at=expires_at,
    )
    return locator, row_id
