# -*- coding: utf-8 -*-
"""淘宝以图搜款：detail_0 图上传 → 同款结果（低频，用后即删）"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path(__file__).resolve().parent.parent.parent / "backend" / "data" / "images" / "listing" / "1" / "detail_0.png"
print("图片:", IMG, "存在:", IMG.exists())

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://s.taobao.com/image", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        print("URL:", page.url[:60], "| title:", page.title()[:40])

        # 找上传 file input 并 set_input_files
        fi = page.locator("input[type=file]").first
        print("file input count:", page.locator("input[type=file]").count())
        fi.set_input_files(str(IMG), timeout=30000)
        print("已上传 detail_0.png，等待识图结果...")
        page.wait_for_timeout(12000)

        print("当前 URL:", page.url[:80])
        # 结果页商品
        items = page.evaluate("""() => {
            const out = [];
            const body = document.body.innerText || '';
            out.push({bodyLen: body.length, hasLogin: body.includes('登录')});
            // 商品卡
            document.querySelectorAll('[class*="item"],[class*="Card"],[class*="card"],[data-itemid]').forEach(el=>{
                const r=el.getBoundingClientRect();
                if (r.width>150 && r.height>150) {
                    out.push({tag:el.tagName, cls:(el.getAttribute('class')||'').slice(0,50), rect:`${Math.round(r.width)}x${Math.round(r.height)}`, dataId:(el.getAttribute('data-itemid')||'').slice(0,20)});
                }
            });
            return out.slice(0, 15);
        }""")
        print("结果:", json.dumps(items, ensure_ascii=False)[:600])
        page.screenshot(path="taobao_image_search_result.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
