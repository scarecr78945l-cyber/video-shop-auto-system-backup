# -*- coding: utf-8 -*-
"""T4: 17 trigger migration 往返 + 幂等 drill（round-59）。

流程：
  upgrade head（base -> T1..T4）-> assert_enums + assert_t3_schema + assert_triggers + probes + gen --check
  downgrade 31tbl000001（只回退 T4，保留 T1~T3）-> assert_t4_rolled_back + assert_t3_schema
  upgrade head（re-upgrade）-> assert_triggers + assert_triggers_probes
  再 upgrade head（幂等）-> assert_triggers
用法：python scripts/t4_trigger_drill.py（需 MIGRATION_ROLE/DATABASE_URL）
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


def alembic(*args):
    print(f"\n=== alembic {args[0]} {args[1] if len(args) > 1 else ''} ===")
    r = subprocess.run([PY, "-m", "alembic"] + list(args), cwd=BASE, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[FAIL] alembic {args} rc={r.returncode}", file=sys.stderr)
        print(r.stderr[-400:], file=sys.stderr)
        sys.exit(r.returncode)
    return r


def run_script(name, check=True, extra_env=None):
    print(f"\n=== {name} ===")
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    r = subprocess.run([PY, os.path.join(BASE, "scripts", name)], capture_output=True, text=True, env=env)
    print(r.stdout, end="")
    if r.returncode != 0 and check:
        sys.exit(r.returncode)


def gen_check():
    print("\n=== gen_trg_migration.py --check ===")
    r = subprocess.run([PY, os.path.join(BASE, "scripts", "gen_trg_migration.py"), "--check"],
                       capture_output=True, text=True)
    print(r.stdout, end="")
    if r.returncode != 0:
        sys.exit(r.returncode)


T4_EXPECT = {"T4_TRIGGER_EXPECT": "17"}

alembic("upgrade", "head")
run_script("assert_enums.py")
run_script("assert_t3_schema.py", extra_env=T4_EXPECT)
run_script("assert_triggers.py")
run_script("assert_triggers_probes.py")
gen_check()

# T4 单包回退：只回退 17trg000001 -> 31tbl000001，保留 T1~T3
alembic("downgrade", "31tbl000001")
run_script("assert_t4_rolled_back.py")
run_script("assert_t3_schema.py")  # trigger=0（T3 默认）

alembic("upgrade", "head")
run_script("assert_triggers.py")
run_script("assert_triggers_probes.py")

# 幂等：重复 upgrade head
alembic("upgrade", "head")
run_script("assert_triggers.py")

print("\nT4 DRILL: PASS")