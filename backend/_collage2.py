# -*- coding: utf-8 -*-
"""拼接查看 3 个商品的 5 张主图（用后即删）"""
from pathlib import Path

from PIL import Image

OUT = Path("data/images/listing")

for pid in [1, 3, 4]:
    d = OUT / str(pid)
    imgs = []
    for i in range(5):
        p = d / f"main_{i}.png"
        imgs.append(Image.open(p) if p.exists() else Image.new("RGB", (400, 400), (200, 200, 200)))
    w, h = imgs[0].size
    canvas = Image.new("RGB", (w * 5 + 40, h), (255, 255, 255))
    for i, im in enumerate(imgs):
        canvas.paste(im, (i * (w + 10), 0))
    out = Path(f"_main_{pid}.png")
    canvas.save(out)
    print("saved", out, [im.size for im in imgs])
