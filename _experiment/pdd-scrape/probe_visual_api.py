# -*- coding: utf-8 -*-
"""探测拼多多识图 API 端点（页面上下文 fetch，带登录态，用后即删）"""
import json
from playwright.sync_api import sync_playwright

# 拼多多已知的识图/以图搜接口候选
ENDPOINTS = [
    "https://api.pinduoduo.com/api/search/visual/search",
    "https://apiv2.pinduoduo.com/api/search/visual/search",
    "https://api.pinduoduo.com/api/visual/search",
    "https://mobile.yangkeduo.com/proxy/api/search/visual/search",
    "https://mobile.yangkeduo.com/api/search/visual/search",
    "https://api.pinduoduo.com/api/search/visual/upload",
]

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].new_page()
    try:
        # 先导航到拼多多同源页面（拿 cookie/上下文）
        page.goto("https://mobile.yangkeduo.com/", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        for ep in ENDPOINTS:
            # 用 OPTIONS/GET 探测可达性（POST 识图需 multipart+签名，先看是否有此端点）
            result = page.evaluate("""async (url) => {
                try {
                    const r = await fetch(url, {method: 'GET', credentials: 'include'});
                    const text = await r.text();
                    return {status: r.status, len: text.length, head: text.slice(0, 120)};
                } catch (e) {
                    return {err: String(e).slice(0, 80)};
                }
            }""", ep)
            print(f"{'OK ' if 'status' in result else 'ERR'} {ep}")
            print(f"   {json.dumps(result, ensure_ascii=False)[:140]}")
    finally:
        page.close()
finally:
    pw.stop()
