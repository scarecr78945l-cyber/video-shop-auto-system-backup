# -*- coding: utf-8 -*-
"""下载扒到的拼多多主图前 6 张看质量（用后即删）"""
import json
import urllib.request
from pathlib import Path

OUT = Path("pdd-scrape")
imgs = json.loads((OUT / "996511983583_main_images.json").read_text(encoding="utf-8"))

dl = OUT / "downloaded"
dl.mkdir(exist_ok=True)
for i, url in enumerate(imgs[:6]):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://mobile.yangkeduo.com/"})
        data = urllib.request.urlopen(req, timeout=15).read()
        ext = ".jpg"
        if "imageMogr2" in url:
            ext = ".jpg"
        if ".png" in url or "format/png" in url:
            ext = ".png"
        p = dl / f"main_{i}{ext}"
        p.write_bytes(data)
        print(f"[{i}] {len(data)//1024}KB {p.name}")
    except Exception as e:
        print(f"[{i}] ERR {str(e)[:50]}")
