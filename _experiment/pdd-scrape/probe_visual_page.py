# -*- coding: utf-8 -*-
"""探测 visual_search 页：完整 DOM（含隐藏 file input / 相机按钮）（用后即删）"""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].new_page()
    try:
        page.goto("https://mobile.yangkeduo.com/visual_search.html", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(12000)
        print("URL:", page.url[:90])
        page.screenshot(path="pdd_visual.png", full_page=False)

        # 全量探测 file input / 相机语义 / 上传按钮（含隐藏）
        info = page.evaluate("""() => {
            const outs = {fileInputs: [], cameraBtns: [], uploadBtns: []};
            document.querySelectorAll('input').forEach(el=>{
                const t=el.getAttribute('type')||'';
                const cls=(el.getAttribute('class')||'');
                if (t==='file' || /upload|pic|img/i.test(cls)) {
                    outs.fileInputs.push({type:t, cls:cls.slice(0,50), accept:el.getAttribute('accept'), visible:!!(el.getBoundingClientRect().width)});
                }
            });
            const kw=['camera','识图','拍照','传图','以图','上传图片','拍一拍','相册','upload'];
            document.querySelectorAll('*').forEach(el=>{
                const cls=(el.getAttribute('class')||'');
                const txt=(el.textContent||'').trim();
                const hit=kw.some(k=>cls.toLowerCase().includes(k.toLowerCase())||txt===k||(txt.length<8&&txt.includes(k)));
                const r=el.getBoundingClientRect();
                if (hit && r.width>0 && r.height>0 && el.children.length<=2) {
                    outs.cameraBtns.push({tag:el.tagName, cls:cls.slice(0,50), txt:txt.slice(0,10), rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
                }
            });
            // 去重
            outs.cameraBtns = outs.cameraBtns.slice(0, 15);
            return outs;
        }""")
        print("=== file inputs ===")
        for f in info["fileInputs"]:
            print(json.dumps(f, ensure_ascii=False))
        print("=== 相机/上传按钮 ===")
        for c in info["cameraBtns"]:
            print(json.dumps(c, ensure_ascii=False))
    finally:
        page.close()
finally:
    pw.stop()
