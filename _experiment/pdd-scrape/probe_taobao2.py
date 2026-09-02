# -*- coding: utf-8 -*-
"""深挖淘宝以图搜：搜索框相机按钮 + 识图独立页（低频，用后即删）"""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://www.taobao.com", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # 1) 聚焦搜索框 → 相机图标是否出现
        page.evaluate("""() => {
            const box = document.querySelector('input[class*="imageSearch"]') || document.querySelector('input[class*="search"]');
            if (box) box.focus();
        }""")
        page.wait_for_timeout(2000)
        after = page.evaluate("""() => {
            const out = [];
            const kw=['camera','img-search','image-search','icon-camera','拍照','相机','识图','图搜','imageSearch'];
            document.querySelectorAll('[class*="imageSearch"],[class*="img-search"],[class*="camera"],[class*="search-btn"],svg,i,[class*="icon"]').forEach(el=>{
                const cls=(el.getAttribute('class')||'').toLowerCase();
                const r=el.getBoundingClientRect();
                if (r.width>0 && r.height>0 && kw.some(k=>cls.includes(k))) {
                    out.push({tag:el.tagName, cls:cls.slice(0,50), rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
                }
            });
            return out.slice(0, 12);
        }""")
        print("聚焦后 imageSearch/相机 元素:")
        for a in after:
            print(json.dumps(a, ensure_ascii=False))
        page.screenshot(path="taobao_focus.png", full_page=False)
    finally:
        page.close()

    # 2) 淘宝识图独立页
    for url in ["https://shitu.taobao.com/", "https://s.taobao.com/image"]:
        page = ctx.new_page()
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            print(f"\n识图页 {url} → URL={page.url[:60]} title={page.title()[:40]}")
            info = page.evaluate("""() => {
                const out = {fileInputs: [], uploadBtns: []};
                document.querySelectorAll('input[type=file]').forEach(el=>{
                    out.fileInputs.push({cls:(el.getAttribute('class')||'').slice(0,40), accept:el.getAttribute('accept'), visible:!!el.getBoundingClientRect().width, rect:`${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`});
                });
                document.querySelectorAll('*').forEach(el=>{
                    const t=(el.textContent||'').trim();
                    const r=el.getBoundingClientRect();
                    if (r.width>0 && r.height>0 && t && t.length<12 && /上传|选择图片|本地图片|识图|搜索/.test(t) && el.children.length<=1) {
                        out.uploadBtns.push({tag:el.tagName, txt:t.slice(0,10), cls:(el.getAttribute('class')||'').slice(0,40)});
                    }
                });
                return out;
            }""")
            print("fileInputs:", json.dumps(info["fileInputs"], ensure_ascii=False))
            print("uploadBtns:", json.dumps(info["uploadBtns"], ensure_ascii=False)[:200])
        except Exception as e:
            print(f"识图页 {url} ERR: {str(e)[:70]}")
        finally:
            page.close()
finally:
    pw.stop()
