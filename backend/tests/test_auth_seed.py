# -*- coding: utf-8 -*-
"""T7: 种子 migration 所有权验收（round-83 R82-4）。

覆盖 Codex round-82 R82-4 三类场景：
- 无预存：upgrade 插入 3 行 -> downgrade 删除 3 行（正常往返）；
- 同值预存：目标 actor_id 已存在且内容与种子一致 -> **拒绝预存**（upgrade 终止，整体回滚）；
- 异值预存：目标 actor_id 已存在且内容不同 -> **拒绝预存**（upgrade 终止，整体回滚）；
- 核对失败零副作用：回滚后预存行保留、种子未插入、head 不变。

所有权策略（R82-4 允许的「拒绝预存」分支）：
- 三个种子 actor_id 归本迁移所有；upgrade 遇任何预存（同值或异值）即终止迁移；
- downgrade 只删除本迁移创建的行（无预存时所有权无歧义）。

运行：cd project && python -m pytest ../backend/tests/test_auth_seed.py -q --basetemp=.pytest-tmp-t7seed
"""
import os
import sys
import uuid
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[2]  # 工作区根
PROJECT = WORKSPACE / "project"                   # project/（migration 位置）
sys.path.insert(0, str(PROJECT))

DB_URL = os.environ.get("DATABASE_URL", "").strip()
SEED_SYSTEM = "699f543a-2540-5127-913e-8cca0148db9b"
SEED_WORKER = "a9a79363-609b-5848-a4b3-33982797cfb8"
SEED_SERVICE = "e57a6a59-da1d-5628-baef-e3b78f12f9e5"


@pytest.fixture()
def conn():
    if not DB_URL:
        pytest.skip("无 DATABASE_URL，跳过真实 PG 验收")
    from sqlalchemy import create_engine

    eng = create_engine(DB_URL)
    c = eng.connect()
    tx = c.begin()
    try:
        yield c
    finally:
        tx.rollback()
        c.close()
        eng.dispose()


def _load_seed_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "t7seed", str(PROJECT / "migrations/versions/t7seed000001_actor_registry_seed.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(conn, actor_id):
    from sqlalchemy import text as sqltext

    return conn.execute(sqltext(
        "SELECT actor_id, actor_kind, name, status FROM app.actor_registry WHERE actor_id=:a"),
        {"a": actor_id}).first()


def _apply_upgrade(conn, mod):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()


def _apply_downgrade(conn, mod):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with Operations.context(MigrationContext.configure(conn)):
        mod.downgrade()


def test_seed_no_preexisting_roundtrip(conn):
    """无预存：upgrade 插入 3 行 -> downgrade 删除 3 行。"""
    from sqlalchemy import text as sqltext

    mod = _load_seed_module()
    # 清掉 DB 中既有种子（若 head 已在 t7seed000001）
    for aid in (SEED_SYSTEM, SEED_WORKER, SEED_SERVICE):
        conn.execute(sqltext("DELETE FROM app.actor_registry WHERE actor_id=:a"), {"a": aid})
    _apply_upgrade(conn, mod)
    assert _row(conn, SEED_SYSTEM) is not None
    assert _row(conn, SEED_WORKER) is not None
    assert _row(conn, SEED_SERVICE) is not None
    _apply_downgrade(conn, mod)
    assert _row(conn, SEED_SYSTEM) is None
    assert _row(conn, SEED_WORKER) is None
    assert _row(conn, SEED_SERVICE) is None
    # 恢复 3 行（保持 DB 在交付 head 状态）
    _apply_upgrade(conn, mod)
    assert _row(conn, SEED_SYSTEM) is not None


def test_seed_same_value_preexisting_rejected(conn):
    """同值预存：upgrade 拒绝预存（所有权归迁移），整体回滚零副作用。"""
    from sqlalchemy import text as sqltext

    mod = _load_seed_module()
    # 预存与种子同值行
    conn.execute(sqltext(
        "DELETE FROM app.actor_registry WHERE actor_id=:a"), {"a": SEED_SYSTEM})
    conn.execute(sqltext(
        "INSERT INTO app.actor_registry (actor_id, actor_kind, name, status) "
        "VALUES (:a, 'system', 'system', 'active')"), {"a": SEED_SYSTEM})
    with pytest.raises(RuntimeError):
        _apply_upgrade(conn, mod)
    # 回滚后预存行保留（未删）
    assert _row(conn, SEED_SYSTEM) is not None


def test_seed_diff_value_preexisting_rejected(conn):
    """异值预存：upgrade 拒绝预存并终止迁移，预存行保留。"""
    from sqlalchemy import text as sqltext

    mod = _load_seed_module()
    conn.execute(sqltext(
        "DELETE FROM app.actor_registry WHERE actor_id=:a"), {"a": SEED_SYSTEM})
    conn.execute(sqltext(
        "INSERT INTO app.actor_registry (actor_id, actor_kind, name, status) "
        "VALUES (:a, 'service', 'PREEXISTING', 'disabled')"), {"a": SEED_SYSTEM})
    with pytest.raises(RuntimeError):
        _apply_upgrade(conn, mod)
    row = _row(conn, SEED_SYSTEM)
    assert row is not None
    assert tuple(row[1:]) == ("service", "PREEXISTING", "disabled")  # 内容未被覆盖


def test_seed_conflict_fail_closed_zero_side_effect(conn):
    """异值预存拒绝后：种子未插入、预存保留、其他种子行不受影响。"""
    from sqlalchemy import text as sqltext

    mod = _load_seed_module()
    for aid in (SEED_SYSTEM, SEED_WORKER, SEED_SERVICE):
        conn.execute(sqltext("DELETE FROM app.actor_registry WHERE actor_id=:a"), {"a": aid})
    conn.execute(sqltext(
        "INSERT INTO app.actor_registry (actor_id, actor_kind, name, status) "
        "VALUES (:a, 'service', 'PREEXISTING', 'disabled')"), {"a": SEED_SYSTEM})
    with pytest.raises(RuntimeError):
        _apply_upgrade(conn, mod)
    # 整个迁移事务回滚：预存保留、种子行未插入
    assert _row(conn, SEED_SYSTEM) is not None
    assert _row(conn, SEED_WORKER) is None
    assert _row(conn, SEED_SERVICE) is None
