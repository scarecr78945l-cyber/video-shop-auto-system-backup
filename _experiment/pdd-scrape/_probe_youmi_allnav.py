# -*- coding: utf-8 -*-
"""Dump ALL 有米云 nav hrefs to find 商品销售榜."""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    items = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('a[href]').forEach(a => {
            const t = (a.innerText||'').replace(/\\s+/g,' ').trim();
            const h = a.getAttribute('href')||'';
            if (t && h) out.push({t: t.slice(0,24), href: h.slice(0,80)});
        });
        return out;
    }""")
    seen = set()
    for it in items:
        k = it["t"] + it["href"]
        if k in seen:
            continue
        seen.add(k)
        print(it["t"], "=>", it["href"], flush=True)
finally:
    pw.stop()
