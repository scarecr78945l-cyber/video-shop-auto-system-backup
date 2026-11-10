# -*- coding: utf-8 -*-
"""Single-product validation of youmi deep extraction (#22)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _youmi_deep_stage2 import extract_images, is_real, download

from playwright.sync_api import sync_playwright

GID = "73qZp4l-s~1d7w"
OUT = Path("backend/data/images/youmi_deep/22")
OUT.mkdir(parents=True, exist_ok=True)

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        urls = []
        for tab in ("overview", "leaflet", "video"):
            u = extract_images(page, f"https://console.youshu.youcloud.com/goods/{GID}/{tab}")
            real = [x for x in u if is_real(x)]
            print(f"[{tab}] raw={len(u)} real={len(real)}", flush=True)
            for x in real[:5]:
                print("   ", x[:110], flush=True)
            for x in real:
                if x not in urls:
                    urls.append(x)
        print("total unique:", len(urls), flush=True)
        dl = 0
        for j, u in enumerate(urls[:10]):
            if download(u, OUT / f"img_{j}.jpg"):
                dl += 1
        print(f"downloaded {dl}/10 → {OUT}", flush=True)
    finally:
        page.close()
finally:
    pw.stop()
