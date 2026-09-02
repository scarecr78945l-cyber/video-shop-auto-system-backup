# -*- coding: utf-8 -*-
"""探测拼多多网页端：以图搜图/关键词搜 + 商品详情页主图结构（用后即删）"""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].new_page()
    try:
        # 拼多多网页端（移动版更可能支持以图搜）
        for url in [
            "https://mobile.yangkeduo.com/",
            "https://www.pinduoduo.com/",
        ]:
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                print(f"URL: {url}")
                print(f"  title: {page.title()[:50]}")
                print(f"  final: {page.url[:80]}")
                # 探测以图搜图 / 搜索框
                body = page.evaluate("() => document.body.innerText || ''")
                print(f"  文本含'搜索': {'搜索' in body}, 含'拍照': {'拍照' in body}, 含'以图': {'以图' in body}")
                break
            except Exception as e:
                print(f"{url} ERR: {str(e)[:80]}")
    finally:
        page.close()
finally:
    pw.stop()
