# -*- coding: utf-8 -*-
"""CDP 关闭文件选择拦截 → 让真实 Windows 对话框弹出（用后即删）"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path("data/tmp_taobao_input/22_clean.png").resolve()

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    cdp = ctx.new_cdp_session(page)
    try:
        # 关闭 file chooser 拦截（Playwright 默认拦截，需显式关）
        cdp.send("Page.setInterceptFileChooserDialog", {"enabled": False})
        print("已关闭 file chooser 拦截", flush=True)

        page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(7000)
        cam = page.locator("[class*='image-search-icon-wrapper']").first
        cam.hover(timeout=5000)
        page.wait_for_timeout(800)
        cam.click(timeout=5000)
        page.wait_for_timeout(2500)
        ub = page.locator("text=上传图片").first
        ub.click(timeout=5000)
        print("已点击上传，等待系统对话框...", flush=True)
        time.sleep(3)

        from pywinauto import Desktop
        dlg = None
        for attempt in range(5):
            try:
                for w in Desktop(backend="uia").windows():
                    t = w.window_text()
                    if "打开" in t or "Open" in t or "选择" in t:
                        dlg = w
                        print("找到对话框:", t, flush=True)
                        break
                if dlg:
                    break
            except Exception as e:
                print(f"  查找 {attempt}: {str(e)[:50]}", flush=True)
            time.sleep(2)

        if not dlg:
            print("仍未找到系统文件对话框", flush=True)
        else:
            # 输入路径（Windows 文件对话框支持地址栏直接输入路径）
            try:
                edit = dlg.child_window(auto_id="1148", control_type="Edit")
                edit.set_text(str(IMG))
                time.sleep(1)
                btn = dlg.child_window(title="打开", control_type="Button")
                if btn.exists():
                    btn.click()
                else:
                    dlg.type_keys("{ENTER}")
                print("已选图并确认", flush=True)
            except Exception as e:
                print(f"pywinauto: {str(e)[:100]}", flush=True)
                try:
                    dlg.type_keys(str(IMG) + "{ENTER}", with_spaces=True)
                except Exception as e2:
                    print(f"SendKeys: {str(e2)[:80]}", flush=True)

        print("等待识图...", flush=True)
        for i in range(20):
            page.wait_for_timeout(1500)
            if "s.taobao" in page.url or "search" in page.url:
                print(f"  t+{(i+1)*1.5:.0f}s 跳转: {page.url[:90]}", flush=True)
                break
        print("最终 URL:", page.url[:90], flush=True)
        page.screenshot(path="real_dialog2.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
