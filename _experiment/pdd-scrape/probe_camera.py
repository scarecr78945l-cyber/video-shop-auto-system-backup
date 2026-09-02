# -*- coding: utf-8 -*-
"""探测：搜索页 UI（找拍照/识图入口）+ 触发图片搜索（用后即删）"""
import json
from urllib.parse import quote
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].new_page()
    try:
        kw = quote("不锈钢锅刷")
        page.goto(f"https://mobile.yangkeduo.com/search_result.html?search_key={kw}", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        page.screenshot(path="pdd_ui.png", full_page=False)

        # 找相机/识图/搜索框结构
        info = page.evaluate("""() => {
            const outs = [];
            const kw = ['camera','visual','img-search','image-search','识图','拍照','相机','扫一扫','以图'];
            document.querySelectorAll('input,button,[class*="camera"],[class*="visual"],[class*="img"],[class*="search"] i,svg,[class*="icon"]').forEach((el,i)=>{
                if (i>60) return;
                const cls=(el.getAttribute('class')||'');
                const txt=(el.textContent||'').trim().slice(0,12);
                const r=el.getBoundingClientRect();
                const hit=kw.some(k=>(cls+txt).toLowerCase().includes(k.toLowerCase()));
                if (hit && r.width>0 && r.height>0) outs.push({tag:el.tagName,cls:cls.slice(0,50),txt,rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
            });
            // 所有 input[type=file]
            const files=[];
            document.querySelectorAll('input[type=file]').forEach(el=>{files.push({cls:(el.getAttribute('class')||'').slice(0,40),accept:el.getAttribute('accept')});});
            return {candidates: outs.slice(0,12), fileInputs: files};
        }""")
        print("=== 相机/识图候选 ===")
        for c in info["candidates"]:
            print(json.dumps(c, ensure_ascii=False))
        print("file inputs:", info["fileInputs"])
    finally:
        page.close()
finally:
    pw.stop()
