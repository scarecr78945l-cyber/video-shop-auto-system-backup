# -*- coding: utf-8 -*-
"""T1 migration 全流程实测脚本（可复现，round-45 R44-2/3 覆盖）。

流程：
  upgrade head -> assert -> downgrade base -> empty-assert -> re-upgrade -> assert
  + offline 拒绝校验（R44-3）
  + 扩展所有权专项（R44-4，另脚本）
用法（env：MIGRATION_ROLE / DATABASE_URL）：
  python scripts/t1_migration_drill.py
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

required = ["MIGRATION_ROLE", "DATABASE_URL"]
missing = [k for k in required if not os.environ.get(k)]
if missing:
    sys.exit(f"缺少环境变量: {missing}")


def run(*args):
    print(f"\n=== alembic {args[0]} {args[1] if len(args) > 1 else ''} ===")
    r = subprocess.run([PY, "-m", "alembic"] + list(args), cwd=BASE, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout, end="")
    if r.returncode != 0:
        print(f"[FAIL] alembic {args} rc={r.returncode}", file=sys.stderr)
        print(r.stderr[-400:], file=sys.stderr)
        sys.exit(r.returncode)


def run_script(name, expect_fail=False):
    print(f"\n=== {name} ===")
    r = subprocess.run([PY, os.path.join(BASE, "scripts", name)], capture_output=True, text=True)
    print(r.stdout, end="")
    if expect_fail:
        if r.returncode == 0:
            print(f"[FAIL] 期望 {name} 失败但返回 0", file=sys.stderr)
            sys.exit(1)
        print(f"（{name} 按预期失败，rc={r.returncode}）")
        return
    if r.returncode != 0:
        sys.exit(r.returncode)


run("upgrade", "head")
run_script("assert_upgrade_head.py")
run("downgrade", "base")
run_script("assert_downgrade_base.py")
run("upgrade", "head")
run_script("assert_upgrade_head.py")

# R44-3：offline 模式必须稳定拒绝（helper 成功退出=拒绝被确认）
run_script("_expect_offline_rejected.py")

print("\nT1 DRILL: PASS")
