# -*- coding: utf-8 -*-
"""从 1688 详情页扒高清商品图（cbu01 图床，无时效）→ 作为淘宝识图输入（用后即删）"""
import re
import sqlite3
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

TMP = Path("data/tmp_taobao_input")
TMP.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect("../../backend/data/db/m1-sourcing.db")
cur = con.cursor()
offers = {}
for pid in [22, 40, 1]:
    cur.execute("SELECT raw_url FROM sku WHERE product_id=? AND raw_url IS NOT NULL LIMIT 1", (pid,))
    row = cur.fetchone()
    if row and row[0]:
        offers[pid] = row[0]
con.close()
print("1688 详情链接:", offers)

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        for pid, url in offers.items():
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(8000)
                imgs = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('img').forEach(el => {
                        const s = el.getAttribute('src') || el.getAttribute('data-src') || '';
                        const r = el.getBoundingClientRect();
                        if (s && s.startsWith('http') && r.width > 200 && (s.includes('alicdn') || s.includes('cbu01') || s.includes('umcdn'))) out.push(s);
                    });
                    return [...new Set(out)].slice(0, 5);
                }""")
                print(f"\n#{pid} {url.split('/')[-1]}")
                for i, u in enumerate(imgs):
                    print(f"  [{i}] {u[:100]}")
                # 下载第一张主图作为识图输入
                if imgs:
                    dest = TMP / f"{pid}_1688.jpg"
                    req = urllib.request.Request(imgs[0], headers={"User-Agent": "Mozilla/5.0"})
                    data = urllib.request.urlopen(req, timeout=15).read()
                    dest.write_bytes(data)
                    print(f"  下载 {len(data)//1024}KB -> {dest.name}")
            except Exception as e:
                print(f"#{pid} ERR {str(e)[:60]}")
    finally:
        page.close()
finally:
    pw.stop()
