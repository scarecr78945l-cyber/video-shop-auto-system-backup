# -*- coding: utf-8 -*-
"""用 1688 高清主图重搜 #22/#40 淘宝识图（验证输入质量=根因）（用后即删）"""
from pathlib import Path
from playwright.sync_api import sync_playwright

TMP = Path("data/tmp_taobao_input")

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        for pid in [22, 40]:
            img = TMP / f"{pid}_1688.jpg"
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
            print(f"\n=== #{pid} 1688高清图识图结果 {len(related)} ===")
            for it in related[:6]:
                print(f"  {it['id']} {it['title'][:45]}")
    finally:
        page.close()
finally:
    pw.stop()
