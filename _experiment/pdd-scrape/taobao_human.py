# -*- coding: utf-8 -*-
"""淘宝以图搜款：模拟真人浏览器操作（hover+click+文件选择器，非 JS 注入）（用后即删）

关键改进：
- 用 Playwright locator 原生 click/hover（真实鼠标事件），不用 page.evaluate 注入；
- 用 expect_file_chooser 处理文件选择（自然流程）；
- 等待识图后跳转到真正的结果页（s.taobao.com/search?imgfile= 或带 q 的页面）。
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path("data/tmp_taobao_input/22_1688.jpg")

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        # 1) 打开淘宝首页
        page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        page.screenshot(path="tb_1_home.png", full_page=False)

        # 2) 真实 hover 到搜索框（触发搜索框 UI）
        search_input = page.locator("input[class*='imageSearch'], input[class*='search']").first
        print("搜索框:", search_input.count(), search_input.get_attribute("placeholder"), flush=True)
        search_input.hover(timeout=5000)
        page.wait_for_timeout(1500)

        # 3) 找相机图标（搜索框旁 image-search-icon），真实 hover + click
        cam = page.locator("[class*='image-search-icon-wrapper'], [class*='image-search-icon-pic']").first
        print("相机图标:", cam.count(), flush=True)
        cam.hover(timeout=5000)
        page.wait_for_timeout(800)
        # 真实点击（触发文件选择器）
        try:
            with page.expect_file_chooser(timeout=8000) as fc_info:
                cam.click(timeout=5000)
            fc = fc_info.value
            print("文件选择器触发，设置文件...", flush=True)
            fc.set_files(str(IMG))
            print("已设置文件，等待识别...", flush=True)
        except Exception as e:
            print(f"相机点击/文件选择器: {str(e)[:100]}", flush=True)
            # 兜底：若未弹选择器，尝试直接 set_input_files
            page.wait_for_timeout(2000)
            fi = page.locator("input[type=file]").first
            if fi.count() > 0:
                fi.set_input_files(str(IMG), timeout=30000)
                print("兜底 set_input_files", flush=True)

        # 4) 等待识图结果（观察 URL 是否跳转）
        for i in range(15):
            page.wait_for_timeout(1500)
            url = page.url
            if "search" in url or "s.taobao" in url:
                print(f"  t+{(i+1)*1.5:.0f}s 跳转: {url[:90]}", flush=True)
                break
        print("最终 URL:", page.url[:90], flush=True)
        body = page.evaluate("() => document.body.innerText || ''")
        print("含'综合':", '综合' in body, "| 含'同款':", '同款' in body, "| 含'抱歉':", '抱歉' in body, flush=True)
        page.screenshot(path="tb_result.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
