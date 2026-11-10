# -*- coding: utf-8 -*-
"""T2: downgrade 到 32f34131a28a 后的 T1 保留断言（R50-2）。

断言四要素：
  - current revision = 32f34131a28a（T1 baseline）
  - app schema enum 数量 = 0（T2 已回退）
  - btree_gist 扩展存在（T1 G1 保留）
  - T1 owner mark = created_by_migration_32f34131a28a（T1 所有权标记保留）
用法：python scripts/assert_enums_t1_retained.py（需 DATABASE_URL）
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
        enums = c.execute(text(
            "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
            "WHERE n.nspname='app' AND t.typtype='e'"
        )).scalar()
        ext = c.execute(text("SELECT count(*) FROM pg_extension WHERE extname='btree_gist'")).scalar()
        mark = c.execute(text(
            "SELECT obj_description(oid,'pg_extension') FROM pg_extension WHERE extname='btree_gist'"
        )).scalar()
        check("revision = 32f34131a28a（T1 baseline 保留）", rev == "32f34131a28a", str(rev))
        check("app enum = 0（T2 已回退）", enums == 0, str(enums))
        check("btree_gist 存在（T1 G1 保留）", ext == 1, str(ext))
        check("T1 owner mark 保留", mark == "created_by_migration_32f34131a28a", str(mark))
except Exception as exc:  # noqa: BLE001
    check("连接失败（URL 非法/不可达）", False, f"{type(exc).__name__}: {exc}")

print("ENUM-T1-RETAINED:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
