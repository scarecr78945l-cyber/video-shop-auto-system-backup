# -*- coding: utf-8 -*-
"""探测拼多多以图搜款：识图页面路由 + API 接口（登录态下，用后即删）"""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].new_page()
    try:
        # 1) 常见识图路由
        for route in [
            "https://mobile.yangkeduo.com/visual_search.html",
            "https://mobile.yangkeduo.com/visual.html",
            "https://mobile.yangkeduo.com/pic_search.html",
            "https://mobile.yangkeduo.com/search_result.html?search_key=%E4%B8%8D%E9%94%88%E9%92%A2%E9%94%85%E5%88%B7",
        ]:
            try:
                page.goto(route, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                title = page.title()[:30]
                body = page.evaluate("() => document.body.innerText || ''")[:120]
                print(f"ROUTE {route.split('.html')[0].split('/')[-1]:<18} → title={title!r} body={body[:60]!r}")
            except Exception as e:
                print(f"ROUTE {route} ERR {str(e)[:60]}")
    finally:
        page.close()
finally:
    pw.stop()
