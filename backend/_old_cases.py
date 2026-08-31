"""旧系统发品脚本流程提取（步骤/函数/类目选择）。"""
import re
from pathlib import Path

script = Path(r"E:\视频号上架系统\视频号上架系统\backend\app\scripts\open_wechat_upload_product.py")
txt = script.read_text(encoding="utf-8", errors="ignore")
lines = txt.splitlines()
print(f"总行数: {len(lines)}")

# 函数/步骤结构
print("\n=== 函数/类定义 ===")
for i, l in enumerate(lines):
    if re.match(r"^(def |class |    def )", l) and len(l.strip()) < 100:
        print(f"{i+1}: {l.strip()[:90]}")
