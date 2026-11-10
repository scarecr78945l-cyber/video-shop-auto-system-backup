# -*- coding: utf-8 -*-
"""Test 有米云 全局素材搜索 (globalMaterial): search a product keyword, inspect result structure."""
import json
import sys
from playwright.sync_api import sync_playwright

KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "内衣洗衣液"

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://console.youshu.youcloud.com/globalMaterial", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        print("url:", page.url[:80], flush=True)
        # type into the search input
        inp = page.locator('input[placeholder*="关键词"], .ymc-input__inner').first
        print("input count:", inp.count(), flush=True)
        if inp.count():
            inp.fill(KEYWORD)
            inp.press("Enter")
            page.wait_for_timeout(6000)
        info = page.evaluate("""() => {
            const cards = document.querySelectorAll('[class*="card"], [class*="Card"], [class*="material"], [class*="Material"], [class*="leaflet"]');
            const imgs = [];
            document.querySelectorAll('img, .ys-bg-img').forEach(el => {
                let u = el.getAttribute('src')||'';
                if (!u) { const st = el.getAttribute('style')||''; const m = st.match(/url\\(\\s*["']?(https?:\\/\\/[^"')\\s]+)/); u = m?m[1]:''; }
                if (u.startsWith('http') && !u.includes('caas') && !u.includes('logo') && u.length>40) imgs.push(u.slice(0,100));
            });
            return {cardCount: cards.length, imgCount: imgs.length, sampleImgs: imgs.slice(0,6),
                    body: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,300)};
        }""")
        print(json.dumps(info, ensure_ascii=False, indent=1)[:1800], flush=True)
    finally:
        page.close()
finally:
    pw.stop()
