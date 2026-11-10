# -*- coding: utf-8 -*-
"""T3: T3 单包回退后的状态断言（只回退 31tbl000001，保留 T1/T2）。

断言（对应 round-52 R50-2 原则 + T3 单包 downgrade）：
  - current revision = 60enum000000（T2 保留）
  - app 业务表 = 0（31 表已回退；alembic_version 元数据除外）
  - app enum = 60（T2 保留）
  - btree_gist 存在 + T1 owner mark 保留
用法：python scripts/assert_t3_rolled_back.py（需 DATABASE_URL）
"""
import os
import sys

from sqlalchemy import create_engine, text

URL = os.environ.get("DATABASE_URL", "").strip()
if not URL:
    print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
    sys.exit(1)

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


try:
    with create_engine(URL).connect() as c:
        rev = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        tables = c.execute(text(
            "SELECT count(*) FROM pg_tables WHERE schemaname='app' AND tablename <> 'alembic_version'"
        )).scalar()
        enums = c.execute(text(
            "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
            "WHERE n.nspname='app' AND t.typtype='e'"
        )).scalar()
        ext = c.execute(text("SELECT count(*) FROM pg_extension WHERE extname='btree_gist'")).scalar()
        mark = c.execute(text(
            "SELECT obj_description(oid,'pg_extension') FROM pg_extension WHERE extname='btree_gist'"
        )).scalar()
        check("revision = 60enum000000（T2 保留）", rev == "60enum000000", str(rev))
        check("app 业务表 = 0（T3 已回退）", tables == 0, str(tables))
        check("app enum = 60（T2 保留）", enums == 60, str(enums))
        check("btree_gist 存在（T1 保留）", ext == 1, str(ext))
        check("T1 owner mark 保留", mark == "created_by_migration_32f34131a28a", str(mark))
except Exception as exc:  # noqa: BLE001
    check("连接失败（URL 非法/不可达）", False, f"{type(exc).__name__}: {exc}")

print("T3-ROLLED-BACK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)