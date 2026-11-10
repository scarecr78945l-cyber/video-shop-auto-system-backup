# -*- coding: utf-8 -*-
"""P0-2 批次 2（C2）：四类源码变异门禁演练（round-161；round-160 D7 纳入验收）。

D7 四项真实变异，逐项 RC=1、还原 RC=0：

1. `identity_key_drops_aggregation_version`——fb 身份键漏 `aggregation_version`
   （三黄金键断言不再成立）；
2. `replay_comparison_misses_extra_explanation`——replay 比较集漏 `extra_explanation`
   （NULL↔对象不再判冲突）；
3. `audit_also_on_replay`——`created=false` 也写审计（重放新增第二条 feedback_write）；
4. `audit_split_from_ledger_transaction`——ledger 写入移出 Service savepoint，
   **覆盖「调用方捕获审计异常后仍提交外层事务」路径**：本次 ledger 不再回滚为 0。

流程：
  1. 独立临时库 upgrade head（复用冻结迁移，不触碰共享基线 dsh_test）；
  2. 基线：C2 两个测试文件 pytest RC=0；
  3. 逐项变异：改源码 → 跑目标用例期望 RC≠0 → 还原 → 再跑期望 RC=0；
  4. finally 清理临时库；源码任何异常路径都还原为备份。

用法（PowerShell）：
  $env:DATABASE_URL="postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test"
  $env:MIGRATION_ROLE="dsh_migrator"
  python project/scripts/p0_2_c2_mutation_drill.py
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
BACKEND = ROOT / "backend"

ADMIN_URL = os.environ.get("T9_ADMIN_URL", "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/postgres")

FEEDBACK_REPO = BACKEND / "domain" / "report" / "feedback_repository.py"
FEEDBACK_SVC = BACKEND / "domain" / "report" / "feedback_service.py"

C2_TESTS = ["tests/test_report_feedback.py", "tests/test_report_feedback_service.py"]

MUTANTS = [
    {
        "name": "identity_key_drops_aggregation_version",
        "file": FEEDBACK_REPO,
        "old": ('    return _hash_key("fb", [source_snapshot_id, feedback_type, subject_type, subject_key,\n'
                '                            aggregation_version])\n'),
        "new": ('    return _hash_key("fb", [source_snapshot_id, feedback_type, subject_type, subject_key])\n'),
        "tests": ["tests/test_report_feedback.py::test_golden_key_a"],
        "note": "变异：五字段 fb:v1 身份公式漏 aggregation_version（黄金键不再成立）",
    },
    {
        "name": "replay_comparison_misses_extra_explanation",
        "file": FEEDBACK_REPO,
        "old": ('    "subject_key", "value", "aggregation_version", "extra_explanation",\n'
                ')\n'),
        "new": ('    "subject_key", "value", "aggregation_version",\n'
                ')\n'),
        "tests": ["tests/test_report_feedback.py::test_pg_extra_explanation_null_safe_conflict"],
        "note": "变异：replay 比较集漏 extra_explanation（NULL↔对象不再判冲突）",
    },
    {
        "name": "audit_also_on_replay",
        "file": FEEDBACK_SVC,
        "old": "            result = self._repo.write(draft)\n            if result.created:\n",
        "new": "            result = self._repo.write(draft)\n            if True:  # 变异：重放也写审计\n",
        "tests": ["tests/test_report_feedback_service.py::test_service_replay_no_new_audit"],
        "note": "变异：created=false 也写反馈审计（重放新增第二条 audit）",
    },
    {
        "name": "audit_split_from_ledger_transaction",
        "file": FEEDBACK_SVC,
        "old": "        with self._conn.begin_nested():\n            result = self._repo.write(draft)\n",
        "new": "        if True:  # 变异：ledger 写入移出 savepoint（审计异常不再回滚业务行）\n"
               "            result = self._repo.write(draft)\n",
        "tests": ["tests/test_report_feedback_service.py::"
                  "test_r1603_audit_failure_savepoint_rollback_outer_commit_keeps_nothing"],
        "note": "变异：ledger 与审计拆出同一 savepoint；捕获审计异常后外层提交仍留下 ledger 行",
    },
]


def run(cmd, env=None, allow_fail=False, cwd=None):
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    if env:
        e.update(env)
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, timeout=1200, cwd=cwd)
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


def apply_edit(path: Path, old: str, new: str) -> None:
    src = path.read_text(encoding="utf-8")
    assert old in src, f"变异锚点未命中 {path.name}: {old[:80]!r}"
    path.write_text(src.replace(old, new, 1), encoding="utf-8")


def pytest_c2(env, bt, extra=None):
    return run(["python", "-m", "pytest", *(extra or C2_TESTS), "-q", "-p", "no:cacheprovider",
                "--basetemp=" + str(bt)], env=env, cwd=str(BACKEND), allow_fail=True)


def main():
    base = os.environ.get("DATABASE_URL", "").strip()
    if not base:
        print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    dbname = "dsh_test_p02m_" + uuid.uuid4().hex[:8]
    temp_url = base.rsplit("/", 1)[0] + "/" + dbname
    bt = BACKEND / f".pytest-tmp-c2m-{uuid.uuid4().hex[:8]}"
    bt.mkdir(parents=True, exist_ok=True)
    created = False
    backups = {}
    try:
        for p in (FEEDBACK_REPO, FEEDBACK_SVC):
            backups[p] = p.read_bytes()

        admin_sql(f"CREATE DATABASE {dbname}")
        created = True
        admin_sql(f"ALTER DATABASE {dbname} OWNER TO dsh_migrator")
        env = {"DATABASE_URL": temp_url, "MIGRATION_ROLE": "dsh_migrator"}
        run(["python", "-m", "alembic", "upgrade", "head"], env=env, cwd=str(PROJECT))
        print("[STEP0] 临时库 upgrade head OK")

        r0 = pytest_c2(env, bt / "base")
        assert r0.returncode == 0, f"基线 C2 pytest 应 RC=0（实际 {r0.returncode}）"
        print("[STEP1] 基线 C2 pytest RC=0 PASS")

        ok_count = 0
        for idx, m in enumerate(MUTANTS, start=1):
            name = m["name"]
            apply_edit(m["file"], m["old"], m["new"])
            try:
                rm = pytest_c2(env, bt / f"mut{idx}", extra=m["tests"])
                assert rm.returncode != 0, f"变异 {name} 未导致失败（RC=0）"
                print(f"[STEP2.{idx}] 变异 {name} 目标用例 RC={rm.returncode}（期望非 0）PASS")
            finally:
                m["file"].write_bytes(backups[m["file"]])
            rr = pytest_c2(env, bt / f"rest{idx}", extra=m["tests"])
            assert rr.returncode == 0, f"变异 {name} 还原后应 RC=0（实际 {rr.returncode}）"
            print(f"[STEP3.{idx}] 变异 {name} 还原后 RC=0 PASS")
            ok_count += 1

        r_final = pytest_c2(env, bt / "final")
        assert r_final.returncode == 0, "全部还原后 C2 全量应 RC=0"
        print(f"[STEP4] 全部还原后 C2 全量 RC=0 PASS；变异 {ok_count}/{len(MUTANTS)} 符合预期")
        print("P0_2_C2_MUTATION_DRILL=PASS")
    finally:
        for p, data in backups.items():
            try:
                p.write_bytes(data)
            except Exception:  # noqa: BLE001
                pass
        if created:
            try:
                admin_sql(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)")
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] 临时库清理失败 {dbname}: {exc}", file=sys.stderr)
        try:
            import shutil
            shutil.rmtree(bt, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
