"""T7: auth schema 7 表落库（round-91；来源 frontend/auth-schema.ts v4，snapshot hash 81E2AD7D...）

Revision ID: auth000001
Revises: t7seed000001
Create Date: 2026-09-06T10:00:00+00:00

逐项对照 better-auth 1.7.2 + organization() 生成器 snapshot（auth-gate.md §四）：
- 7 表：user / session / account / verification / organization / member / invitation；
- 显式 schema=auth（T1 env.py search_path 固定 app, pg_catalog，不会自动映射到 auth；
  dsh_migrator 有数据库级 CREATE 权限，可建 auth schema）；
- UUID：id 列 uuid + gen_random_uuid() 默认（advanced.database.generateId="uuid" 对应存储）；
- user.status 扩展列 text default 'active' notNull（停用权威来源，round-88/89 定稿）；
- FK 逐项对照：session.user_id/user 级联、account.user_id/user 级联、member.organization_id/organization、
  member.user_id/user、invitation.organization_id/organization、invitation.inviter_id/user 均 CASCADE；
- 索引/唯一：email unique、token unique、slug unique、account(issuer,account_id) unique，
  session_userId_idx / account_userId_idx / verification_identifier_idx / member_organizationId_idx /
  member_userId_idx / invitation_organizationId_idx / invitation_email_idx。

时序映射（round-90 §三.1）：
- drizzle `timestamp()`（无 withTimezone 选项）默认生成 PG `timestamp without time zone`；
  本迁移采用 **timestamptz**（与 app 业务表时区语义一致、better-auth drizzle adapter 兼容），
  并在 §映射说明中显式记录该决策，供 Codex diff 复核；
- drizzle `$onUpdate` 是运行时行为（Node adapter 写 updated_at），**不**翻译为 DB 触发器/默认值；
  数据库仅 default now()（与 snapshot defaultNow 对应）。

downgrade：删除 7 表 + auth schema（保留 app schema 与 alembic 元数据）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'auth000001'
down_revision: Union[str, Sequence[str], None] = 't7seed000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH = "auth"


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{AUTH}"')
    ts = postgresql.TIMESTAMP(timezone=True)  # timestamptz（映射决策见模块 docstring）
    uuid_default = sa.text("gen_random_uuid()")

    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=uuid_default, primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("image", sa.Text(), nullable=True),
        sa.Column("created_at", ts, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", ts, nullable=False, server_default=sa.text("now()")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.UniqueConstraint("email", name="user_email_unique"),
        schema=AUTH,
    )

    op.create_table(
        "session",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=uuid_default, primary_key=True),
        sa.Column("expires_at", ts, nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("created_at", ts, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", ts, nullable=False, server_default=sa.text("now()")),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("active_organization_id", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE", name="session_user_id_fkey"),
        sa.UniqueConstraint("token", name="session_token_unique"),
        schema=AUTH,
    )
    op.create_index("session_userId_idx", "session", ["user_id"], schema=AUTH)

    op.create_table(
        "account",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=uuid_default, primary_key=True),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("id_token", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", ts, nullable=True),
        sa.Column("refresh_token_expires_at", ts, nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("password", sa.Text(), nullable=True),
        sa.Column("created_at", ts, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", ts, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE", name="account_user_id_fkey"),
        schema=AUTH,
    )
    op.create_index("account_issuer_accountId_uidx", "account", ["issuer", "account_id"], unique=True, schema=AUTH)
    op.create_index("account_userId_idx", "account", ["user_id"], schema=AUTH)

    op.create_table(
        "verification",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=uuid_default, primary_key=True),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("expires_at", ts, nullable=False),
        sa.Column("created_at", ts, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", ts, nullable=False, server_default=sa.text("now()")),
        schema=AUTH,
    )
    op.create_index("verification_identifier_idx", "verification", ["identifier"], schema=AUTH)

    op.create_table(
        "organization",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=uuid_default, primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("logo", sa.Text(), nullable=True),
        sa.Column("created_at", ts, nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.UniqueConstraint("slug", name="organization_slug_unique"),
        schema=AUTH,
    )

    op.create_table(
        "member",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=uuid_default, primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'member'")),
        sa.Column("created_at", ts, nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["auth.organization.id"], ondelete="CASCADE", name="member_organization_id_fkey"),
        sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], ondelete="CASCADE", name="member_user_id_fkey"),
        schema=AUTH,
    )
    op.create_index("member_organizationId_idx", "member", ["organization_id"], schema=AUTH)
    op.create_index("member_userId_idx", "member", ["user_id"], schema=AUTH)

    op.create_table(
        "invitation",
        sa.Column("id", sa.Uuid(), nullable=False, server_default=uuid_default, primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("expires_at", ts, nullable=False),
        sa.Column("created_at", ts, nullable=False, server_default=sa.text("now()")),
        sa.Column("inviter_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["auth.organization.id"], ondelete="CASCADE", name="invitation_organization_id_fkey"),
        sa.ForeignKeyConstraint(["inviter_id"], ["auth.user.id"], ondelete="CASCADE", name="invitation_inviter_id_fkey"),
        schema=AUTH,
    )
    op.create_index("invitation_organizationId_idx", "invitation", ["organization_id"], schema=AUTH)
    op.create_index("invitation_email_idx", "invitation", ["email"], schema=AUTH)


def downgrade() -> None:
    op.drop_table("invitation", schema=AUTH)
    op.drop_table("member", schema=AUTH)
    op.drop_table("organization", schema=AUTH)
    op.drop_table("verification", schema=AUTH)
    op.drop_table("account", schema=AUTH)
    op.drop_table("session", schema=AUTH)
    op.drop_table("user", schema=AUTH)
    op.execute(f'DROP SCHEMA IF EXISTS "{AUTH}"')
