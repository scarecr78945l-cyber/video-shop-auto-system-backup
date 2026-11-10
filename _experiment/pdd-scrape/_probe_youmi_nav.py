# -*- coding: utf-8 -*-
"""Probe 有米云: full sidebar nav + find 商品销售榜 path."""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    # all clickable nav items with hrefs
    info = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('a[href], [class*="menu-item"], [class*="nav-item"]').forEach(a => {
            const t = (a.innerText||'').replace(/\\s+/g,' ').trim();
            const h = a.getAttribute('href')||'';
            if (t) out.push({t: t.slice(0,20), href: h.slice(0,60)});
        });
        return out.slice(0,60);
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=0)[:2500], flush=True)
finally:
    pw.stop()
