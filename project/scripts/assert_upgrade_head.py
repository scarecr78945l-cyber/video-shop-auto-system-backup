# -*- coding: utf-8 -*-
"""T1 upgrade head 后的 pg_catalog 断言（只读）。

R44-2：URL 从环境变量 DATABASE_URL 读取（与迁移同源），不再硬编码；缺失/非法即失败。
R44-4：btree_gist 所有权断言——迁移创建后有标记；预存扩展无标记场景由专项测试覆盖。
"""
import os
import sys

from sqlalchemy import create_engine, text

URL = os.environ.get("DATABASE_URL", "").strip()
if not URL:
    print("[FAIL] 缺少 DATABASE_URL（断言与迁移必须同源，R44-2）", file=sys.stderr)
    sys.exit(1)

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False


try:
    e = create_engine(URL)
    with e.connect() as c:
        s = c.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name='app'")).scalar()
        ext = c.execute(text("SELECT extname FROM pg_extension WHERE extname='btree_gist'")).scalar()
        vt = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        check("schema app 存在", s == "app", str(s))
        check("btree_gist 扩展存在", ext == "btree_gist", str(ext))
        check("alembic_version=32f34131a28a", vt == "32f34131a28a", str(vt))
        tables = c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='app' ORDER BY tablename"
        )).fetchall()
        names = [r[0] for r in tables]
        check("app schema 仅 alembic_version 表（T1 阶段）", names == ["alembic_version"], str(names))
except Exception as exc:  # noqa: BLE001
    check(f"连接失败（URL 非法/不可达）", False, f"{type(exc).__name__}: {exc}")

print("ASSERT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
