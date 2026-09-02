# -*- coding: utf-8 -*-
"""确认官方相机识图后的结果区结构（找'同款'卡片选择器）（用后即删）"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path("data/tmp_taobao_input/1_1688.jpg")

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://www.taobao.com", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        page.evaluate("""() => {
            const box = document.querySelector('input[class*="imageSearch"]') || document.querySelector('input[class*="search"]');
            if (box) box.focus();
        }""")
        page.wait_for_timeout(2000)
        page.evaluate("""() => {
            const icon = document.querySelector('[class*="image-search-icon-wrapper"]');
            if (icon) icon.click();
        }""")
        page.wait_for_timeout(3000)
        page.locator("input[type=file]").first.set_input_files(str(IMG), timeout=30000)
        page.wait_for_timeout(12000)

        # 找"同款"标签附近的商品卡结构
        cards = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('[class*="card"],[class*="item"],[class*="goods"],[class*="recommend"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width < 150 || r.height < 150) return;
                const t = (el.textContent || '').replace(/\\s+/g,' ').trim();
                if (t.includes('同款') || t.includes('锅刷')) {
                    const a = el.querySelector('a[href*="item.taobao.com"]');
                    const href = a ? a.getAttribute('href') : '';
                    const img = el.querySelector('img');
                    const src = img ? (img.getAttribute('src')||img.getAttribute('data-src')||'') : '';
                    out.push({cls:(el.getAttribute('class')||'').slice(0,60), href: href.slice(0,70), img: src.slice(0,80), title: t.slice(0,40)});
                }
            });
            return out.slice(0, 8);
        }""")
        print("同款卡片:", len(cards))
        for c in cards:
            print(json.dumps(c, ensure_ascii=False)[:160])
    finally:
        page.close()
finally:
    pw.stop()
