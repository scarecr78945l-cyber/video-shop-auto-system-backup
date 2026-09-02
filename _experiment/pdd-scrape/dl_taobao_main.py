# -*- coding: utf-8 -*-
"""下载淘宝详情页主图验证（用后即删）"""
import urllib.request
from pathlib import Path

urls = [
    "//img.alicdn.com/imgextra/i3/2215232749841/O1CN01gEzPqy2MZEURjLdOu_!!2215232749841-0-shopmanager.jpg_760x760q3",
    "//img.alicdn.com/imgextra/i4/2215232749841/O1CN01eKknVQ2MZEpD7Xl3H_!!2215232749841.jpg_q50.jpg_.webp",
    "//img.alicdn.com/imgextra/i3/2215232749841/O1CN01z9fiQf2MZEpBrmVoK_!!2215232749841.jpg_q50.jpg_.webp",
]
OUT = Path("pdd-scrape") / "downloaded"
OUT.mkdir(exist_ok=True)
for i, u in enumerate(urls):
    full = "https:" + u
    try:
        req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://item.taobao.com/"})
        data = urllib.request.urlopen(req, timeout=15).read()
        p = OUT / f"tb_main_{i}.webp"
        p.write_bytes(data)
        print(f"[{i}] {len(data)//1024}KB {p.name} <- {full[:80]}")
    except Exception as e:
        print(f"[{i}] ERR {str(e)[:50]}")
