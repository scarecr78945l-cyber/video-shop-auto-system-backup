# -*- coding: utf-8 -*-
"""backend.infra.auth：认证/身份基座（P0-1 T7，round-81；round-83 R82-2/R82-3 回修）。

依据 auth-boundary.md（P0-0 批 C 冻结契约）：
- 身份源：better-auth（自托管 IdP）提供 users/sessions/tenant_members（auth schema，未建表，
  round-20 §七 gate 通过前不创建）；
- actor 双来源：actor_registry（app schema，本包落种子 system/worker/service）+ better-auth users；
- 业务表 actor_id 不建跨 schema DB FK；应用层校验 + 审计 join（先 registry 后 users）；
- 四类验收：伪造 actor_id 拒绝 / 跨 tenant membership 拒绝 / 停用用户拒绝 / 后台 worker 带正确租户上下文可执行；
- 四补项：双命中 actor 拒绝 / 未知 tenant_public_id 拒绝 / role 越权拒绝 / request_id 贯通。
"""
from .actor import (  # noqa: F401
    ACTOR_KINDS,
    ACTOR_STATUSES,
    ROLE_RANK,
    TENANT_ROLES,
    ActorAmbiguousError,
    ActorDirectoryMismatchError,
    ActorDirectoryUnavailableError,
    ActorDisabledError,
    ActorError,
    ActorNotFoundError,
    ActorRecord,
    ActorResolver,
    TenantForbiddenError,
    TenantNotFoundError,
    UserDirectory,
    UserRecord,
    WorkerScopeError,
    canonical_uuid,
)
from .organization import (  # noqa: F401
    OrganizationError,
    bind_tenant_organization,
    set_member_role,
    unbind_tenant_organization,
)
from .pg_directory import PgUserDirectory  # noqa: F401

__all__ = [
    "ACTOR_KINDS",
    "ACTOR_STATUSES",
    "ROLE_RANK",
    "TENANT_ROLES",
    "ActorAmbiguousError",
    "ActorDirectoryMismatchError",
    "ActorDirectoryUnavailableError",
    "ActorDisabledError",
    "ActorError",
    "ActorNotFoundError",
    "ActorRecord",
    "ActorResolver",
    "OrganizationError",
    "PgUserDirectory",
    "TenantForbiddenError",
    "TenantNotFoundError",
    "UserDirectory",
    "UserRecord",
    "WorkerScopeError",
    "bind_tenant_organization",
    "canonical_uuid",
    "set_member_role",
    "unbind_tenant_organization",
]
