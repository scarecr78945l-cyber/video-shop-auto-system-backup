"""临时探测脚本（交付前删除）：验证真实子进程 + capture_output 在本环境可用。"""
import subprocess
import sys
import tempfile
from pathlib import Path

d = Path(tempfile.mkdtemp())
s = d / "child.py"
s.write_text(
    "import sys\nprint('HELLO-FROM-CHILD')\nprint('ERR-LINE', file=sys.stderr)\nsys.exit(0)",
    encoding="utf-8",
)
r = subprocess.run([sys.executable, str(s)], capture_output=True, timeout=10)
print("rc:", r.returncode)
print("out:", r.stdout.decode("utf-8", "replace").strip())
print("err:", r.stderr.decode("utf-8", "replace").strip())

# 超时场景：子进程 sleep，父进程 timeout 生效
t0 = __import__("time").time()
try:
    subprocess.run([sys.executable, "-c", "import time; time.sleep(30)"], capture_output=True, timeout=1)
    print("timeout: NOT TRIGGERED (bad)")
except subprocess.TimeoutExpired:
    print("timeout: OK, elapsed=%.2fs" % (__import__("time").time() - t0))

# 非零退出码
r2 = subprocess.run([sys.executable, "-c", "import sys; sys.exit(3)"], capture_output=True, timeout=10)
print("exit3 rc:", r2.returncode)
print("SUBPROCESS PROBE PASSED")
