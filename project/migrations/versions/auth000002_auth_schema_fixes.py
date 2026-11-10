"""T7: auth schema 修正 revision（round-93 R92-3/R92-4）

Revision ID: auth000002
Revises: auth000001
Create Date: 2026-09-06T12:00:00+00:00

依据 round-92 终验（R92-3/R92-4）：
- R92-4：session.updated_at / account.updated_at 现库多出 now() 默认值（snapshot 仅有运行时 $onUpdate，
  无 DB 默认）；本修正移除这两个额外 server_default，恢复 snapshot 语义
  （updated_at 由 better-auth 运行时写入，DB 不设默认）；
- R92-3：member 增加 (organization_id, user_id) 唯一约束——相对 snapshot 的显式差异，
  防止同一成员多行歧义与并发重复写入（round-92 §B 要求唯一性机制）；
- timestamptz 保持（round-91 已披露的映射决策；运行时 adapter 实测见 round-93 交付）。

downgrade：恢复 updated_at 默认值、删除 member 唯一约束。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'auth000002'
down_revision: Union[str, Sequence[str], None] = 'auth000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH = "auth"


def upgrade() -> None:
    # R92-4：移除 session/account.updated_at 的额外默认值（snapshot 无 DB 默认）
    op.alter_column("session", "updated_at", server_default=None, schema=AUTH)
    op.alter_column("account", "updated_at", server_default=None, schema=AUTH)
    # R92-3：member (organization_id, user_id) 唯一约束（相对 snapshot 显式差异）
    op.create_unique_constraint(
        "member_organization_id_user_id_uidx", "member",
        ["organization_id", "user_id"], schema=AUTH,
    )


def downgrade() -> None:
    op.drop_constraint("member_organization_id_user_id_uidx", "member",
                       type_="unique", schema=AUTH)
    op.alter_column("session", "updated_at", server_default=sa.text("now()"), schema=AUTH)
    op.alter_column("account", "updated_at", server_default=sa.text("now()"), schema=AUTH)
