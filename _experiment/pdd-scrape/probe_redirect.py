# -*- coding: utf-8 -*-
"""精确探测：首页相机识图上传后实际跳转 URL + 结果页结构（用后即删）"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# 用 #22 洗衣液的一张 1688 图（用户同款图源）
IMG = Path("data/tmp_taobao_input/22_1688.jpg")

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        # 监听跳转
        navigations = []
        page.on("framenavigated", lambda f: navigations.append(f.url[:90]) if "taobao" in f.url else None)

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
        # 上传前看 file input
        fi_count = page.locator("input[type=file]").count()
        print("上传前 file input:", fi_count)
        page.locator("input[type=file]").first.set_input_files(str(IMG), timeout=30000)
        print("已上传，等待识别跳转...")
        for i in range(12):
            page.wait_for_timeout(1500)
            print(f"  t+{(i+1)*1.5:.0f}s URL: {page.url[:80]}")
            if "search" in page.url or "s.taobao" in page.url:
                print("  >>> 跳转到搜索/结果页")
                break

        print("\n导航记录:")
        for n in navigations[-8:]:
            print("  ", n)
        # 结果页是否有综合/销量/价格
        body = page.evaluate("() => document.body.innerText || ''")
        print("\n含'综合':", '综合' in body, "含'销量':", '销量' in body, "含'价格':", '价格' in body)
        page.screenshot(path="taobao_img_result2.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
