# -*- coding: utf-8 -*-
"""用原始采集高清图（evidence）重搜 #22/#40（验证输入质量是根因）（用后即删）"""
import json
import sqlite3
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

TMP = Path("data/tmp_taobao_input")
TMP.mkdir(parents=True, exist_ok=True)

# 取 evidence 原始图
con = sqlite3.connect("../../backend/data/db/m1-sourcing.db")
cur = con.cursor()
inputs = {}
for pid in [22, 40]:
    cur.execute("SELECT image_urls FROM product_source_evidence WHERE product_id=? LIMIT 1", (pid,))
    row = cur.fetchone()
    urls = json.loads(row[0]) if row and row[0] else []
    http = [u for u in urls if str(u).startswith("http")]
    if http:
        dest = TMP / f"{pid}.jpg"
        try:
            req = urllib.request.Request(str(http[0]), headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=15).read()
            dest.write_bytes(data)
            inputs[pid] = dest
            print(f"#{pid} 原始图 {len(data)//1024}KB -> {dest.name}")
        except Exception as e:
            print(f"#{pid} 下载ERR {str(e)[:40]}")
con.close()

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        for pid, img in inputs.items():
            page.goto("https://s.taobao.com/image", timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            page.locator("input[type=file]").first.set_input_files(str(img), timeout=30000)
            page.wait_for_timeout(12000)
            related = page.evaluate("""() => {
                const out = [];
                const seen = new Set();
                document.querySelectorAll('[class*="item"],[class*="card"],[class*="Card"],a[href*="item.taobao.com"]').forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width < 150 || r.height < 150) return;
                    const a = el.tagName === 'A' ? el : el.querySelector('a[href]');
                    const href = a ? (a.getAttribute('href')||'') : '';
                    const m = href.match(/item\\.taobao\\.com\\/item\\.htm\\?id=(\\d+)/);
                    if (!m || seen.has(m[1])) return;
                    seen.add(m[1]);
                    out.push({id: m[1], title: (el.textContent||'').replace(/\\s+/g,' ').trim().slice(0,60)});
                });
                return out;
            }""")
            print(f"\n=== #{pid} 原始图识图结果 {len(related)} ===")
            for it in related[:6]:
                print(f"  {it['id']} {it['title'][:45]}")
    finally:
        page.close()
finally:
    pw.stop()
