# -*- coding: utf-8 -*-
"""探测淘宝以图搜款入口（低频轻量，阿里系注意风控 P-039）（用后即删）"""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://www.taobao.com", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        print("URL:", page.url[:60], "| title:", page.title()[:40])

        info = page.evaluate("""() => {
            const out = {searchInputs: [], fileInputs: [], camera: [], imgSearchLinks: []};
            document.querySelectorAll('input').forEach(el=>{
                const t=el.getAttribute('type')||'';
                const ph=el.getAttribute('placeholder')||'';
                const cls=(el.getAttribute('class')||'');
                if (/搜索/.test(ph) || /search/i.test(cls)) out.searchInputs.push({ph, cls:cls.slice(0,40)});
                if (t==='file') out.fileInputs.push({cls:cls.slice(0,40), accept:el.getAttribute('accept'), visible:!!el.getBoundingClientRect().width});
            });
            // 相机/以图搜图标
            const kw=['camera','img-search','image-search','search-image','拍照','相机','识图','以图'];
            document.querySelectorAll('svg,i,img,[class*="camera"],[class*="img-search"],[class*="search-img"]').forEach(el=>{
                const cls=(el.getAttribute('class')||'').toLowerCase();
                const src=(el.getAttribute('src')||'').toLowerCase();
                const r=el.getBoundingClientRect();
                if (r.width>0 && r.height>0 && kw.some(k=>cls.includes(k)||src.includes(k))) {
                    out.camera.push({tag:el.tagName, cls:cls.slice(0,40), rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
                }
            });
            // 以图搜链接
            document.querySelectorAll('a[href*="image"],[href*="imgSearch"],[href*="s.taobao.com/image"]').forEach(el=>{
                out.imgSearchLinks.push({href:(el.getAttribute('href')||'').slice(0,80), txt:(el.textContent||'').trim().slice(0,10)});
            });
            return out;
        }""")
        print("searchInputs:", json.dumps(info["searchInputs"], ensure_ascii=False))
        print("fileInputs:", json.dumps(info["fileInputs"], ensure_ascii=False))
        print("camera:", json.dumps(info["camera"], ensure_ascii=False)[:300])
        print("imgSearchLinks:", json.dumps(info["imgSearchLinks"], ensure_ascii=False)[:300])
        page.screenshot(path="taobao_home.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
