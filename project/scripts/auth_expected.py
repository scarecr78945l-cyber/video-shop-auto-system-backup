# -*- coding: utf-8 -*-
"""auth 独立冻结 expected（round-123 R122-1 定稿）。

来源：auth-gate.md §四（生成 snapshot hash 81E2AD7D...，round-90 冻结）+ auth000001/000002 migration
（round-91/93 应用）——**不从当前运行时导出 expected**（避免"迁移与自身一致"假通过）。

覆盖：
  - 7 表列定义（name/type/null/default）：user/session/account/verification/organization/member/invitation
  - 7 PK（表/名/列）
  - 3 UNIQUE（user.email / session.token / organization.slug）+ account(issuer,account_id) 唯一索引
  - 6 FK（名称/child 列/父表/父列/ON DELETE）：session.user_id→user.id CASCADE、
    account.user_id→user.id CASCADE、member.organization_id→organization.id CASCADE、
    member.user_id→user.id CASCADE、invitation.organization_id→organization.id CASCADE、
    invitation.inviter_id→user.id CASCADE
  - member (organization_id,user_id) UNIQUE（auth000002 新增）
"""

# 7 表名
TABLES = ["user", "session", "account", "verification", "organization", "member", "invitation"]

# 表 -> 列定义（name: (type, nullable, default)）——冻结于 auth-gate snapshot
COLUMNS = {
    "user": {
        "id": ("uuid", False, "gen_random_uuid()"), "name": ("text", False, None),
        "email": ("text", False, None), "email_verified": ("boolean", False, "false"),
        "image": ("text", True, None), "created_at": ("timestamp with time zone", False, "now()"),
        "updated_at": ("timestamp with time zone", False, "now()"),
        "status": ("text", False, "'active'::text"),
    },
    "session": {
        "id": ("uuid", False, "gen_random_uuid()"), "expires_at": ("timestamp with time zone", False, None),
        "token": ("text", False, None), "created_at": ("timestamp with time zone", False, "now()"),
        "updated_at": ("timestamp with time zone", False, None),  # auth000002 移除默认
        "ip_address": ("text", True, None), "user_agent": ("text", True, None),
        "user_id": ("uuid", False, None), "active_organization_id": ("text", True, None),
    },
    "account": {
        "id": ("uuid", False, "gen_random_uuid()"), "issuer": ("text", False, None),
        "account_id": ("text", False, None), "provider_id": ("text", False, None),
        "user_id": ("uuid", False, None), "access_token": ("text", True, None),
        "refresh_token": ("text", True, None), "id_token": ("text", True, None),
        "access_token_expires_at": ("timestamp with time zone", True, None),
        "refresh_token_expires_at": ("timestamp with time zone", True, None),
        "scope": ("text", True, None), "password": ("text", True, None),
        "created_at": ("timestamp with time zone", False, "now()"),
        "updated_at": ("timestamp with time zone", False, None),  # auth000002 移除默认
    },
    "verification": {
        "id": ("uuid", False, "gen_random_uuid()"), "identifier": ("text", False, None),
        "value": ("text", False, None), "expires_at": ("timestamp with time zone", False, None),
        "created_at": ("timestamp with time zone", False, "now()"),
        "updated_at": ("timestamp with time zone", False, "now()"),
    },
    "organization": {
        "id": ("uuid", False, "gen_random_uuid()"), "name": ("text", False, None),
        "slug": ("text", False, None), "logo": ("text", True, None),
        "created_at": ("timestamp with time zone", False, None), "metadata": ("text", True, None),
    },
    "member": {
        "id": ("uuid", False, "gen_random_uuid()"), "organization_id": ("uuid", False, None),
        "user_id": ("uuid", False, None), "role": ("text", False, "'member'::text"),
        "created_at": ("timestamp with time zone", False, None),
    },
    "invitation": {
        "id": ("uuid", False, "gen_random_uuid()"), "organization_id": ("uuid", False, None),
        "email": ("text", False, None), "role": ("text", True, None),
        "status": ("text", False, "'pending'::text"),
        "expires_at": ("timestamp with time zone", False, None),
        "created_at": ("timestamp with time zone", False, "now()"),
        "inviter_id": ("uuid", False, None),
    },
}

# 7 PK（表, 约束名, 列）
PRIMARY_KEYS = [
    ("user", "user_pkey", ("id",)),
    ("session", "session_pkey", ("id",)),
    ("account", "account_pkey", ("id",)),
    ("verification", "verification_pkey", ("id",)),
    ("organization", "organization_pkey", ("id",)),
    ("member", "member_pkey", ("id",)),
    ("invitation", "invitation_pkey", ("id",)),
]

# UNIQUE（表, 约束名, 列）
UNIQUES = [
    ("user", "user_email_unique", ("email",)),
    ("session", "session_token_unique", ("token",)),
    ("organization", "organization_slug_unique", ("slug",)),
    ("account", "account_issuer_accountId_uidx", ("issuer", "account_id")),
    ("member", "member_organization_id_user_id_uidx", ("organization_id", "user_id")),
]

# 6 FK（child 表, 约束名, child 列, 父表, 父列, ON DELETE）
FOREIGN_KEYS = [
    ("session", "session_user_id_fkey", ("user_id",), "user", ("id",), "CASCADE"),
    ("account", "account_user_id_fkey", ("user_id",), "user", ("id",), "CASCADE"),
    ("member", "member_organization_id_fkey", ("organization_id",), "organization", ("id",), "CASCADE"),
    ("member", "member_user_id_fkey", ("user_id",), "user", ("id",), "CASCADE"),
    ("invitation", "invitation_organization_id_fkey", ("organization_id",), "organization", ("id",), "CASCADE"),
    ("invitation", "invitation_inviter_id_fkey", ("inviter_id",), "user", ("id",), "CASCADE"),
]
