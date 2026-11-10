# -*- coding: utf-8 -*-
"""Probe a product detail (overview/leaflet/video) image counts to size up deep collection."""
import json
from playwright.sync_api import sync_playwright

GID = "ug5TtTXqIKfOx3-Y2aT3Rg=="

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        for tab, path in [("overview", "/overview"), ("leaflet", "/leaflet"), ("video", "/video")]:
            url = f"https://console.youshu.youcloud.com/goods/{GID}{path}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(7000)
                info = page.evaluate("""() => {
                    const urls = new Set();
                    document.querySelectorAll('img, .ys-bg-img').forEach(el => {
                        let u = el.getAttribute('src')||'';
                        if (!u) { const st = el.getAttribute('style')||''; const m = st.match(/url\\(\\s*["']?(https?:\\/\\/[^"')\\s]+)/); u = m ? m[1] : ''; }
                        if (u && u.startsWith('http') && !u.includes('data:') && u.length > 40) urls.add(u);
                    });
                    const videos = [...document.querySelectorAll('video')].length;
                    const title = (document.title||'');
                    return {title, imgCount: urls.size, sampleUrls: [...urls].slice(0,8),
                            videoTags: videos,
                            hasMainImg: !!document.querySelector('[class*="main"], [class*="Main"] img, .el-image')};
                }""")
                print(f"=== {tab} ===", flush=True)
                print(json.dumps(info, ensure_ascii=False, indent=1)[:1800], flush=True)
            except Exception as e:
                print(f"=== {tab} ERR {type(e).__name__}: {str(e)[:80]} ===", flush=True)
    finally:
        page.close()
finally:
    pw.stop()
