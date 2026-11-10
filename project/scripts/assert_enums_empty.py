# -*- coding: utf-8 -*-
"""T2: downgrade base 后枚举空库断言（app schema enum 数量=0）。

用法：python scripts/assert_enums_empty.py（需 DATABASE_URL）
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
        enums = c.execute(text(
            "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
            "WHERE n.nspname='app' AND t.typtype='e'"
        )).scalar()
        check("app schema enum 数量=0（downgrade 后）", enums == 0, str(enums))
except Exception as exc:  # noqa: BLE001
    check("连接失败（URL 非法/不可达）", False, f"{type(exc).__name__}: {exc}")

print("ENUM-EMPTY-ASSERT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
