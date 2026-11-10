# -*- coding: utf-8 -*-
"""Generate contact sheets of the real HD listing images (main_0..4) for review."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent.parent
LISTING = ROOT / "backend" / "data" / "images" / "listing"
OUT = ROOT / "_management" / "_review_sheets"
OUT.mkdir(parents=True, exist_ok=True)

pids = sorted([int(d.name) for d in LISTING.iterdir()
               if d.is_dir() and d.name.isdigit() and (d / "main_0.png").exists()])
real_pids = [p for p in pids if list((LISTING / str(p)).glob("tb_main_*"))]
print("product dirs:", len(pids), "| with real tb_main:", len(real_pids))

THUMB = 220
LABEL_H = 26


def row_for(pid):
    d = LISTING / str(pid)
    cells = []
    for i in range(5):
        f = d / f"main_{i}.png"
        if f.exists():
            cells.append(Image.open(f).convert("RGB").resize((THUMB, THUMB), Image.LANCZOS))
        else:
            c = Image.new("RGB", (THUMB, THUMB), (40, 40, 40))
            cells.append(c)
    w = THUMB * 5
    row = Image.new("RGB", (w, THUMB + LABEL_H), (250, 250, 250))
    dr = ImageDraw.Draw(row)
    dr.text((6, 4), f"#{pid}", fill=(20, 20, 20))
    for i, c in enumerate(cells):
        row.paste(c, (i * THUMB, LABEL_H))
    return row


# split into sheets of 7 products each
for si, start in enumerate(range(0, len(real_pids), 7)):
    batch = real_pids[start:start + 7]
    rows = [row_for(p) for p in batch]
    h = sum(r.height for r in rows)
    sheet = Image.new("RGB", (THUMB * 5, h), (255, 255, 255))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    fp = OUT / f"review_sheet_{si + 1}.png"
    sheet.save(fp)
    print("saved", fp, sheet.size)

# also individual pid sheets are overkill; one combined sheet of all products' main_0 only for quick scan
all0 = Image.new("RGB", (THUMB * 13, THUMB + LABEL_H), (255, 255, 255))
dr = ImageDraw.Draw(all0)
for i, p in enumerate(real_pids):
    f = LISTING / str(p) / "main_0.png"
    im = Image.open(f).convert("RGB").resize((THUMB, THUMB), Image.LANCZOS)
    all0.paste(im, (i * THUMB, LABEL_H))
    dr.text((i * THUMB + 4, 4), f"#{p}", fill=(20, 20, 20))
fp0 = OUT / "review_all_main0.png"
all0.save(fp0)
print("saved", fp0, all0.size)
