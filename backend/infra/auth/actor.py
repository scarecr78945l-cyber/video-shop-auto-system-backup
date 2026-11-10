# -*- coding: utf-8 -*-
"""actor：身份解析与权限校验基座（P0-1 T7，round-81；round-83 R82-2/R82-3 聚焦回修）。

契约（auth-boundary.md §五/§六/§八）：
- actor 双来源唯一命中：写审计前验证**恰好命中一个来源**（actor_registry 或 users），0 或 2 都拒绝；
- 审计 join 顺序：先 registry 后 users；
- 跨 tenant membership 拒绝；active/disabled 状态；角色值集 admin/operator/viewer；
- 后台 worker 租户上下文：worker 任务须显式声明所属 tenant（经可信 scope，T8 从 workflow_run 加载）。

round-83 回修（Codex round-82 R82-2/R82-3）：
- R82-2：两源共用规范化 UUID（str(uuid.UUID(x)) 小写规范形）；目录缺失/异常与「查无用户」
  分开处理（ActorDirectoryUnavailableError，fail closed）；canonical/uppercase/无连字符同值
  输入的双命中均抛 ActorAmbiguousError；目录未配置/失效时写审计零新增；
- R82-3：membership role 无论是否传 required_role 都先做值集门禁（admin/operator/viewer，
  空串/未知拒绝）；worker 增加可信 scope 输入（worker_scope_tenant_public_id），与操作
  tenant exact equality 门禁，缺 scope 拒绝（T8 再从真实任务加载该 scope）。

实现说明（round-20 §七 gate）：
- better-auth users/tenant_members 表**未创建**（gate 未过）。`UserDirectory` 是注入式目录接口：
  生产实现指向 better-auth（auth schema，**未确认**）；本包不宣称真实 IdP 能力。
- actor_registry（app schema）与 tenants（app schema）为本包真实落库来源（种子 migration t7seed000001）。
- 验收在真实 PostgreSQL 事务内执行：registry/tenants 走真实表，user 类 actor 经受控目录 fixture
  验证应用层校验（auth-boundary §六：外部 schema 无 DB FK 时以事务内应用断言 + 审计证据补足）。
"""
from __future__ import annotations

import uuid as _uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

# v6 §6.8 enum_actor_kind / enum_actor_status（auth-boundary §五）
ACTOR_KINDS = {"user", "system", "worker", "service"}
ACTOR_STATUSES = {"active", "disabled"}
TENANT_ROLES = {"admin", "operator", "viewer"}
ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}


class ActorError(Exception):
    """auth 基座契约错误基类。"""


class ActorNotFoundError(ActorError):
    """actor 在两个来源均不存在（伪造 actor_id）。"""


class ActorAmbiguousError(ActorError):
    """actor 同时命中 actor_registry 与 users（双来源歧义）。"""


class ActorDisabledError(ActorError):
    """actor 状态为 disabled（停用用户/停用 worker）。"""


class ActorDirectoryUnavailableError(ActorError):
    """UserDirectory 未注入或异常（第二来源未校验；完整双源校验必须显式依赖目录）。"""


class ActorDirectoryMismatchError(ActorError):
    """目录返回的 UserRecord.actor_id 与请求 UUID 不一致（adapter 契约失配，fail closed）。"""


class TenantNotFoundError(ActorError):
    """tenant_public_id 不存在（未知租户）。"""


class TenantForbiddenError(ActorError):
    """跨 tenant membership / role 越权 / 未知 role 值。"""


class WorkerScopeError(ActorError):
    """worker 缺少可信 scope 或 scope 与操作 tenant 不一致。"""


@dataclass(frozen=True)
class ActorRecord:
    actor_id: str          # 规范化 UUID（小写规范形）
    kind: str              # user / system / worker / service
    name: str
    status: str            # active / disabled
    source: str            # 'registry' | 'users'


@dataclass(frozen=True)
class UserRecord:
    actor_id: str
    email: str
    status: str            # active / disabled


def canonical_uuid(value: str) -> str:
    """R82-2：统一 UUID 规范形式（小写规范形 str(uuid.UUID(x))）。非法抛 ValueError。"""
    return str(_uuid.UUID(str(value)))


class UserDirectory(ABC):
    """better-auth users/tenant_members 目录接口（gate 前注入式；生产实现未确认）。"""

    @abstractmethod
    def lookup(self, actor_id: str) -> Optional[UserRecord]:
        """按 actor_id 查 users（actor_id 为规范化 UUID）；不存在返回 None。"""

    @abstractmethod
    def membership(self, actor_id: str, tenant_public_id: str) -> Optional[str]:
        """返回该 user 在 tenant 的角色；无 membership 返回 None。"""


class ActorResolver:
    """actor 唯一命中解析 + 权限校验（auth-boundary §五/§六/§八；R82-2/R82-3 加固）。"""

    def __init__(self, conn: Connection, user_directory: Optional[UserDirectory] = None):
        self._conn = conn
        self._users = user_directory

    # ---- 解析：先 registry 后 users；恰好命中一个来源 ----
    def resolve(self, actor_id: str) -> ActorRecord:
        cid = canonical_uuid(actor_id)  # R82-2：两源共用规范化 UUID
        reg = self._lookup_registry(cid)
        usr = self._lookup_user(cid)    # R82-2：目录缺失/异常与查无用户分开
        hits = []
        if reg is not None:
            hits.append(ActorRecord(actor_id=cid, kind=reg["actor_kind"],
                                    name=reg["name"], status=reg["status"], source="registry"))
        if usr is not None:
            hits.append(ActorRecord(actor_id=cid, kind="user",
                                    name=usr.email, status=usr.status, source="users"))
        if len(hits) == 0:
            raise ActorNotFoundError(f"伪造 actor_id（registry 与 users 均不存在）: {cid}")
        if len(hits) > 1:
            raise ActorAmbiguousError(f"actor 双来源命中（registry+users 同 UUID）: {cid}")
        return hits[0]

    def _lookup_registry(self, cid: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            text("SELECT actor_id, actor_kind, name, status FROM app.actor_registry "
                 "WHERE actor_id = :a"),
            {"a": cid},
        ).mappings().first()
        return dict(row) if row is not None else None

    def _lookup_user(self, cid: str) -> Optional[UserRecord]:
        if self._users is None:
            raise ActorDirectoryUnavailableError(
                f"UserDirectory 未注入（第二来源未校验；完整双源校验必须显式依赖目录）: {cid}")
        try:
            rec = self._users.lookup(cid)
        except ActorDirectoryUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ActorDirectoryUnavailableError(
                f"UserDirectory 异常（fail closed）: {cid}（{type(exc).__name__}: {exc}）") from exc
        if rec is None:
            return None
        # R84-2：目录返回记录必须与请求 UUID 值相等（规范形核对），否则 adapter 契约失配
        try:
            returned_cid = canonical_uuid(rec.actor_id)
        except (ValueError, TypeError) as exc:  # noqa: BLE001
            raise ActorDirectoryMismatchError(
                f"UserDirectory 返回非法 actor_id（fail closed）: {rec.actor_id!r}") from exc
        if returned_cid != cid:
            raise ActorDirectoryMismatchError(
                f"UserDirectory 返回记录身份错位（fail closed）: requested={cid} returned={returned_cid}")
        return rec

    def _tenant_public_id_exists(self, tenant_public_id: str) -> bool:
        row = self._conn.execute(
            text("SELECT 1 FROM app.tenants WHERE public_id = :t"),
            {"t": tenant_public_id},
        ).first()
        return row is not None

    def _validate_role_value(self, role: Optional[str]) -> Optional[str]:
        """R82-3：membership role 值集门禁（无论是否传 required_role）。"""
        if role is None:
            return None
        if role not in TENANT_ROLES:
            raise TenantForbiddenError(f"未知 membership role 值: {role!r}（允许 admin/operator/viewer）")
        return role

    # ---- 权限校验：停用 / 跨租户 / role 值集与越权 / worker 可信 scope ----
    def assert_can_act(
        self,
        actor_id: str,
        tenant_public_id: str,
        required_role: Optional[str] = None,
        worker_scope_tenant_public_id: Optional[str] = None,
    ) -> ActorRecord:
        """校验 actor 可代表 tenant 执行；返回解析记录。

        R84-2：actor/tenant/scope 入口统一 canonical_uuid；membership 用解析后 rec.actor_id；
        worker scope equality 用规范 UUID 值比较。
        """
        cid = canonical_uuid(actor_id)
        tid = canonical_uuid(tenant_public_id)
        scope = canonical_uuid(worker_scope_tenant_public_id) if worker_scope_tenant_public_id is not None else None
        rec = self.resolve(cid)
        if rec.status != "active":
            raise ActorDisabledError(f"actor 已停用: {cid}（status={rec.status}）")
        if not self._tenant_public_id_exists(tid):
            raise TenantNotFoundError(f"未知 tenant_public_id: {tid}")
        if rec.kind == "user":
            if self._users is None:
                raise ActorDirectoryUnavailableError(
                    f"user 类 actor 校验需要 UserDirectory（better-auth gate 未过，未确认）: {cid}")
            role = self._validate_role_value(self._users.membership(rec.actor_id, tid))
            if role is None:
                raise TenantForbiddenError(f"跨 tenant membership: {cid} 不在 {tid}")
            if required_role is not None:
                self._validate_role_value(required_role)
                if ROLE_RANK.get(role, 0) < ROLE_RANK.get(required_role, 99):
                    raise TenantForbiddenError(
                        f"role 越权: {cid} role={role} < required={required_role}")
        elif rec.kind == "worker":
            # R82-3：可信 worker scope 与 tenant exact equality；缺 scope 拒绝
            if scope is None:
                raise WorkerScopeError(f"worker 缺少可信 scope: {cid}")
            if scope != tid:
                raise WorkerScopeError(
                    f"worker scope 与操作 tenant 不一致: scope={scope} != tenant={tid}")
        # system/service：trusted 类，无需 scope（T8 任务 scope 另由 workflow_run 绑定）
        return rec
