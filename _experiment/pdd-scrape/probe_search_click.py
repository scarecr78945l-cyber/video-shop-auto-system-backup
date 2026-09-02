# -*- coding: utf-8 -*-
"""探测：搜索页点击搜索框后是否出现相机/识图上传入口 + 页面 JS 里的 visual 能力（用后即删）"""
import json
from urllib.parse import quote
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        kw = quote("不锈钢锅刷")
        page.goto(f"https://mobile.yangkeduo.com/search_result.html?search_key={kw}", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)

        # 1) 找搜索框并点击（可能弹出识图入口）
        clicked = page.evaluate("""() => {
            const els = [...document.querySelectorAll('input, [class*="search"], [placeholder]')];
            const box = els.find(e => (e.getAttribute('placeholder')||'').includes('搜索') || /search/i.test(e.getAttribute('class')||''));
            if (box) { box.click(); return box.tagName + '.' + (box.getAttribute('class')||'').slice(0,40); }
            return 'no box';
        }""")
        print("点击搜索框:", clicked)
        page.wait_for_timeout(2500)

        # 2) 点击后再查 file input / 相机
        after = page.evaluate("""() => {
            const out = {fileInputs: [], camera: []};
            document.querySelectorAll('input[type=file]').forEach(el=>{
                out.fileInputs.push({cls:(el.getAttribute('class')||'').slice(0,40), accept:el.getAttribute('accept'), visible:!!el.getBoundingClientRect().width});
            });
            const kw=['camera','识图','拍照','相册','以图','upload','scan'];
            document.querySelectorAll('svg,i,img,[class*="camera"],[class*="upload"],[class*="scan"]').forEach(el=>{
                const cls=(el.getAttribute('class')||'').toLowerCase();
                const src=(el.getAttribute('src')||'').toLowerCase();
                const r=el.getBoundingClientRect();
                if (r.width>0 && r.height>0 && kw.some(k=>cls.includes(k)||src.includes(k))) {
                    out.camera.push({tag:el.tagName, cls:cls.slice(0,40), rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
                }
            });
            return out;
        }""")
        print("点击后 fileInputs:", json.dumps(after["fileInputs"], ensure_ascii=False))
        print("点击后 camera:", json.dumps(after["camera"], ensure_ascii=False))

        # 3) 页面 JS 里 visual / anti_content 相关全局
        js = page.evaluate("""() => {
            const out = {};
            const keys = Object.keys(window).filter(k => /visual|img|upload|search/i.test(k));
            out.windowKeys = keys.slice(0, 15);
            // 尝试找 window 上的识图入口函数
            out.hasAnti = !!(window.anti_content || window.__anti_content);
            return out;
        }""")
        print("window keys:", json.dumps(js, ensure_ascii=False))
    finally:
        page.close()
finally:
    pw.stop()
