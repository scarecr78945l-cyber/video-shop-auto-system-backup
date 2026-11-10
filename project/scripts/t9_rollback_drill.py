# -*- coding: utf-8 -*-
"""T9: 独立临时库迁移演练 + 空库断言 + re-upgrade 回归（round-111）。

依据 test-strategy.md §二/§八（round-20 §5.4 修正）+ ddl-order.md §九 exact-set：
  1. 创建独立临时库（不触碰共享基线库 dsh_test），记录库标识/基线；
  2. 空库 upgrade head -> pg_catalog exact-set + 行为 pytest；
  3. downgrade base -> 空库断言（业务表=0/enum=0/trigger=0/索引=0）；
  4. re-upgrade head -> exact-set + 行为回归；
  5. 全程携带 mode/provider/model/source/evidence；finally 清理临时库。

用法（PowerShell，后端环境变量与迁移同源）：
  $env:DATABASE_URL="postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test"
  $env:MIGRATION_ROLE="dsh_migrator"
  python project/scripts/t9_rollback_drill.py
"""
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
BACKEND = ROOT / "backend"

EVIDENCE = {
    "mode": "migration+behavior",
    "provider": "postgres:16+docker:dsh-pg-test",
    "model": "alembic:psycopg2",
    "source": "t9_rollback_drill.py",
    "evidence": "independent-temp-db-" + uuid.uuid4().hex[:8],
}
BASE_URL = os.environ.get("DATABASE_URL", "").strip()
ADMIN_URL = os.environ.get("T9_ADMIN_URL", "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/postgres")


def run(cmd, env=None, cwd=None, allow_fail=False):
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    if env:
        e.update(env)
    r = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, timeout=600)
    if not allow_fail and r.returncode != 0:
        print(f"[FAIL] cmd={' '.join(cmd)} rc={r.returncode}")
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        sys.exit(1)
    return r


def _admin_sql(sql: str) -> None:
    """管理员连接执行 DDL（autocommit，避免 CREATE/DROP DATABASE 事务块错误）。"""
    from sqlalchemy import create_engine, text

    e = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with e.connect() as c:
        c.execute(text(sql))
    e.dispose()


def main():
    if not BASE_URL:
        print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    dbname = "dsh_test_t9_" + uuid.uuid4().hex[:8]
    temp_url = BASE_URL.rsplit("/", 1)[0] + "/" + dbname
    # R114-3：本次运行唯一 basetemp 根（所有阶段路径由同一根派生；finally 只清理本次根）
    run_root = BACKEND / f".pytest-tmp-t9-{uuid.uuid4().hex[:8]}"
    bt_up = run_root / "up"
    bt_re = run_root / "re"
    bt_up.mkdir(parents=True, exist_ok=True)
    bt_re.mkdir(parents=True, exist_ok=True)
    print(f"[EVIDENCE] {EVIDENCE}")
    print(f"[TEMP_DB] {dbname}（独立临时库，共享基线 {BASE_URL.rsplit('/', 1)[-1]} 未触碰）")
    print(f"[BASETEMP] {run_root}（本次运行独占）")
    created = False
    try:
        # 1) 创建独立临时库（R112-3：CREATE 成功即登记所有权）+ owner 授予 dsh_migrator
        #    R112-4 修正：不再"预装"扩展——dsh_migrator 作为库 owner 可建扩展（探针实测
        #    ACTUAL_EXTENSION_OWNER_MARK=('dsh_migrator','created_by_migration_...')），
        #    扩展由 baseline migration 创建（冻结契约：迁移创建才删/预存保留）；连接关闭回滚
        #    使旧"预装"实际无效，删除该路径。
        _admin_sql(f"CREATE DATABASE {dbname}")
        created = True
        _admin_sql(f"ALTER DATABASE {dbname} OWNER TO dsh_migrator")
        print("[STEP1] 独立临时库创建（owner=dsh_migrator）OK")
        env = {"DATABASE_URL": temp_url, "MIGRATION_ROLE": "dsh_migrator"}

        # 2) 空库 upgrade head
        run(["python", "-m", "alembic", "upgrade", "head"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_t9_catalog.py"], env=env, cwd=PROJECT)
        print("[STEP2] upgrade head + catalog exact-set PASS")
        # 行为 pytest（repository/trigger/fixture-e2e）——独立库
        r = run(["python", "-m", "pytest", "tests/test_cid_engine.py",
                 "tests/test_secret_store.py", "tests/test_auth_actor.py",
                 "tests/test_auth_seed.py", "tests/test_auth_integration.py",
                 "tests/test_auth_idp_chain.py", "tests/test_workflow_queue.py",
                 "-q", "--basetemp=" + str(bt_up)], env=env, cwd=BACKEND)
        print("[STEP2b] 行为 pytest PASS（独立库）")

        # 3) downgrade base + 空库精确断言（R112-1/3：assert_t9_base 失败即停止，不用 allow_fail）
        run(["python", "-m", "alembic", "downgrade", "base"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_t9_base.py"], env=env, cwd=PROJECT)
        print("[STEP3] downgrade base + 空库精确断言 PASS")
        # 附加空库断言：enum/trigger 清零（assert_t9_base 已含 auth=0/索引白名单）
        r = run(["python", "-c",
                 "from sqlalchemy import create_engine,text;"
                 "e=create_engine(__import__('os').environ['DATABASE_URL']);c=e.connect();"
                 "en=c.execute(text(\"SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid\")).scalar();"
                 "tr=c.execute(text(\"SELECT count(*) FROM pg_trigger t JOIN pg_class x ON x.oid=t.tgrelid JOIN pg_namespace n ON n.oid=x.relnamespace WHERE n.nspname='app' AND NOT t.tgisinternal\")).scalar();"
                 "print(f'EMPTY_CHECK enums={en} triggers={tr}');"
                 "assert en==0 and tr==0,'空库断言失败';"
                 "c.close();e.dispose()"], env=env, allow_fail=False)
        print("[STEP3b] 空库对象断言 PASS（app/auth 业务清零；enum/trigger=0）")

        # 4) re-upgrade head + catalog/behavior 回归
        #    R112-4 修正：downgrade 时 baseline migration DROP 了扩展（迁移创建路径），
        #    re-upgrade 由 baseline migration 重新 CREATE（owner=dsh_migrator 有权限）——无需预装。
        run(["python", "-m", "alembic", "upgrade", "head"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_t9_catalog.py"], env=env, cwd=PROJECT)
        run(["python", "-m", "pytest", "tests/test_cid_engine.py",
             "tests/test_secret_store.py", "tests/test_auth_actor.py",
             "tests/test_auth_seed.py", "tests/test_auth_integration.py",
             "tests/test_auth_idp_chain.py", "tests/test_workflow_queue.py",
             "-q", "--basetemp=" + str(bt_re)], env=env, cwd=BACKEND)
        print("[STEP4] re-upgrade head + catalog/behavior 回归 PASS")
        print("T9_ROLLBACK_DRILL=PASS")
    finally:
        # R112-3：从 CREATE 成功起所有失败路径清理本次精确库名——DROP DATABASE 最先（独立 try，
        # 文件清理失败不影响库清理）
        if created:
            try:
                _admin_sql(f"DROP DATABASE IF EXISTS {dbname} (FORCE)")
                print(f"[CLEANUP] 临时库 {dbname} 已删除；共享基线库保持")
            except Exception as exc:  # noqa: BLE001
                print(f"[CLEANUP-FAIL] 临时库删除失败: {exc}")
                raise
        for tmp in (bt_up, bt_re):
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
        if run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)


if __name__ == "__main__":
    main()
