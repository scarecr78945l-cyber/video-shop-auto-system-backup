# -*- coding: utf-8 -*-
"""Probe 有米云 UI (CDP 9566, user's live window): sidebar links + current page structure."""
import json
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    print("current url:", page.url, flush=True)
    print("title:", page.title(), flush=True)
    info = page.evaluate("""() => {
        const out = {};
        // sidebar nav links
        out.sidebar = [...document.querySelectorAll('a, .el-menu-item, [class*="menu-item"]')].slice(0,40)
            .map(a => (a.innerText||'').trim()).filter(Boolean).slice(0,30);
        // search inputs
        out.inputs = [...document.querySelectorAll('input')].map(i => ({
            ph: i.getAttribute('placeholder')||'', cls: (i.className||'').toString().slice(0,40)
        })).slice(0,15);
        // card structure
        out.cardCount = document.querySelectorAll('[class*="card"], [class*="Card"], [class*="item"], [class*="Item"]').length;
        out.images = [...document.querySelectorAll('img')].slice(0,5).map(i => (i.getAttribute('src')||'').slice(0,90));
        return out;
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1)[:2000], flush=True)
finally:
    pw.stop()
