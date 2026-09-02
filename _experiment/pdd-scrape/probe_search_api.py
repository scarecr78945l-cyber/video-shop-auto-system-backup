# -*- coding: utf-8 -*-
"""探测拼多多：搜索页渲染 + 抓搜索接口 + 找识图接口（用后即删）"""
import json
from urllib.parse import quote
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].new_page()
    try:
        apis = []
        def on_resp(resp):
            url = resp.url
            if any(k in url for k in ["search", "visual", "image", "upload", "antideep", "anti_content"]):
                apis.append({"url": url[:150], "status": resp.status})
        page.on("response", on_resp)

        kw = quote("不锈钢锅刷")
        page.goto(f"https://mobile.yangkeduo.com/search_result.html?search_key={kw}", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(9000)

        print("URL:", page.url[:90])
        page.screenshot(path="pdd_state.png", full_page=True)
        print("截图: pdd_state.png")

        body = page.evaluate("() => document.body.innerText || ''")
        print("正文长度:", len(body), "| 前120:", body[:120])
        has_goods = page.evaluate("() => !!document.querySelector('a[href*=\"goods_id=\"]')")
        print("有商品链接:", has_goods)

        print("\n捕获接口:")
        for a in apis[:15]:
            print(json.dumps(a, ensure_ascii=False))
    finally:
        page.close()
finally:
    pw.stop()
