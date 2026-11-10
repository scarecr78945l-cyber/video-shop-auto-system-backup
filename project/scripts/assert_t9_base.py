# -*- coding: utf-8 -*-
"""T9: base（downgrade 后）空库精确断言（round-115 R114-1 定稿）。

  - app 仅 alembic_version 元数据表；
  - **auth 业务表 = 0**；
  - enum = 0 / user trigger = 0；
  - **索引白名单按真实元数据 PK 身份核对**（pg_constraint contype='p' 且属 alembic_version）——
    拒绝"非 PK 前缀命名"伪装索引（R114-1：alembic_version_pk_fake 变异必须失败）；
  - **扩展所有权**：迁移创建路径（comment='created_by_migration_*'）downgrade 后必须删除——
    残留即失败（R114-1：BASE_MIGRATION_OWNED_EXTENSION_LEFTOVER 变异必须失败）；
    预存路径（无迁移标记）保留（由 test_extension_ownership.py 专项覆盖）。
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
    e = create_engine(URL)
    with e.connect() as c:
        app_tables = c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='app' ORDER BY tablename")).all()
        check("app 仅 alembic_version 元数据", [r[0] for r in app_tables] == ["alembic_version"],
              f"got={[r[0] for r in app_tables]}")
        auth_tables = c.execute(text(
            "SELECT count(*) FROM pg_tables WHERE schemaname='auth'")).scalar()
        check("auth 业务表 = 0", int(auth_tables) == 0, f"got {auth_tables}")
        enums = c.execute(text(
            "SELECT count(DISTINCT t.typname) FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid "
            "JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='app'")).scalar()
        check("app enum = 0", int(enums) == 0, f"got {enums}")
        triggers = c.execute(text(
            "SELECT count(*) FROM pg_trigger t JOIN pg_class x ON x.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=x.relnamespace "
            "WHERE n.nspname='app' AND NOT t.tgisinternal")).scalar()
        check("app user trigger = 0", int(triggers) == 0, f"got {triggers}")
        # 真实元数据 PK 身份（R114-1）：app 仅允许 alembic_version 的 PK
        pk_rows = c.execute(text(
            "SELECT con.conname, x.relname FROM pg_constraint con "
            "JOIN pg_class x ON x.oid=con.conrelid "
            "JOIN pg_namespace n ON n.oid=x.relnamespace "
            "WHERE n.nspname='app' AND con.contype='p'")).all()
        check("app PK 仅 alembic_version（身份核对）",
              len(pk_rows) == 1 and pk_rows[0][1] == "alembic_version",
              f"got={[tuple(r) for r in pk_rows]}")
        # 索引精确白名单：仅 alembic_version PK 关联索引（拒绝前缀伪装）
        idx = c.execute(text(
            "SELECT i.indexname, i.tablename FROM pg_indexes i WHERE schemaname='app' "
            "ORDER BY i.indexname")).all()
        allowed = len(idx) == 1 and idx[0][1] == "alembic_version" and \
            idx[0][0] in ("alembic_version_pkey", "alembic_version_pkc")
        check("app 索引仅 alembic_version PK 白名单（拒绝伪装）", allowed,
              f"got={[tuple(r) for r in idx]}")
        # 扩展所有权（R114-1）：迁移创建路径（comment 标记）残留即失败
        ext_rows = c.execute(text(
            "SELECT extname, obj_description(oid,'pg_extension') "
            "FROM pg_extension WHERE extname='btree_gist'")).all()
        migration_owned = ext_rows and ext_rows[0][1] and \
            "created_by_migration" in (ext_rows[0][1] or "")
        check("迁移创建扩展已删除（downgrade 契约）", not migration_owned,
              f"got={[tuple(r) for r in ext_rows]}")
except Exception as exc:  # noqa: BLE001
    check("连接失败", False, f"{type(exc).__name__}: {exc}")

print("T9-BASE-ASSERT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
