# -*- coding: utf-8 -*-
"""探测拼多多首页搜索框 + 相机/识图按钮（移动网页，用后即删）"""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://mobile.yangkeduo.com/", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(10000)
        print("URL:", page.url[:90])
        page.screenshot(path="pdd_home.png", full_page=False)

        # 找搜索框 + 相机/识图 + 所有 file input（含隐藏）+ 图标
        info = page.evaluate("""() => {
            const out = {searchInputs: [], fileInputs: [], cameraIcons: [], allIcons: []};
            document.querySelectorAll('input').forEach(el=>{
                const t=el.getAttribute('type')||'';
                const ph=el.getAttribute('placeholder')||'';
                const cls=(el.getAttribute('class')||'');
                if (/search|搜索/.test(ph) || /search/i.test(cls)) out.searchInputs.push({ph, cls:cls.slice(0,40), rect:`${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`});
                if (t==='file') out.fileInputs.push({cls:cls.slice(0,40), accept:el.getAttribute('accept'), visible:!!el.getBoundingClientRect().width});
            });
            // 相机/识图类图标（svg/i/img 带 camera/scan/pic）
            const kw=['camera','scan','识图','拍照','相册','以图','upload','img-search','pic-search'];
            document.querySelectorAll('svg, i, img, [class*="camera"], [class*="scan"], [class*="search-img"]').forEach(el=>{
                const cls=(el.getAttribute('class')||'').toLowerCase();
                const src=(el.getAttribute('src')||'').toLowerCase();
                const r=el.getBoundingClientRect();
                if (r.width>0 && r.height>0 && kw.some(k=>cls.includes(k)||src.includes(k))) {
                    out.cameraIcons.push({tag:el.tagName, cls:cls.slice(0,50), rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
                }
            });
            return out;
        }""")
        print("searchInputs:", json.dumps(info["searchInputs"], ensure_ascii=False))
        print("fileInputs:", json.dumps(info["fileInputs"], ensure_ascii=False))
        print("cameraIcons:", json.dumps(info["cameraIcons"], ensure_ascii=False))
    finally:
        page.close()
finally:
    pw.stop()
