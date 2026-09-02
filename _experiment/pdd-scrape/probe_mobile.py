# -*- coding: utf-8 -*-
"""手机 UA 访问淘宝：找识图入口（用后即删）"""
import json
from playwright.sync_api import sync_playwright

# 手机淘宝 H5 UA（含 App 特征）
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A.230805.001; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 "
    "TmallH5/1.0"
)

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        # 覆盖 UA
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.setUserAgentOverride", {"userAgent": MOBILE_UA, "platform": "Android"})

        for url in ["https://m.taobao.com/", "https://h5.m.taobao.com/", "https://www.taobao.com/"]:
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(8000)
                print(f"\n=== {url} → {page.url[:70]} ===", flush=True)
                info = page.evaluate("""() => {
                    const out = {fileInputs: [], camera: [], imgSearch: []};
                    document.querySelectorAll('input[type=file]').forEach(el=>{
                        out.fileInputs.push({cls:(el.getAttribute('class')||'').slice(0,40), accept:el.getAttribute('accept'), visible:!!el.getBoundingClientRect().width});
                    });
                    const kw=['camera','识图','拍照','相机','相册','以图','search-img','image-search','icon-camera'];
                    document.querySelectorAll('svg,i,img,[class*="camera"],[class*="search-img"],[class*="image-search"],[class*="scan"]').forEach(el=>{
                        const cls=(el.getAttribute('class')||'').toLowerCase();
                        const src=(el.getAttribute('src')||'').toLowerCase();
                        const r=el.getBoundingClientRect();
                        if (r.width>0 && r.height>0 && kw.some(k=>cls.includes(k)||src.includes(k))) {
                            out.camera.push({tag:el.tagName, cls:cls.slice(0,50), rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
                        }
                    });
                    return out;
                }""")
                print("fileInputs:", json.dumps(info["fileInputs"], ensure_ascii=False))
                print("camera:", json.dumps(info["camera"], ensure_ascii=False)[:250])
                page.screenshot(path=f"mobile_{url.split('/')[2]}.png", full_page=False)
                if info["fileInputs"] or info["camera"]:
                    break
            except Exception as e:
                print(f"{url} ERR {str(e)[:60]}")
    finally:
        page.close()
finally:
    pw.stop()
