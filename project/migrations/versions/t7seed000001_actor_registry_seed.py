"""T7: actor_registry 种子（system/worker/service，round-81；round-83 R82-4 聚焦回修）

Revision ID: t7seed000001
Revises: 17trg000001
Create Date: 2026-09-05T09:00:00+00:00

依据：auth-boundary.md §五（actor_registry 只登记 system/worker/service，含 stable UUID）；
15-数据字典.md v6 §6.8 actor_registry（actor_id uuid UNIQUE / actor_kind / name / status）。
UUID 生成策略：uuid5(namespace=固定业务 namespace a0d983f5-2f48-59d5-bf52-becf33d6a669,
name='system'|'worker'|'service')——稳定、namespace 互斥、可复现（auth-boundary §四）。

round-83 回修（Codex round-82 R82-4）：
- upgrade 不再用 ON CONFLICT DO NOTHING 静默放行；三个种子 actor_id 属本迁移所有权——
  若目标 actor_id 已存在（同值或异值），拒绝预存并 RAISE 终止迁移（整体回滚，零副作用）；
- downgrade 只删除本迁移创建的三行（无预存时所有权清晰；预存被 upgrade 拒绝，不存在误删）；
- 无预存 / 同值预存 / 异值预存三类场景测试见 backend/tests/test_auth_seed.py。
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 't7seed000001'
down_revision: Union[str, Sequence[str], None] = '17trg000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA = 'app'

ACTOR_SEEDS = [
    # (actor_id, actor_kind, name, status)
    ('699f543a-2540-5127-913e-8cca0148db9b', 'system', 'system', 'active'),
    ('a9a79363-609b-5848-a4b3-33982797cfb8', 'worker', 'worker', 'active'),
    ('e57a6a59-da1d-5628-baef-e3b78f12f9e5', 'service', 'service', 'active'),
]


def upgrade() -> None:
    """种子所有权：目标 actor_id 已存在 -> 拒绝预存并终止迁移（整体回滚）。"""
    for actor_id, kind, name, status in ACTOR_SEEDS:
        exists = op.get_bind().execute(
            text(f"SELECT 1 FROM {SCHEMA}.actor_registry WHERE actor_id = '{actor_id}'::uuid")
        ).first()
        if exists is not None:
            raise RuntimeError(
                f"actor_registry 种子冲突（R82-4 拒绝预存）: actor_id={actor_id} 已存在；"
                "迁移所有权归 Alembic，请先清理预存记录后重跑"
            )
        op.execute(
            f"""
INSERT INTO {SCHEMA}.actor_registry (actor_id, actor_kind, name, status)
VALUES ('{actor_id}'::uuid, '{kind}', '{name}', '{status}')
"""
        )


def downgrade() -> None:
    """只删除本迁移创建的三行（upgrade 已拒绝预存，所有权无歧义）。"""
    for actor_id, _kind, _name, _status in ACTOR_SEEDS:
        op.execute(f"DELETE FROM {SCHEMA}.actor_registry WHERE actor_id = '{actor_id}'::uuid")
