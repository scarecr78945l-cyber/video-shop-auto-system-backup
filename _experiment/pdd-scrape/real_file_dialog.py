# -*- coding: utf-8 -*-
"""真实系统文件选择：点击上传 → Windows 对话框弹出 → pywinauto 输入路径选图（用后即删）"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path("data/tmp_taobao_input/22_clean.png").resolve()

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        api_calls = []
        page.on("request", lambda r: api_calls.append(r.url[:160])
                if any(k in r.url for k in ["h5api.m.taobao.com", "mtop", "visual", "picture.search", "imgsearch"]) and "mmstat" not in r.url else None)

        page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(7000)
        cam = page.locator("[class*='image-search-icon-wrapper']").first
        cam.hover(timeout=5000)
        page.wait_for_timeout(800)
        cam.click(timeout=5000)
        page.wait_for_timeout(2500)
        ub = page.locator("text=上传图片").first
        # 关键：不用 expect_file_chooser，真实点击让系统对话框弹出
        ub.click(timeout=5000)
        print("已点击上传，等待系统文件对话框弹出...", flush=True)
        time.sleep(3)

        # 用 pywinauto 找系统"打开"对话框
        from pywinauto import Desktop
        dlg = None
        for attempt in range(5):
            try:
                wins = Desktop(backend="uia").windows()
                for w in wins:
                    t = w.window_text()
                    if "打开" in t or "Open" in t:
                        dlg = w
                        print(f"找到文件对话框: {t}", flush=True)
                        break
                if dlg:
                    break
            except Exception as e:
                print(f"  查找对话框 {attempt}: {str(e)[:50]}", flush=True)
            time.sleep(2)

        if not dlg:
            print("未找到系统文件对话框", flush=True)
        else:
            # 在文件名编辑框输入完整路径（Windows 对话框支持直接输入路径+回车）
            try:
                edit = dlg.child_window(auto_id="1148", control_type="Edit")  # 文件名编辑框
                edit.set_text(str(IMG))
                print("已输入路径:", str(IMG), flush=True)
                time.sleep(1)
                # 点击"打开"按钮
                open_btn = dlg.child_window(title="打开", control_type="Button")
                if open_btn.exists():
                    open_btn.click()
                else:
                    dlg.child_window(title_re=".*打开.*").click()
                print("已点击打开", flush=True)
            except Exception as e:
                print(f"pywinauto 操作失败: {str(e)[:100]}", flush=True)
                # 兜底：sendkeys
                try:
                    dlg.type_keys(str(IMG) + "{ENTER}", with_spaces=True)
                    print("兜底 SendKeys", flush=True)
                except Exception as e2:
                    print(f"SendKeys 失败: {str(e2)[:80]}", flush=True)

        print("等待识图...", flush=True)
        for i in range(20):
            page.wait_for_timeout(1500)
            if "s.taobao" in page.url or "search" in page.url:
                print(f"  t+{(i+1)*1.5:.0f}s 跳转: {page.url[:90]}", flush=True)
                break
        print("最终 URL:", page.url[:90], flush=True)
        print(f"识图API {len(api_calls)}:", flush=True)
        for u in api_calls[-8:]:
            print("  ", u, flush=True)
        page.screenshot(path="real_dialog_result.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
