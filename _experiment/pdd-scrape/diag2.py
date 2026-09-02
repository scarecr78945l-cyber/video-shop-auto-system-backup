# -*- coding: utf-8 -*-
"""抓识图上传 API（mtop/h5api）——定位 set_files 后为何不跳转（用后即删）"""
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
        api_calls = []
        page.on("request", lambda r: api_calls.append({
            "url": r.url[:150], "method": r.method,
            "post": (r.post_data or "")[:120]
        }) if ("h5api.m.taobao.com" in r.url or "mtop" in r.url or "pict" in r.url or "image" in r.url.lower() and "img.alicdn" not in r.url) else None)

        page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(7000)
        page.locator("[class*='image-search-icon-wrapper']").first.hover(timeout=5000)
        page.wait_for_timeout(800)
        page.locator("[class*='image-search-icon-wrapper']").first.click(timeout=5000)
        page.wait_for_timeout(2000)
        # 点上传按钮
        ub = page.locator("text=上传图片").first
        if ub.count() > 0:
            with page.expect_file_chooser(timeout=8000) as fc_info:
                ub.click(timeout=5000)
            fc = fc_info.value
            fc.set_files(str(IMG))
        print("已上传，等待...", flush=True)
        page.wait_for_timeout(15000)

        print(f"=== 识图相关 API 请求 {len(api_calls)} ===")
        for c in api_calls:
            print(json.dumps(c, ensure_ascii=False))
        print("\n最终 URL:", page.url[:90], flush=True)
        body = page.evaluate("() => document.body.innerText || ''")
        print("含'综合':", '综合' in body, "含'同款':", '同款' in body, flush=True)
    finally:
        page.close()
finally:
    pw.stop()
