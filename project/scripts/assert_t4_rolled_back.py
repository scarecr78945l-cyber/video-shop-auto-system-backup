# -*- coding: utf-8 -*-
"""T4: T4 单包回退后的状态断言（只回退 17trg000001，保留 T1~T3）。

断言：
  - current revision = 31tbl000001（T3 保留）
  - app user trigger = 0（T4 已回退）
  - app fn_% 函数 = 0（T4 函数已回退）
  - app 业务表 = 31（T3 保留）；enum = 60（T2 保留）；btree_gist 存在（T1 保留）
用法：python scripts/assert_t4_rolled_back.py（需 DATABASE_URL）
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
        trg = c.execute(text(
            "SELECT count(*) FROM pg_trigger t JOIN pg_class cr ON cr.oid=t.tgrelid "
            "JOIN pg_namespace ns ON ns.oid=cr.relnamespace "
            "WHERE ns.nspname='app' AND NOT t.tgisinternal"
        )).scalar()
        fns = c.execute(text(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='app' AND p.proname LIKE 'fn\\_%'"
        )).scalar()
        tables = c.execute(text(
            "SELECT count(*) FROM pg_tables WHERE schemaname='app' AND tablename <> 'alembic_version'"
        )).scalar()
        enums = c.execute(text(
            "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
            "WHERE n.nspname='app' AND t.typtype='e'"
        )).scalar()
        ext = c.execute(text("SELECT count(*) FROM pg_extension WHERE extname='btree_gist'")).scalar()
        check("revision = 31tbl000001（T3 保留）", rev == "31tbl000001", str(rev))
        check("app user trigger = 0（T4 已回退）", trg == 0, str(trg))
        check("app fn_% 函数 = 0（T4 已回退）", fns == 0, str(fns))
        check("app 业务表 = 31（T3 保留）", tables == 31, str(tables))
        check("app enum = 60（T2 保留）", enums == 60, str(enums))
        check("btree_gist 存在（T1 保留）", ext == 1, str(ext))
except Exception as exc:  # noqa: BLE001
    check("连接失败", False, f"{type(exc).__name__}: {exc}")

print("T4-ROLLED-BACK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)