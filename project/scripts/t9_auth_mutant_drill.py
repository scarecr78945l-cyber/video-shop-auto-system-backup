# -*- coding: utf-8 -*-
"""T9 R122-1: auth 门禁变异演练（round-123）。

依据 round-122-cdx-P0-1-T9聚焦复核.md R122-1：auth FK action（ON DELETE）必须逐项校验——
对共享基线库的 account_user_id_fkey 展示"定义即校验"：

  1. 独立临时库 upgrade head（auth 冻结 expected：7 表列/PK/UNIQUE/FK exact-set）；
  2. 无变异基线：assert_t9_catalog RN=0（auth FK exact-set PASS）；
  3. 应用真实负例变异：DROP account_user_id_fkey + 重建同名列 ON DELETE SET NULL
     （CASCADE->SET NULL）——assert_t9_catalog 必须 FAIL（RC=1，auth FK 逐项 action 被捕获）；
  4. 还原为 CASCADE 后 assert 回归 PASS（RC=0）；
  5. 清理独立临时库；共享基线库 dsh_test 全程不触碰（结构/数据不变）。

用法（PowerShell，环境同迁移）：
  $env:DATABASE_URL="postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test"
  $env:MIGRATION_ROLE="dsh_migrator"
  python project/scripts/t9_auth_mutant_drill.py
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"

ADMIN_URL = os.environ.get("T9_ADMIN_URL", "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/postgres")


def run(cmd, env=None, allow_fail=False):
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    if env:
        e.update(env)
    r = subprocess.run(cmd, cwd=str(PROJECT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, timeout=600)
    if not allow_fail and r.returncode != 0:
        print(f"[FAIL] cmd={' '.join(cmd)} rc={r.returncode}")
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        sys.exit(1)
    return r


def admin_sql(sql: str) -> None:
    from sqlalchemy import create_engine, text
    e = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with e.connect() as c:
        c.execute(text(sql))
    e.dispose()


def apply_mutant(temp_url):
    from sqlalchemy import create_engine, text
    e = create_engine(temp_url)
    with e.begin() as c:
        c.execute(text("ALTER TABLE auth.account DROP CONSTRAINT account_user_id_fkey"))
        c.execute(text("ALTER TABLE auth.account ADD CONSTRAINT account_user_id_fkey "
                       "FOREIGN KEY (user_id) REFERENCES auth.\"user\"(id) ON DELETE SET NULL"))
    e.dispose()


def main():
    base = os.environ.get("DATABASE_URL", "").strip()
    if not base:
        print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    dbname = "dsh_test_authm_" + uuid.uuid4().hex[:8]
    temp_url = base.rsplit("/", 1)[0] + "/" + dbname
    print(f"[TEMP_DB] {dbname}（auth 变异演练独立临时库；共享基线 {base.rsplit('/', 1)[-1]} 不触碰）")
    created = False
    try:
        admin_sql(f"CREATE DATABASE {dbname}")
        created = True
        admin_sql(f"ALTER DATABASE {dbname} OWNER TO dsh_migrator")
        env = {"DATABASE_URL": temp_url, "MIGRATION_ROLE": "dsh_migrator"}
        run(["python", "-m", "alembic", "upgrade", "head"], env=env)
        print("[STEP1] upgrade head OK")

        # STEP2: 无变异基线 RC=0
        r0 = run(["python", "scripts/assert_t9_catalog.py"], env=env, allow_fail=True)
        ok0 = r0.returncode == 0 and "T9-CATALOG-ASSERT: PASS" in r0.stdout
        print("[STEP2] 基线 assert_t9_catalog ", "PASS" if ok0 else "FAIL", f"rc={r0.returncode}")
        if not ok0:
            raise SystemExit("STEP2 基线未通过")

        # STEP3: 应用 FK action 变异（CASCADE->SET NULL）-> 必须 FAIL
        apply_mutant(temp_url)
        r1 = run(["python", "scripts/assert_t9_catalog.py"], env=env, allow_fail=True)
        neg_ok = r1.returncode != 0 and "auth FK" in r1.stdout and "SET NULL" in r1.stdout
        print("[STEP3] 变异 account_user_id_fkey=ON DELETE SET NULL 被捕获 ->",
              "PASS" if neg_ok else "FAIL", f"rc={r1.returncode}")
        print(r1.stdout[-1600:] if not neg_ok else "")
        if not neg_ok:
            raise SystemExit("STEP3 变异未被捕获")

        # STEP4: 还原 CASCADE -> 回归 PASS
        admin_sql(f"ALTER DATABASE {dbname} OWNER TO dsh")
        from sqlalchemy import create_engine, text
        e = create_engine(temp_url)
        with e.begin() as c:
            c.execute(text("ALTER TABLE auth.account DROP CONSTRAINT account_user_id_fkey"))
            c.execute(text("ALTER TABLE auth.account ADD CONSTRAINT account_user_id_fkey "
                           "FOREIGN KEY (user_id) REFERENCES auth.\"user\"(id) ON DELETE CASCADE"))
        e.dispose()
        r2 = run(["python", "scripts/assert_t9_catalog.py"], env=env, allow_fail=True)
        ok2 = r2.returncode == 0 and "T9-CATALOG-ASSERT: PASS" in r2.stdout
        print("[STEP4] 还原 CASCADE 回归 ", "PASS" if ok2 else "FAIL", f"rc={r2.returncode}")
        if not ok2:
            raise SystemExit("STEP4 回归未通过")
        print("T9_AUTH_MUTANT_DRILL=PASS")
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