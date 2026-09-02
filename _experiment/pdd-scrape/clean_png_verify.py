# -*- coding: utf-8 -*-
"""用干净 PNG 重新验证淘宝识图（修复扩展名/内容不匹配卡点）（用后即删）"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

IMGS = {
    1: Path("data/tmp_taobao_input/1_clean.png"),
    22: Path("data/tmp_taobao_input/22_clean.png"),
}

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        api_calls = []
        page.on("request", lambda r: api_calls.append(r.url[:160])
                if any(k in r.url for k in ["h5api.m.taobao.com", "mtop", "visual", "picture.search", "imgsearch", "imageSearch"]) and "mmstat" not in r.url else None)

        for pid, img in IMGS.items():
            print(f"\n=== #{pid} 干净PNG: {img.name} ===", flush=True)
            page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(7000)
            cam = page.locator("[class*='image-search-icon-wrapper']").first
            cam.hover(timeout=5000)
            page.wait_for_timeout(800)
            cam.click(timeout=5000)
            page.wait_for_timeout(2500)
            ub = page.locator("text=上传图片").first
            with page.expect_file_chooser(timeout=8000) as fc:
                ub.click(timeout=5000)
            fc.value.set_files(str(img))
            print("已上传干净PNG，等待识图...", flush=True)

            jumped = False
            for i in range(20):
                page.wait_for_timeout(1500)
                if "s.taobao" in page.url or "search" in page.url:
                    print(f"  t+{(i+1)*1.5:.0f}s 跳转: {page.url[:90]}", flush=True)
                    jumped = True
                    break
            print("最终 URL:", page.url[:90], flush=True)
            print(f"识图API请求 {len(api_calls)}:", flush=True)
            for u in api_calls[-8:]:
                print("  ", u, flush=True)
            page.screenshot(path=f"clean_{pid}.png", full_page=False)
            api_calls.clear()
            if pid == 1:
                time.sleep(5)  # 间隔
    finally:
        page.close()
finally:
    pw.stop()
