# -*- coding: utf-8 -*-
"""淘宝以图搜：从结果区提取同款主图 + 商品链接（低频，用后即删）"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path(__file__).resolve().parent.parent.parent / "backend" / "data" / "images" / "listing" / "1" / "detail_0.png"

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://s.taobao.com/image", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        fi = page.locator("input[type=file]").first
        fi.set_input_files(str(IMG), timeout=30000)
        page.wait_for_timeout(12000)

        # 提取同款商品：图片 + 链接 + 标题 + 价格
        items = page.evaluate("""() => {
            const out = [];
            const seen = new Set();
            document.querySelectorAll('[class*="item"], [class*="Card"], [class*="card"], li').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width < 120 || r.height < 120) return;
                const a = el.querySelector('a[href]');
                const img = el.querySelector('img');
                const t = (el.textContent || '').replace(/\\s+/g,' ').trim().slice(0, 45);
                if (!a && !img) return;
                const href = a ? a.getAttribute('href') : '';
                const src = img ? (img.getAttribute('src') || img.getAttribute('data-src') || '') : '';
                const key = src || href;
                if (seen.has(key)) return;
                seen.add(key);
                out.push({title: t, href: href.slice(0, 90), img: src.slice(0, 110)});
            });
            return out.slice(0, 20);
        }""")
        print(f"提取到 {len(items)} 个同款")
        for i, it in enumerate(items[:10]):
            print(f"  [{i}] {it['title'][:30]} | {it['href'][:40]}")
        (Path(__file__).parent / "pdd-scrape" / "taobao_same_items.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已存 taobao_same_items.json")
    finally:
        page.close()
finally:
    pw.stop()
