# -*- coding: utf-8 -*-
"""验证：61 商品 5 张主图是否齐全且视觉可辨（用后即删）"""
import sqlite3
from pathlib import Path

from PIL import Image

OUT = Path("data/images/listing")

def dhash(img: Image.Image, size=8) -> str:
    img = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(img.getdata())
    bits = []
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits.append("1" if left > right else "0")
    return "".join(bits)

def hamming(a, b):
    return sum(1 for x, y in zip(a, b) if x != y)

con = sqlite3.connect("data/db/m1-sourcing.db")
cur = con.cursor()
cur.execute("SELECT id FROM products WHERE state='pool' AND real_cost IS NOT NULL")
pool = [r[0] for r in cur.fetchall()]
con.close()

complete = 0
incomplete = []
distinct_ok = 0
for pid in pool:
    d = OUT / str(pid)
    mains = [d / f"main_{i}.png" for i in range(5)]
    if not all(p.exists() for p in mains):
        incomplete.append((pid, [p.name for p in mains if not p.exists()]))
        continue
    complete += 1
    hs = [dhash(Image.open(m)) for m in mains]
    min_pair = min(hamming(a, b) for i, a in enumerate(hs) for b in hs[i+1:])
    if min_pair >= 5:
        distinct_ok += 1
    else:
        incomplete.append((pid, f"dhash min={min_pair}"))

print(f"pool 总数 {len(pool)}")
print(f"5 张主图齐全: {complete}")
print(f"视觉可辨(dhash>=5): {distinct_ok}")
print(f"不完整/同图: {len(incomplete)}")
for pid, why in incomplete[:15]:
    print(f"  #{pid}: {why}")
