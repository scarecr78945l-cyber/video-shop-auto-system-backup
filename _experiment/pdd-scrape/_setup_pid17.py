# -*- coding: utf-8 -*-
"""Create listing/17 from youmi deep image + generate its 4 img2img variants."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from PIL import Image  # noqa: E402

src = Path("backend/data/images/youmi_deep/17")
d = Path("backend/data/images/listing/17")
d.mkdir(parents=True, exist_ok=True)
imgs = sorted(src.glob("img_*"))
print("source imgs:", [f.name for f in imgs])
best = max(imgs, key=lambda f: f.stat().st_size)
im = Image.open(best).convert("RGB")
w, h = im.size
side = min(w, h)
im = im.crop(((w - side)//2, (h - side)//2, (w - side)//2 + side, (h - side)//2 + side)).resize((800, 800), Image.LANCZOS)
im.save(d / "main_0.png")
im.save(d / "detail_0.png")
print("saved main_0.png + detail_0.png from", best.name)
