# -*- coding: utf-8 -*-
"""P0-2 批次 1（B3）：六类源码变异门禁演练（round-133；round-135 R134-1/4 扩展）。

依据 round-132-cdx §四.8 + round-134-cdx R134-1/R134-4：
captured_at 入键、UPDATE 覆盖、漏比较 raw hash、错误 NULL 语义、漏比较维度字段（tenant_id）、
跳过 Repository 受信边界重验——六类变异均 RC=1，还原 RC=0。变异作用于**新交付的批次 1 源码**
（backend/domain/report/），由批次定向 pytest 捕获；与既有 185/61 回归、tsc、T5 CLI、T9 CI 无关
（批次 1 未改动 P0-1 冻结实现）。

流程：
  1. 独立临时库 upgrade head（复用冻结迁移，不触碰共享基线 dsh_test）；
  2. 基线：批次 1 三文件 pytest RC=0；
  3. 逐项变异：改源码 -> 跑相关用例期望 RC=1 -> 还原 -> 再跑期望 RC=0；
  4. finally 清理临时库；源码任何异常路径都还原为备份。

用法（PowerShell，环境同迁移）：
  $env:DATABASE_URL="postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test"
  $env:MIGRATION_ROLE="dsh_migrator"
  python project/scripts/p0_2_batch1_mutation_drill.py
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

ADMIN_URL = os.environ.get("T9_ADMIN_URL", "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/postgres")

# 变异目标：backend/domain/report/version.py（B1）与 repository.py（B2）
VERSION_PY = BACKEND / "domain" / "report" / "version.py"
REPO_PY = BACKEND / "domain" / "report" / "repository.py"

# 各变异的目标测试（该测试在变异存在时 RC=1、还原后 RC=0）
MUTANTS = [
    {
        "name": "captured_at_enters_version_key",
        "file": REPO_PY,
        "old": "        version_key = build_report_version_key(  # 3) 三源 version key\n"
               "            v.platform_version_id, v.platform_updated_at, evidence_hash)\n",
        "new": "        version_key = build_report_version_key(  # 3) 三源 version key\n"
               "            v.platform_version_id, v.platform_updated_at, evidence_hash) \\\n"
               "            + \"-\" + v.captured_at.isoformat()  # R136-1 变异：真实读取 captured_at 污染版本键\n",
        "tests": ["tests/test_snapshot_repository.py::test_captured_at_change_still_reuses"],
        "note": "变异：write_observation 把 v.captured_at 拼入 version key（同 (S,V) 仅 captured_at 不同将产生第二事实而非复用原 id）",
    },
    {
        "name": "repository_update_overwrite",
        "file": REPO_PY,
        "old": "        \"window_start, window_end, attribution_mode, report_version_key) \"\n"
               "        \"DO NOTHING RETURNING id\"",
        "new": "        \"window_start, window_end, attribution_mode, report_version_key) \"\n"
               "        \"DO UPDATE SET gmv = EXCLUDED.gmv RETURNING id\"",
        "tests": ["tests/test_snapshot_repository.py::test_full_replay_reuses_same_id"],
        "note": "变异：ON CONFLICT DO NOTHING -> DO UPDATE（违反 append-only）",
    },
    {
        "name": "comparison_miss_raw_hash",
        "file": REPO_PY,
        "old": "    \"diagnosis\", \"status\", \"raw_evidence_hash\",\n)",
        "new": "    \"diagnosis\", \"status\",\n)",  # 漏掉 raw_evidence_hash
        "tests": ["tests/test_snapshot_repository.py::test_raw_evidence_hash_conflict"],
        "note": "变异：比较集漏 raw_evidence_hash（同 (S,V) 内容不同不再冲突）",
    },
    {
        "name": "wrong_null_semantics",
        "file": REPO_PY,
        "old": "        \"AND shop_listing_sku_id IS NOT DISTINCT FROM :shop_listing_sku_id \"\n"
               "        \"AND asset_binding_id IS NOT DISTINCT FROM :asset_binding_id \"",
        "new": "        \"AND shop_listing_sku_id = :shop_listing_sku_id \"\n"
               "        \"AND asset_binding_id = :asset_binding_id \"",
        "tests": ["tests/test_snapshot_repository.py::test_nulls_not_distinct_both_null_reuse"],
        "note": "变异：NULLS NOT DISTINCT -> 普通 =（NULL 语义错误，重放不命中）",
    },
    {
        "name": "comparison_miss_dimension_field",
        "file": REPO_PY,
        "old": "    \"tenant_id\", \"account_id\", \"shop_id\", \"shop_listing_id\", \"shop_listing_sku_id\",\n",
        "new": "    \"account_id\", \"shop_id\", \"shop_listing_id\", \"shop_listing_sku_id\",\n",  # 漏掉 tenant_id
        "tests": ["tests/test_snapshot_repository.py::test_comparison_field_conflict"],
        "note": "变异：比较集漏维度字段 tenant_id（同 (S,V) 跨租户不再冲突）",
    },
    {
        "name": "skip_repository_boundary_validation",
        "file": REPO_PY,
        "old": "    def _validate_draft(self, draft: _SnapshotDraft) -> None:\n"
               "        \"\"\"INSERT 前重验全部持久化不变量（防内部 draft 绕过/伪造 digest/错误 version key）。\"\"\"\n",
        "new": "    def _validate_draft(self, draft: _SnapshotDraft) -> None:\n"
               "        return  # R134-1 变异：跳过受信边界重验（伪造 digest/错误 version key 不再被拒）\n",
        "tests": [
            "tests/test_snapshot_repository.py::test_draft_boundary_rejects_forged_digest",
            "tests/test_snapshot_repository.py::test_draft_boundary_rejects_wrong_version_key",
        ],
        "note": "变异：跳过 Repository 受信边界重验（伪造 digest/错误 version key 不再被拒）",
    },
]


def run(cmd, env=None, allow_fail=False, cwd=None):
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    if env:
        e.update(env)
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, timeout=900, cwd=cwd)
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


def main():
    base = os.environ.get("DATABASE_URL", "").strip()
    if not base:
        print("[FAIL] 缺少 DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    dbname = "dsh_test_p02m_" + uuid.uuid4().hex[:8]
    temp_url = base.rsplit("/", 1)[0] + "/" + dbname
    bt = BACKEND / f".pytest-tmp-p02m-{uuid.uuid4().hex[:8]}"
    bt.mkdir(parents=True, exist_ok=True)
    created = False
    backups = {}
    try:
        # 备份源码（任何路径 finally 还原）
        for p in (VERSION_PY, REPO_PY):
            backups[p] = p.read_bytes()

        admin_sql(f"CREATE DATABASE {dbname}")
        created = True
        admin_sql(f"ALTER DATABASE {dbname} OWNER TO dsh_migrator")
        env = {"DATABASE_URL": temp_url, "MIGRATION_ROLE": "dsh_migrator"}
        run(["python", "-m", "alembic", "upgrade", "head"], env=env, cwd=str(PROJECT))
        print("[STEP0] 临时库 upgrade head OK")

        tests_all = [
            "tests/test_report_version.py",
            "tests/test_snapshot_repository.py",
            "tests/test_snapshot_collector.py",
        ]
        r0 = run(["python", "-m", "pytest", *tests_all, "-q",
                  "--basetemp=" + str(bt / "base")], env=env, cwd=str(BACKEND), allow_fail=True)
        assert r0.returncode == 0, "基线批次 1 pytest 应 RC=0"
        print("[STEP1] 基线批次 1 pytest RC=0 PASS")

        for m in MUTANTS:
            name = m["name"]
            # 变异生效
            apply_edit(m["file"], m["old"], m["new"])
            r1 = run(["python", "-m", "pytest", *m["tests"], "-q",
                      "--basetemp=" + str(bt / name)], env=env, cwd=str(BACKEND), allow_fail=True)
            ok1 = r1.returncode != 0
            print(f"[MUTANT] {name}（{m['note']}）被捕获 ->", "PASS" if ok1 else "FAIL",
                  f"rc={r1.returncode}")
            if not ok1:
                raise SystemExit(f"{name} 变异未被测试捕获")
            # 还原
            m["file"].write_bytes(backups[m["file"]])
            r2 = run(["python", "-m", "pytest", *m["tests"], "-q",
                      "--basetemp=" + str(bt / (name + "_restore"))],
                     env=env, cwd=str(BACKEND), allow_fail=True)
            ok2 = r2.returncode == 0
            print(f"[RESTORE] {name} 还原后 ->", "PASS" if ok2 else "FAIL", f"rc={r2.returncode}")
            if not ok2:
                raise SystemExit(f"{name} 还原后未回归 RC=0")

        # 最终：源码恢复 + 三文件全绿
        for p, blob in backups.items():
            p.write_bytes(blob)
        r3 = run(["python", "-m", "pytest", *tests_all, "-q",
                  "--basetemp=" + str(bt / "final")], env=env, cwd=str(BACKEND), allow_fail=True)
        assert r3.returncode == 0, "还原后批次 1 三文件应 RC=0"
        print("[FINAL] 还原后批次 1 三文件 RC=0 PASS")
        print("P0_2_BATCH1_MUTATION_DRILL=PASS")
    finally:
        for p, blob in backups.items():
            if p.read_bytes() != blob:
                p.write_bytes(blob)
        if created:
            try:
                admin_sql(f"DROP DATABASE IF EXISTS {dbname} (FORCE)")
                print(f"[CLEANUP] 临时库 {dbname} 已删除")
            except Exception as exc:  # noqa: BLE001
                print(f"[CLEANUP-FAIL] 临时库删除失败: {exc}")
                raise
        if bt.exists():
            shutil.rmtree(bt, ignore_errors=True)


if __name__ == "__main__":
    main()
