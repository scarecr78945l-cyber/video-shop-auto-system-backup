# -*- coding: utf-8 -*-
"""最终验证：官方相机识图 + 1688高清图 + .tb-pick-content-item 提取（用后即删）"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# 官方相机识图 + 1688 高清洗衣粉图
IMG = Path("data/tmp_taobao_input/22_1688.jpg")

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(7000)
        page.locator("[class*='image-search-icon-wrapper']").first.hover(timeout=5000)
        page.wait_for_timeout(800)
        page.locator("[class*='image-search-icon-wrapper']").first.click(timeout=5000)
        page.wait_for_timeout(2500)
        ub = page.locator("text=上传图片").first
        if ub.count() > 0:
            with page.expect_file_chooser(timeout=8000) as fc:
                ub.click(timeout=5000)
            fc.value.set_files(str(IMG))
        print("已上传，等待识图结果渲染...", flush=True)
        page.wait_for_timeout(15000)

        # 提取 .tb-pick-content-item（官方识图结果卡片，带同款标签）
        cards = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.tb-pick-content-item').forEach(el => {
                const a = el.querySelector('a[href*="item.taobao.com"]');
                const href = a ? a.getAttribute('href') : '';
                const m = href.match(/item\\.taobao\\.com\\/item\\.htm\\?id=(\\d+)/);
                if (!m) return;
                const t = (el.textContent||'').replace(/\\s+/g,' ').trim();
                out.push({id: m[1], title: t.slice(0, 55)});
            });
            return out;
        }""")
        print(f"\n识图结果卡片 {len(cards)} 个:")
        for it in cards[:12]:
            print(f"  {it['id']} {it['title'][:45]}")
        page.screenshot(path="official_22.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
