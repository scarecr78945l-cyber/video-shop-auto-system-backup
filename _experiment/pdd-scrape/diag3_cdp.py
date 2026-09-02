# -*- coding: utf-8 -*-
"""用 CDP DOM.setFileInputFiles 触发淘宝识图上传（更接近真实浏览器，用后即删）"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path("data/tmp_taobao_input/22_1688.jpg").resolve()

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        api_calls = []
        page.on("request", lambda r: api_calls.append(r.url[:140])
                if ("image" in r.url.lower() or "pict" in r.url or "mtop" in r.url) and "img.alicdn" not in r.url and "mmstat" not in r.url else None)

        page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(7000)
        page.locator("[class*='image-search-icon-wrapper']").first.hover(timeout=5000)
        page.wait_for_timeout(800)
        page.locator("[class*='image-search-icon-wrapper']").first.click(timeout=5000)
        page.wait_for_timeout(2500)

        # 点上传按钮 → 打开文件输入
        ub = page.locator("text=上传图片").first
        if ub.count() > 0:
            ub.click(timeout=5000)
        page.wait_for_timeout(2000)

        # 用 CDP DOM.getDocument + querySelector 定位 file input 节点，再 setFileInputFiles
        cdp = ctx.new_cdp_session(page)
        doc = cdp.send("DOM.getDocument")["root"]["nodeId"]
        node = cdp.send("DOM.querySelector", {"nodeId": doc, "selector": "input[type=file]"})
        print("file input nodeId:", node.get("nodeId"), flush=True)
        if node.get("nodeId"):
            cdp.send("DOM.setFileInputFiles", {"nodeId": node["nodeId"], "files": [str(IMG)]})
            print("CDP setFileInputFiles 完成", flush=True)
        else:
            # 兜底 Playwright
            page.locator("input[type=file]").first.set_input_files(str(IMG), timeout=30000)
            print("兜底 set_input_files", flush=True)

        print("等待识图...", flush=True)
        for i in range(15):
            page.wait_for_timeout(1500)
            if "s.taobao" in page.url or "search" in page.url:
                print(f"  t+{(i+1)*1.5:.0f}s 跳转: {page.url[:90]}", flush=True)
                break
        print("最终 URL:", page.url[:90], flush=True)
        print(f"\n识图 API 请求 {len(api_calls)}:")
        for u in api_calls[-12:]:
            print("  ", u)
        page.screenshot(path="cdp_result.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
