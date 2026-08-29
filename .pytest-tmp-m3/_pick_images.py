# -*- coding: utf-8 -*-
"""挑选 3 张小体积真实生成图并验证 PIL 可读。"""
from pathlib import Path
from PIL import Image

GI = Path(r"E:\视频号上架系统\视频号上架系统\backend\runtime\generated_images")
cands = sorted(GI.glob("*.webp")) + sorted(GI.glob("*.png")) + sorted(GI.glob("*.jpg"))
info = []
for p in cands:
    try:
        with Image.open(p) as im:
            info.append((p.stat().st_size, p.name, im.size, im.format))
    except Exception:
        pass
info.sort()
print("valid images:", len(info))
for size, name, dim, fmt in info[:8]:
    print(f"{size:>8}B {name:<40} {dim} {fmt}")
