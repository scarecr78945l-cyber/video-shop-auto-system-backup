# -*- coding: utf-8 -*-
"""拼 #1 的 main_0~5 看效果（用后即删）"""
from pathlib import Path
from PIL import Image

OUT = Path("data/images/listing") / "1"
imgs = [Image.open(OUT / f"main_{i}.png") for i in range(6) if (OUT / f"main_{i}.png").exists()]
w, h = imgs[0].size
canvas = Image.new("RGB", (w * len(imgs) + (len(imgs)-1) * 10, h), (255, 255, 255))
for i, im in enumerate(imgs):
    canvas.paste(im, (i * (w + 10), 0))
canvas.save("_collage_strict.png")
print("saved", [im.size for im in imgs])
