# -*- coding: utf-8 -*-
"""T1 downgrade base 后的空库断言（只读）。

R44-2：URL 从 DATABASE_URL 读取（同源）；R44-4：预存扩展保留、迁移创建可删两条路径由专项测试覆盖。
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
        # 三类对象分开统计（auth-boundary 契约）：业务表=排除 alembic_version 元数据
        biz_tables = c.execute(text(
            "SELECT count(*) FROM pg_tables WHERE schemaname='app' AND tablename <> 'alembic_version'"
        )).scalar()
        app_tables_all = c.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname='app'")).scalar()
        check("业务表=0（排除 alembic_version 元数据）", biz_tables == 0, f"biz={biz_tables}, all={app_tables_all}")
        check("app 仅剩 alembic_version 元数据（<=1）", app_tables_all <= 1, str(app_tables_all))
        # R44-4：默认场景（迁移创建后 downgrade）应删除扩展；预存场景专项覆盖
        ext = c.execute(text("SELECT count(*) FROM pg_extension WHERE extname='btree_gist'")).scalar()
        check("btree_gist 默认已删除（迁移创建场景）", ext == 0, str(ext))
except Exception as exc:  # noqa: BLE001
    check("连接失败（URL 非法/不可达）", False, f"{type(exc).__name__}: {exc}")

print("EMPTY-ASSERT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
