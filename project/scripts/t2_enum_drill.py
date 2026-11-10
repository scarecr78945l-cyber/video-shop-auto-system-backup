# -*- coding: utf-8 -*-
"""T2: 60 enum migration 往返 + 幂等 drill（round-51 R50-2 修正：单步回退保留 T1）。

流程：
  upgrade head -> assert_enums.py
  downgrade 32f34131a28a（只回退 T2，保留 T1 baseline）-> assert_enums_t1_retained.py
  upgrade head -> assert_enums.py
  再 upgrade head（重复运行幂等）-> assert_enums.py
用法：python scripts/t2_enum_drill.py（需 MIGRATION_ROLE/DATABASE_URL）
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


def run_script(name):
    print(f"\n=== {name} ===")
    r = subprocess.run([PY, os.path.join(BASE, "scripts", name)], capture_output=True, text=True)
    print(r.stdout, end="")
    if r.returncode != 0:
        sys.exit(r.returncode)


alembic("upgrade", "head")
run_script("assert_enums.py")

# R50-2：只回退 T2（60enum000000 -> 32f34131a28a），保留 T1 baseline 与 btree_gist
alembic("downgrade", "32f34131a28a")
run_script("assert_enums_t1_retained.py")

alembic("upgrade", "head")
run_script("assert_enums.py")

# 幂等：重复 upgrade head 应无新增
alembic("upgrade", "head")
run_script("assert_enums.py")

print("\nT2 DRILL: PASS")
