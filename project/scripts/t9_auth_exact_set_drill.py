# -*- coding: utf-8 -*-
"""T9 R124-1: auth exact-set 集合闭包变异演练（round-125）。

依据 round-124-cdx-P0-1-T9聚焦终验.md R124-1：`assert_t9_catalog.py` 的 auth 检查此前只做
「期望项存在且定义相同」，未做集合闭包，故额外列/额外唯一索引/额外 FK 均漏报 RC=0。本演练在
独立临时库对三类额外对象逐一施加变异，断言各自 **RC=1**，逐项还原后断言 baseline **RC=0**，
finally 删除临时库；并保留既有 FK action 变异（account_user_id_fkey CASCADE->SET NULL）。

变异（与 CDX round-124/126 探针对齐，不改动迁移/业务实现）：
  1. EXTRA_COLUMN       : ALTER TABLE auth."user" ADD COLUMN cdx_extra text;
  2. EXTRA_UNIQUE_INDEX : CREATE UNIQUE INDEX cdx_extra_user_name_uidx ON auth."user" (name);
  3. PARTIAL_UNIQUE_INDEX: CREATE UNIQUE INDEX cdx_partial_user_email_uidx ON auth."user" (email)
                           WHERE status='active'（带谓词唯一索引必须进拒绝路径）；
  4. EXTRA_FOREIGN_KEY  : ALTER TABLE auth.account ADD CONSTRAINT cdx_extra_account_user_fk
                          FOREIGN KEY (user_id) REFERENCES auth."user" (id) ON DELETE CASCADE;
  5. FK_ACTION_SET_NULL : account_user_id_fkey CASCADE -> SET NULL（round-123 R122-1 保留）
  6. FK_CROSS_TABLE_SAME_NAME（round-127 R126-1）：先删 session_user_id_fkey，在 auth.account
     加同名约束，再在 auth.session 重建同名——同一约束名跨表合法，必须以 (child_table,conname)
     复合键拒绝额外；断言 FK 总数=7、同名行=2，catalog RC=1，还原后 RC=0。

用法（PowerShell，环境同迁移）：
  $env:DATABASE_URL="postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test"
  $env:MIGRATION_ROLE="dsh_migrator"
  python project/scripts/t9_auth_exact_set_drill.py
"""
import os
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text

ADMIN_URL = os.environ.get("T9_ADMIN_URL", "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/postgres")


def run(cmd, env=None, allow_fail=False, cwd=None):
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    if env:
        e.update(env)
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, timeout=600, cwd=cwd)
    if not allow_fail and r.returncode != 0:
        print(f"[FAIL] cmd={' '.join(cmd)} rc={r.returncode}")
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        sys.exit(1)
    return r


def admin_sql(sql: str) -> None:
    e = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with e.connect() as c:
        c.execute(text(sql))
    e.dispose()


def sql(temp_url, stmt):
    e = create_engine(temp_url)
    with e.begin() as c:
        c.execute(text(stmt))
    e.dispose()


def main():
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    PROJECT = ROOT / "project"
    base = os.environ.get("DATABASE_URL", "").strip()
    if not base:
        print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    dbname = "dsh_test_exct_" + uuid.uuid4().hex[:8]
    temp_url = base.rsplit("/", 1)[0] + "/" + dbname
    print(f"[TEMP_DB] {dbname}（auth exact-set 集合闭包演练；共享基线不触碰）")
    created = False
    try:
        admin_sql(f"CREATE DATABASE {dbname}")
        created = True
        admin_sql(f"ALTER DATABASE {dbname} OWNER TO dsh_migrator")
        env = {"DATABASE_URL": temp_url, "MIGRATION_ROLE": "dsh_migrator"}
        run(["python", "-m", "alembic", "upgrade", "head"], env=env, cwd=str(PROJECT))

        def cat_rc():
            return run(["python", "scripts/assert_t9_catalog.py"], env=env,
                       cwd=str(PROJECT), allow_fail=True).returncode

        rc0 = cat_rc()
        assert rc0 == 0 and "T9-CATALOG-ASSERT: PASS" in \
            run(["python", "scripts/assert_t9_catalog.py"], env=env,
                cwd=str(PROJECT), allow_fail=True).stdout, "基线应 PASS"
        print("[STEP0] 基线 assert_t9_catalog RC=0 PASS")

        mutants = [
            ("EXTRA_COLUMN",
             "ALTER TABLE auth.\"user\" ADD COLUMN cdx_extra text;", None),
            ("EXTRA_UNIQUE_INDEX",
             "CREATE UNIQUE INDEX cdx_extra_user_name_uidx ON auth.\"user\" (name);", None),
            ("PARTIAL_UNIQUE_INDEX",
             "CREATE UNIQUE INDEX cdx_partial_user_email_uidx ON auth.\"user\" (email) "
             "WHERE status='active';", None),
            ("EXTRA_FOREIGN_KEY",
             "ALTER TABLE auth.account ADD CONSTRAINT cdx_extra_account_user_fk "
             "FOREIGN KEY (user_id) REFERENCES auth.\"user\" (id) ON DELETE CASCADE;", None),
            ("FK_ACTION_SET_NULL",
             "ALTER TABLE auth.account DROP CONSTRAINT account_user_id_fkey; "
             "ALTER TABLE auth.account ADD CONSTRAINT account_user_id_fkey "
             "FOREIGN KEY (user_id) REFERENCES auth.\"user\" (id) ON DELETE SET NULL;", None),
            ("FK_CROSS_TABLE_SAME_NAME",
             "ALTER TABLE auth.session DROP CONSTRAINT session_user_id_fkey; "
             "ALTER TABLE auth.account ADD CONSTRAINT session_user_id_fkey "
             "FOREIGN KEY (user_id) REFERENCES auth.\"user\" (id) ON DELETE CASCADE; "
             "ALTER TABLE auth.session ADD CONSTRAINT session_user_id_fkey "
             "FOREIGN KEY (user_id) REFERENCES auth.\"user\" (id) ON DELETE CASCADE;", None),
        ]
        for name, ddl, _restore in mutants:
            sql(temp_url, ddl)
            if name == "FK_CROSS_TABLE_SAME_NAME":
                # 断言：跨表同一约束名确实产生 7 FK / 2 同名行（而非被覆盖）
                r = run(["python", "-c",
                         "from sqlalchemy import create_engine,text;"
                         "import os;"
                         "e=create_engine(os.environ['DATABASE_URL']);c=e.connect();"
                         "n=c.execute(text(\"SELECT count(*) FROM pg_constraint con JOIN pg_class x "
                         "ON x.oid=con.conrelid JOIN pg_namespace ns ON ns.oid=x.relnamespace "
                         "WHERE ns.nspname='auth' AND con.contype='f'\")).scalar();"
                         "d=c.execute(text(\"SELECT count(*) FROM pg_constraint con JOIN pg_class x "
                         "ON x.oid=con.conrelid JOIN pg_namespace ns ON ns.oid=x.relnamespace "
                         "WHERE ns.nspname='auth' AND con.contype='f' AND con.conname='session_user_id_fkey'\")).scalar();"
                         "print(f'FK_TOTAL={n} SAME_NAME={d}');"
                         "assert n==7 and d==2, f'期望 7 FK/2 同名, got {n}/{d}';"
                         "c.close();e.dispose()"],
                    env=env, cwd=str(PROJECT))
                print("[MUTANT] FK_CROSS_TABLE_SAME_NAME 结构断言: 7 FK / 2 同名 PASS")
            rc = cat_rc()
            ok = rc != 0
            print(f"[MUTANT] {name} 被捕获 ->", "PASS" if ok else "FAIL", f"rc={rc}")
            if not ok:
                raise SystemExit(f"{name} 变异未被捕获")
            admin_sql(f"ALTER DATABASE {dbname} OWNER TO dsh")  # 允许 dsh 改约束
            # 还原（对应用户为 dsh、库 owner 已转回 dsh，可直接 DDL）
            if name == "EXTRA_COLUMN":
                sql(temp_url, "ALTER TABLE auth.\"user\" DROP COLUMN cdx_extra;")
            elif name == "EXTRA_UNIQUE_INDEX":
                sql(temp_url, "DROP INDEX auth.cdx_extra_user_name_uidx;")
            elif name == "PARTIAL_UNIQUE_INDEX":
                sql(temp_url, "DROP INDEX auth.cdx_partial_user_email_uidx;")
            elif name == "EXTRA_FOREIGN_KEY":
                sql(temp_url, "ALTER TABLE auth.account DROP CONSTRAINT cdx_extra_account_user_fk;")
            elif name == "FK_ACTION_SET_NULL":
                sql(temp_url,
                    "ALTER TABLE auth.account DROP CONSTRAINT account_user_id_fkey; "
                    "ALTER TABLE auth.account ADD CONSTRAINT account_user_id_fkey "
                    "FOREIGN KEY (user_id) REFERENCES auth.\"user\" (id) ON DELETE CASCADE;")
            elif name == "FK_CROSS_TABLE_SAME_NAME":
                sql(temp_url,
                    "ALTER TABLE auth.account DROP CONSTRAINT session_user_id_fkey; "
                    "ALTER TABLE auth.session DROP CONSTRAINT session_user_id_fkey; "
                    "ALTER TABLE auth.session ADD CONSTRAINT session_user_id_fkey "
                    "FOREIGN KEY (user_id) REFERENCES auth.\"user\" (id) ON DELETE CASCADE;")
            rc_r = cat_rc()
            ok_r = rc_r == 0
            print(f"[RESTORE] {name} 还原 baseline ->", "PASS" if ok_r else "FAIL", f"rc={rc_r}")
            if not ok_r:
                raise SystemExit(f"{name} 还原后未回归")
        print("T9_AUTH_EXACT_SET_DRILL=PASS")
    finally:
        if created:
            try:
                admin_sql(f"DROP DATABASE IF EXISTS {dbname} (FORCE)")
                print(f"[CLEANUP] 临时库 {dbname} 已删除")
            except Exception as exc:  # noqa: BLE001
                print(f"[CLEANUP-FAIL] 临时库删除失败: {exc}")
                raise


if __name__ == "__main__":
    main()