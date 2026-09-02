# -*- coding: utf-8 -*-
"""真人路径：搜索框 Ctrl+V 粘贴图片触发识图（用后即删）"""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        api_calls = []
        page.on("request", lambda r: api_calls.append(r.url[:150])
                if ("image" in r.url.lower() or "pict" in r.url or "visual" in r.url or "img" in r.url) and "img.alicdn" not in r.url and "mmstat" not in r.url and "g.alicdn" not in r.url else None)

        page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(7000)

        # 聚焦搜索框
        box = page.locator("input[class*='imageSearch'], input[class*='search'], input[placeholder*='搜索']").first
        print("搜索框:", box.count(), flush=True)
        box.click(timeout=5000)
        page.wait_for_timeout(1500)

        # 真实 Ctrl+V 粘贴（图片在系统剪贴板）
        page.keyboard.press("Control+v")
        print("已 Ctrl+V 粘贴，等待识图...", flush=True)

        for i in range(15):
            page.wait_for_timeout(1500)
            url = page.url
            if "s.taobao" in url or "search" in url:
                print(f"  t+{(i+1)*1.5:.0f}s 跳转: {url[:90]}", flush=True)
                break
        print("最终 URL:", page.url[:90], flush=True)
        body = page.evaluate("() => document.body.innerText || ''")
        print("含'综合':", '综合' in body, "含'同款':", '同款' in body, flush=True)
        print(f"\n识图 API 请求 {len(api_calls)}:")
        for u in api_calls[-10:]:
            print("  ", u)
        page.screenshot(path="paste_result.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
