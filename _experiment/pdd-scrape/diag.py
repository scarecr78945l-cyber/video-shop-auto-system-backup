# -*- coding: utf-8 -*-
"""精准诊断：网页淘宝以图搜款完整流程 + 抓识图请求（定位卡点）（用后即删）"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path("data/tmp_taobao_input/22_1688.jpg")

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        # 抓所有 POST + 图片搜索相关请求
        posts = []
        page.on("request", lambda r: posts.append({
            "url": r.url[:140], "method": r.method,
            "post": (r.post_data or "")[:150]
        }) if (r.method == "POST" or any(k in r.url for k in ["image", "imgfile", "search", "upload", "pict", "s.taobao"])) else None)

        # 检查 webdriver 特征（淘宝可能检测）
        wd = page.evaluate("() => navigator.webdriver")
        print("navigator.webdriver:", wd, flush=True)

        page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(7000)

        # 真实点击相机图标（点击打开上传弹层）
        cam = page.locator("[class*='image-search-icon-wrapper']").first
        print("相机图标:", cam.count(), flush=True)
        cam.hover(timeout=5000)
        page.wait_for_timeout(1000)
        cam.click(timeout=5000)
        page.wait_for_timeout(3000)
        page.screenshot(path="diag_after_cam.png", full_page=False)

        # 点击后看页面结构（弹层？上传按钮？file input 是否激活）
        after = page.evaluate("""() => {
            const out = {fileInputs: [], uploadText: [], visible: []};
            document.querySelectorAll('input[type=file]').forEach(el=>{
                out.fileInputs.push({visible:!!el.getBoundingClientRect().width, accept:el.getAttribute('accept')});
            });
            document.querySelectorAll('*').forEach(el=>{
                const t=(el.textContent||'').trim();
                const r=el.getBoundingClientRect();
                if (r.width>0 && r.height>0 && t && t.length<10 && /上传|选择|本地图片|浏览/.test(t)) {
                    out.uploadText.push({tag:el.tagName, txt:t, cls:(el.getAttribute('class')||'').slice(0,40)});
                }
            });
            return out;
        }""")
        print("点击后 fileInputs:", json.dumps(after["fileInputs"], ensure_ascii=False), flush=True)
        print("点击后 uploadText:", json.dumps(after["uploadText"], ensure_ascii=False)[:250], flush=True)

        # 找"上传/选择"按钮并真实点击（触发文件选择器）
        upload_btn = None
        for sel in ["text=本地上传", "text=选择图片", "text=上传图片", "[class*='upload'] button", "[class*='upload'] a", "[class*='upload'] div"]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=1500):
                    upload_btn = loc
                    print("找到上传按钮:", sel, flush=True)
                    break
            except Exception:
                continue

        # 用文件选择器事件（真人流程：点按钮 → 系统选文件）
        try:
            with page.expect_file_chooser(timeout=8000) as fc_info:
                if upload_btn:
                    upload_btn.click(timeout=5000)
                else:
                    # 无按钮：直接对 file input 操作但先触发其 click
                    page.locator("input[type=file]").first.evaluate("el => el.click()")
            fc = fc_info.value
            print("文件选择器触发! 设置:", IMG.name, flush=True)
            fc.set_files(str(IMG))
        except Exception as e:
            print(f"文件选择器未触发: {str(e)[:80]}", flush=True)
            # 兜底直接 set
            page.locator("input[type=file]").first.set_input_files(str(IMG), timeout=30000)
            print("兜底 set_input_files", flush=True)

        # 等待识别 + 抓请求
        print("等待识别...", flush=True)
        for i in range(15):
            page.wait_for_timeout(1500)
            if "s.taobao" in page.url or "search" in page.url:
                print(f"  t+{(i+1)*1.5:.0f}s 跳转: {page.url[:90]}", flush=True)
                break
        print("最终 URL:", page.url[:90], flush=True)

        print(f"\n=== 捕获请求 {len(posts)} ===")
        for p in posts[-20:]:
            print(json.dumps(p, ensure_ascii=False))
        page.screenshot(path="diag_final.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
