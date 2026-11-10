# -*- coding: utf-8 -*-
"""T9: CI 分层脚本（test-strategy.md §八 job1~job6 冻结顺序；round-121 R120-2/3 定稿）。

  job1 lint（python 编译检查）
  job2 unit（无 DB 依赖：CID/幂等键纯值——workflow golden + CID golden/canonical/envelope）
  job3 empty DB + alembic upgrade head（独立临时库）
  job4 catalog exact-set + trigger/T3 探针 + 样本重放 + repository/trigger/fixture-e2e pytest
  job5 alembic downgrade base + 空库断言
  job6 re-upgrade head + catalog/behavior 回归

migration 与行为分离；migration 失败即阻断。每 job 结果携带 mode/provider/model/source/evidence。
UUID basetemp 根 + finally 精确清理（R114-3/R116-3）。
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

BASE_URL = os.environ.get("DATABASE_URL", "").strip()
ADMIN_URL = os.environ.get("T9_ADMIN_URL", "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/postgres")


def run(cmd, env=None, cwd=None):
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    if env:
        e.update(env)
    r = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, timeout=600)
    if r.returncode != 0:
        print(f"[JOB-FAIL] {' '.join(cmd)} rc={r.returncode}")
        print(r.stdout[-1500:])
        print(r.stderr[-1500:])
        sys.exit(1)
    return r


def _admin_sql(sql: str) -> None:
    """管理员连接执行 DDL（AUTOCOMMIT，避免 CREATE/DROP DATABASE 事务块错误）。"""
    from sqlalchemy import create_engine, text

    e = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with e.connect() as c:
        c.execute(text(sql))
    e.dispose()


def main():
    if not BASE_URL:
        print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    dbname = "dsh_test_ci_" + uuid.uuid4().hex[:8]
    temp_url = BASE_URL.rsplit("/", 1)[0] + "/" + dbname
    # R114-3：本次运行唯一 basetemp 根（所有阶段派生；finally 只清理本次根）
    run_root = BACKEND / f".pytest-tmp-ci-{uuid.uuid4().hex[:8]}"
    bt_u = run_root / "unit"
    bt_4 = run_root / "j4"
    bt_6 = run_root / "j6"
    for _bt in (bt_u, bt_4, bt_6):
        _bt.mkdir(parents=True, exist_ok=True)
    print(f"[BASETEMP] {run_root}（本次运行独占）")
    created = False

    try:  # R116-3：lint/unit 失败也在 finally 清理范围内（从根创建起）
        print("[JOB1] lint（python 编译检查）")
        for f in ["backend/domain/workflow/queue.py", "backend/tests/test_workflow_queue.py",
                  "project/scripts/t9_rollback_drill.py"]:
            run(["python", "-m", "py_compile", str(ROOT / f)])
        print("[JOB1] PASS mode=lint provider=local model=py_compile source=t9_ci_layers.py evidence=job1-lint")

        print("[JOB2] unit（无 DB 依赖：CID/幂等键纯值）")
        run(["python", "-m", "pytest", "tests/test_workflow_queue.py",
             "-q", "--basetemp=" + str(bt_u), "-k",
             "golden_vectors or canonical_join or run_key or uuid_case or time_normalized"],
            cwd=BACKEND)
        run(["python", "-m", "pytest", "tests/test_cid_engine.py",
             "-q", "--basetemp=" + str(bt_u), "-k",
             "golden or canonical or envelope"], cwd=BACKEND)
        print("[JOB2] PASS mode=unit provider=local model=pytest source=t9_ci_layers.py evidence=job2-unit-cid-idem")

        env = {"DATABASE_URL": temp_url, "MIGRATION_ROLE": "dsh_migrator"}

        _admin_sql(f"CREATE DATABASE {dbname}")
        created = True  # R112-3：CREATE 成功即登记所有权
        _admin_sql(f"ALTER DATABASE {dbname} OWNER TO dsh_migrator")
        # R112-4：不预装扩展（owner=dsh_migrator 可建；migration 创建路径）

        print("[JOB3] empty DB + alembic upgrade head")
        run(["python", "-m", "alembic", "upgrade", "head"], env=env, cwd=PROJECT)
        print("[JOB3] PASS mode=migration provider=postgres:16 model=alembic source=t9_ci_layers.py evidence=job3-upgrade-head")

        print("[JOB4] catalog exact-set + trigger/T3 探针 + 样本重放 + fixture-e2e pytest")
        run(["python", "scripts/assert_t9_catalog.py"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_cid_engine.py"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_triggers_probes.py"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_t3_probes.py"], env=env, cwd=PROJECT)
        run(["python", "-m", "pytest", "tests/test_ads_fixtures.py",
             "tests/test_p2_fixtures.py", "-q", "--basetemp=" + str(bt_4)],
            env=env, cwd=BACKEND)
        run(["python", "-m", "pytest", "tests/test_cid_engine.py",
             "tests/test_secret_store.py", "tests/test_auth_actor.py",
             "tests/test_auth_seed.py", "tests/test_auth_integration.py",
             "tests/test_auth_idp_chain.py", "tests/test_workflow_queue.py",
             "-q", "--basetemp=" + str(bt_4)], env=env, cwd=BACKEND)
        print("[JOB4] PASS mode=behavior provider=postgres:16 model=alembic+pytest source=t9_ci_layers.py evidence=job4-catalog-trigger-t3-samples")

        print("[JOB5] alembic downgrade base + 空库断言")
        run(["python", "-m", "alembic", "downgrade", "base"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_t9_base.py"], env=env, cwd=PROJECT)
        print("[JOB5] PASS mode=migration provider=postgres:16 model=alembic source=t9_ci_layers.py evidence=job5-downgrade-base-empty")

        print("[JOB6] re-upgrade head + catalog/behavior 回归")
        run(["python", "-m", "alembic", "upgrade", "head"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_t9_catalog.py"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_triggers_probes.py"], env=env, cwd=PROJECT)
        run(["python", "scripts/assert_t3_probes.py"], env=env, cwd=PROJECT)
        run(["python", "-m", "pytest", "tests/test_ads_fixtures.py",
             "tests/test_p2_fixtures.py", "-q", "--basetemp=" + str(bt_6)],
            env=env, cwd=BACKEND)
        run(["python", "-m", "pytest", "tests/test_cid_engine.py",
             "tests/test_secret_store.py", "tests/test_auth_actor.py",
             "tests/test_auth_seed.py", "tests/test_auth_integration.py",
             "tests/test_auth_idp_chain.py", "tests/test_workflow_queue.py",
             "-q", "--basetemp=" + str(bt_6)], env=env, cwd=BACKEND)
        print("[JOB6] PASS mode=behavior provider=postgres:16 model=alembic+pytest source=t9_ci_layers.py evidence=job6-reupgrade-regression")
        print("T9_CI_LAYERS=PASS")
    finally:
        # R112-3：DROP DATABASE 最先（文件清理失败不影响库清理）
        if created:
            try:
                _admin_sql(f"DROP DATABASE IF EXISTS {dbname} (FORCE)")
                print(f"[CLEANUP] CI 临时库 {dbname} 已删除")
            except Exception as exc:  # noqa: BLE001
                print(f"[CLEANUP-FAIL] CI 临时库删除失败: {exc}")
                raise
        for tmp in (bt_u, bt_4, bt_6):
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
        if run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)


if __name__ == "__main__":
    main()
