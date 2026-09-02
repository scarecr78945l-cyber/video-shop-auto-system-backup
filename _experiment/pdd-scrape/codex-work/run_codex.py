# -*- coding: utf-8 -*-
"""Codex 攻坚启动脚本：读 TASK.md 交给 codex exec（避免命令行转义问题）"""
import subprocess
import sys
from pathlib import Path

TASK = Path("TASK.md").read_text(encoding="utf-8")
workdir = Path(__file__).resolve().parent

result = subprocess.run(
    ["codex", "exec", "-s", "danger-full-access", TASK],
    cwd=str(workdir),
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=5400,
)
print("=== STDOUT ===")
print(result.stdout[-4000:])
print("=== STDERR ===")
print(result.stderr[-2000:])
print(f"exit: {result.returncode}")
