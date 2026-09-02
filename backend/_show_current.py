# -*- coding: utf-8 -*-
"""展示 #1/#3 当前 5 张主图拼图 + dhash 差异（用后即删）"""
from pathlib import Path

from PIL import Image

OUT = Path("data/images/listing")

def dhash(img, size=8):
    img = img.convert("L").resize((size+1, size), Image.LANCZOS)
    px = list(img.getdata())
    bits = []
    for r in range(size):
        for c in range(size):
            bits.append("1" if px[r*(size+1)+c] > px[r*(size+1)+c+1] else "0")
    return "".join(bits)

def hamming(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)

for pid in [1, 3]:
    d = OUT / str(pid)
    imgs = [Image.open(d / f"main_{i}.png") for i in range(5) if (d / f"main_{i}.png").exists()]
    w, h = imgs[0].size
    canvas = Image.new("RGB", (w*5 + 40, h), (255, 255, 255))
    for i, im in enumerate(imgs):
        canvas.paste(im, (i*(w+10), 0))
    canvas.save(f"_current_{pid}.png")
    hs = [dhash(im) for im in imgs]
    diffs = [hamming(hs[0], h) for h in hs[1:]]
    print(f"#{pid} 与main_0的dhash差异: {diffs}（>8 视为明显不同；~0-2 视为同图）")