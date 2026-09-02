# -*- coding: utf-8 -*-
"""模拟拼多多 App UA → 访问识图 H5 → 找上传入口（用后即删）

拼多多 App 识图= WebView 加载 H5；用 CDP Network.setUserAgentOverride 伪装 App UA，
识图入口（相机/file input）可能因此出现（之前默认 UA 访问是空壳）。
"""
import json
from playwright.sync_api import sync_playwright

# 拼多多 Android App 典型 WebView UA
PDD_APP_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 "
    "pinduoduo/7.93.0 pddopenhybrid/9.3.0"
)

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        # 1) CDP 覆盖 UA
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.setUserAgentOverride", {"userAgent": PDD_APP_UA, "platform": "Android"})
        print("已伪装 UA:", PDD_APP_UA[:60], "...", flush=True)

        # 2) 访问识图 H5 候选页
        for route in [
            "https://mobile.yangkeduo.com/pic_search.html",
            "https://mobile.yangkeduo.com/visual_search.html",
            "https://mobile.yangkeduo.com/search_result.html?search_key=%E4%B8%8D%E9%94%88%E9%92%A2",
        ]:
            try:
                page.goto(route, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(8000)
                print(f"\nROUTE: {route.split('?')[0].split('/')[-1]}", flush=True)
                print("  final URL:", page.url[:80], flush=True)
                body = page.evaluate("() => document.body.innerText || ''")
                print(f"  正文长度: {len(body)}", flush=True)

                info = page.evaluate("""() => {
                    const out = {fileInputs: [], camera: [], uploadText: []};
                    document.querySelectorAll('input[type=file]').forEach(el=>{
                        out.fileInputs.push({cls:(el.getAttribute('class')||'').slice(0,40), accept:el.getAttribute('accept'), visible:!!el.getBoundingClientRect().width, rect:`${Math.round(el.getBoundingClientRect().width)}x${Math.round(el.getBoundingClientRect().height)}`});
                    });
                    const kw=['camera','识图','拍照','相册','以图','upload','scan','搜索同款','相似'];
                    document.querySelectorAll('svg,i,img,[class*="camera"],[class*="upload"],[class*="scan"]').forEach(el=>{
                        const cls=(el.getAttribute('class')||'').toLowerCase();
                        const src=(el.getAttribute('src')||'').toLowerCase();
                        const r=el.getBoundingClientRect();
                        if (r.width>0 && r.height>0 && kw.some(k=>cls.includes(k)||src.includes(k))) {
                            out.camera.push({tag:el.tagName, cls:cls.slice(0,40), rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
                        }
                    });
                    document.querySelectorAll('*').forEach(el=>{
                        const t=(el.textContent||'').trim();
                        const r=el.getBoundingClientRect();
                        if (r.width>0 && r.height>0 && t && t.length<12 && kw.some(k=>t.includes(k)) && el.children.length<=1) {
                            out.uploadText.push({tag:el.tagName, txt:t.slice(0,10)});
                        }
                    });
                    return out;
                }""")
                print("  fileInputs:", json.dumps(info["fileInputs"], ensure_ascii=False))
                print("  camera:", json.dumps(info["camera"], ensure_ascii=False)[:200])
                print("  uploadText:", json.dumps(info["uploadText"], ensure_ascii=False)[:200])
                page.screenshot(path=f"pdd_app_{route.split('?')[0].split('/')[-1]}.png", full_page=False)
            except Exception as e:
                print(f"  ERR: {str(e)[:80]}", flush=True)
    finally:
        page.close()
finally:
    pw.stop()
