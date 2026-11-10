# -*- coding: utf-8 -*-
"""R44-3：offline 模式必须稳定拒绝（供 drill 校验；正常应非零退出）。"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

r = subprocess.run([PY, "-m", "alembic", "upgrade", "head", "--sql"], cwd=BASE, capture_output=True, text=True)
print("offline rc =", r.returncode)
if r.stdout:
    print(r.stdout[:200])
if r.stderr:
    print(r.stderr[:300])
# offline 应失败（本契约明确关闭 offline，R44-3）
sys.exit(0 if r.returncode != 0 else 1)
