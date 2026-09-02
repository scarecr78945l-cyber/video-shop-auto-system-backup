# -*- coding: utf-8 -*-
"""抓首页相机识图上传后的真实网络请求（找带图搜索 URL/API）（用后即删）"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path("data/tmp_taobao_input/22_1688.jpg")

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        reqs = []
        page.on("request", lambda r: reqs.append({"url": r.url[:160], "method": r.method, "post": (r.post_data or "")[:200]})
                if any(k in r.url for k in ["image", "img", "search", "upload", "pict", "s.taobao"])
                else None)

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
        page.wait_for_timeout(10000)

        print(f"捕获 {len(reqs)} 个相关请求:")
        for r in reqs[:20]:
            print(json.dumps(r, ensure_ascii=False))
    finally:
        page.close()
finally:
    pw.stop()
