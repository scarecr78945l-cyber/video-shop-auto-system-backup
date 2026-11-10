# -*- coding: utf-8 -*-
"""Probe video tab structure: find video cover image elements."""
import json
from playwright.sync_api import sync_playwright

GID = "73qZp4l-s~1d7w"

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto(f"https://console.youshu.youcloud.com/goods/{GID}/video", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        dump = page.evaluate("""() => {
            const out = {};
            out.videos = document.querySelectorAll('video').length;
            out.coverEls = [];
            // common video-cover patterns
            document.querySelectorAll('[class*="cover"],[class*="Cover"],[class*="video"],[class*="Video"],[class*="card"],[class*="Card"]').forEach(el => {
                if (out.coverEls.length > 6) return;
                const st = el.getAttribute('style')||'';
                const m = st.match(/url\\(\\s*["']?(https?:\\/\\/[^"')\\s]+)/);
                const img = el.querySelector('img');
                const bg = m ? m[1] : '';
                out.coverEls.push({
                    tag: el.tagName, cls: (el.className||'').toString().slice(0,40),
                    bg: bg.slice(0,90), imgSrc: img ? (img.getAttribute('src')||'').slice(0,90) : ''
                });
            });
            out.backgroundCount = document.querySelectorAll('[style*="background-image"], [style*="background"], .ys-bg-img').length;
            return out;
        }""")
        print(json.dumps(dump, ensure_ascii=False, indent=1)[:2500], flush=True)
    finally:
        page.close()
finally:
    pw.stop()
