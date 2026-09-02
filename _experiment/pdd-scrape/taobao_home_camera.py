# -*- coding: utf-8 -*-
"""用首页搜索框相机图标触发淘宝识图（官方入口，用后即删）"""
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

        # 聚焦搜索框，找相机图标（image-search-icon-pic）
        page.evaluate("""() => {
            const box = document.querySelector('input[class*="imageSearch"]') || document.querySelector('input[class*="search"]');
            if (box) box.focus();
        }""")
        page.wait_for_timeout(2000)
        clicked = page.evaluate("""() => {
            const icon = document.querySelector('[class*="image-search-icon-pic"], [class*="image-search-icon-wrapper"], [class*="img-search"]');
            if (icon) { icon.click(); return icon.className; }
            return 'no icon';
        }""")
        print("点击相机图标:", clicked)
        page.wait_for_timeout(4000)
        print("URL:", page.url[:80])

        # 点击后找 file input 并上传
        fi = page.locator("input[type=file]").first
        print("file input count:", page.locator("input[type=file]").count())
        if page.locator("input[type=file]").count() > 0:
            fi.set_input_files(str(IMG), timeout=30000)
            print("已上传，等待识图...")
            page.wait_for_timeout(12000)
            print("识图后 URL:", page.url[:90])
            # 页面是否有识图结果
            body = page.evaluate("() => document.body.innerText || ''")
            print("正文含'同款':", '同款' in body, "| 含'猜你喜欢':", '猜你喜欢' in body, "| 含'抱歉':", '抱歉' in body)
            page.screenshot(path="taobao_home_camera.png", full_page=False)
        else:
            print("相机点击后无 file input，截图看状态")
            page.screenshot(path="taobao_home_camera2.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
