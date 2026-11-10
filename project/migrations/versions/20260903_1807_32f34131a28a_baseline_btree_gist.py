"""baseline: G1 btree_gist extension（round-45 R44-4 回修）

Revision ID: 32f34131a28a
Revises:
Create Date: 2026-09-03 18:07:20.907042

ddl-order.md 契约：
- G1: CREATE EXTENSION IF NOT EXISTS btree_gist
- downgrade 边界：仅当本 migration 确认创建且无外部依赖时删除；预存扩展默认保留。
- R44-4：用 COMMENT 记录创建所有权；downgrade 检查标记——有标记才删（迁移创建），无标记保留（预存）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "32f34131a28a"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OWNER_MARK = "created_by_migration_32f34131a28a"


def _ext_comment(bind) -> str | None:
    """读 btree_gist 扩展的 COMMENT（无扩展/无注释返回 None）。"""
    return bind.execute(
        sa.text(
            "SELECT obj_description(oid, 'pg_extension') "
            "FROM pg_extension WHERE extname = 'btree_gist'"
        )
    ).scalar()


def upgrade() -> None:
    """G1: btree_gist 扩展；记录创建所有权标记（R44-4）。"""
    bind = op.get_bind()
    existed = bind.execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname='btree_gist'")
    ).scalar()
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    if not existed:
        # 本次迁移创建：打所有权标记
        op.execute(sa.text("COMMENT ON EXTENSION btree_gist IS :mark").bindparams(mark=_OWNER_MARK))


def downgrade() -> None:
    """按 ddl-order §八 + R44-4：仅当本 migration 创建（有标记）且无 CASCADE 时删除；预存扩展保留。"""
    bind = op.get_bind()
    comment = _ext_comment(bind)
    if comment == _OWNER_MARK:
        op.execute("DROP EXTENSION IF EXISTS btree_gist")
    # 无标记 = 迁移前预存扩展：保留，不删除
