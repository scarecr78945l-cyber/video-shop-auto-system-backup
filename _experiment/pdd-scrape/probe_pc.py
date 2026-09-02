# -*- coding: utf-8 -*-
"""探测拼多多 PC 桌面版（www.pinduoduo.com）：搜索框 + 相机/识图上传入口（用后即删）"""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://www.pinduoduo.com/", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(10000)
        print("URL:", page.url[:80])
        page.screenshot(path="pdd_pc.png", full_page=False)

        info = page.evaluate("""() => {
            const out = {searchInputs: [], fileInputs: [], camera: [], upload: []};
            document.querySelectorAll('input').forEach(el=>{
                const t=el.getAttribute('type')||'';
                const ph=el.getAttribute('placeholder')||'';
                const cls=(el.getAttribute('class')||'');
                if (/搜索/.test(ph) || /search/i.test(cls)) out.searchInputs.push({ph, cls:cls.slice(0,40), rect:`${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`});
                if (t==='file') out.fileInputs.push({cls:cls.slice(0,40), accept:el.getAttribute('accept'), visible:!!el.getBoundingClientRect().width});
            });
            const kw=['camera','识图','拍照','相册','以图','upload','scan','img-search'];
            document.querySelectorAll('svg,i,img,[class*="camera"],[class*="upload"],[class*="scan"]').forEach(el=>{
                const cls=(el.getAttribute('class')||'').toLowerCase();
                const src=(el.getAttribute('src')||'').toLowerCase();
                const r=el.getBoundingClientRect();
                if (r.width>0 && r.height>0 && kw.some(k=>cls.includes(k)||src.includes(k))) {
                    out.camera.push({tag:el.tagName, cls:cls.slice(0,40), rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
                }
            });
            // 页面上含"识图/以图/拍照"文本的可点击元素
            const kw2=['以图','识图','拍照','搜索同款','找同款','相似'];
            document.querySelectorAll('*').forEach(el=>{
                const t=(el.textContent||'').trim();
                const r=el.getBoundingClientRect();
                if (r.width>0 && r.height>0 && t && t.length<12 && kw2.some(k=>t.includes(k)) && el.children.length<=1) {
                    out.upload.push({tag:el.tagName, txt:t.slice(0,10), cls:(el.getAttribute('class')||'').slice(0,40)});
                }
            });
            return out;
        }""")
        print("searchInputs:", json.dumps(info["searchInputs"], ensure_ascii=False))
        print("fileInputs:", json.dumps(info["fileInputs"], ensure_ascii=False))
        print("camera:", json.dumps(info["camera"], ensure_ascii=False))
        print("upload文本:", json.dumps(info["upload"], ensure_ascii=False))
    finally:
        page.close()
finally:
    pw.stop()
