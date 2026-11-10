# -*- coding: utf-8 -*-
"""T1 R44-4 专项测试：btree_gist 所有权两条路径。

路径 A（迁移创建）：upgrade 创建+标记 → downgrade 删除（默认 drill 已覆盖）
路径 B（预存扩展）：downgrade base → 手工 CREATE EXTENSION → upgrade（IF NOT EXISTS 无标记）
                  → downgrade → 扩展必须保留

用法：python scripts/test_extension_ownership.py（需 MIGRATION_ROLE/DATABASE_URL）
"""
import os
import subprocess
import sys

from sqlalchemy import create_engine, text

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
URL = os.environ.get("DATABASE_URL", "").strip()
ROLE = os.environ.get("MIGRATION_ROLE", "").strip()
if not URL or not ROLE:
    print("[FAIL] 需要 MIGRATION_ROLE 与 DATABASE_URL", file=sys.stderr)
    sys.exit(1)

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


def alembic(*args):
    r = subprocess.run([PY, "-m", "alembic"] + list(args), cwd=BASE, capture_output=True, text=True)
    if r.returncode != 0:
        print("[alembic FAIL]", args, r.stderr[-300:], file=sys.stderr)
        sys.exit(1)
    return r


def ext_comment():
    with create_engine(URL).connect() as c:
        return c.execute(text(
            "SELECT obj_description(oid,'pg_extension') FROM pg_extension "
            "WHERE extname='btree_gist'"
        )).scalar()


def ext_exists():
    with create_engine(URL).connect() as c:
        return c.execute(text("SELECT count(*) FROM pg_extension WHERE extname='btree_gist'")).scalar() == 1


# 准备：确保 base
alembic("downgrade", "base")

# ---- 路径 B：预存扩展 ----
with create_engine(URL).connect() as c:
    c.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    c.commit()
check("B 预存扩展已存在", ext_exists())
# btree_gist 扩展自带默认 COMMENT；正确口径 = 不携带迁移标记（!= _OWNER_MARK）
check("B 预存扩展不携带迁移标记", ext_comment() != "created_by_migration_32f34131a28a", str(ext_comment()))

alembic("upgrade", "head")
check("B upgrade 后扩展仍在（IF NOT EXISTS）", ext_exists())
check("B upgrade 未覆盖标记（预存保持原 COMMENT）", ext_comment() != "created_by_migration_32f34131a28a", str(ext_comment()))

alembic("downgrade", "base")
check("B downgrade 保留预存扩展（无标记）", ext_exists(), "必须保留")

# 清理路径 B 的预存模拟扩展，使后续 upgrade 进入"迁移创建"路径
with create_engine(URL).connect() as c:
    c.execute(text("DROP EXTENSION IF EXISTS btree_gist"))
    c.commit()
alembic("downgrade", "base")
alembic("upgrade", "head")  # 此时扩展不存在 → 迁移创建+标记

# ---- 路径 A 复核：迁移创建有标记，downgrade 删除 ----
check("A upgrade 后迁移创建扩展并带标记", ext_exists() and ext_comment() == "created_by_migration_32f34131a28a", str(ext_comment()))
alembic("downgrade", "base")
check("A downgrade 删除迁移创建的扩展", not ext_exists())
alembic("upgrade", "head")  # 恢复标准 head

print("OWNERSHIP-TEST:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
