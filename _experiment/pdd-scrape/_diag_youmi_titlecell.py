# -*- coding: utf-8 -*-
"""Probe board title cell inner structure to extract clean product title."""
import json
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        end = date.today(); start = end - timedelta(days=7)
        page.goto(f"https://console.youshu.youcloud.com/goods/sale?site_id=10502"
                  f"&startDate={start.isoformat()}&endDate={end.isoformat()}",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)
        dump = page.evaluate("""() => {
            const r = document.querySelector('.el-table__body-wrapper tr');
            if (!r) return {err:'no row'};
            const bgTd = [...r.querySelectorAll('td')].find(td => td.querySelector('.ys-bg-img'));
            if (!bgTd) return {err:'no bg td', rowText: r.innerText.slice(0,120)};
            const info = {tdText: bgTd.innerText.replace(/\\s+/g,' ').slice(0,150)};
            // sub-elements
            info.els = [...bgTd.querySelectorAll('div,span,a,img,p')].slice(0,15).map(el => ({
                tag: el.tagName, cls: (el.className||'').toString().slice(0,30),
                text: (el.innerText||'').trim().slice(0,30),
                alt: el.getAttribute('alt')||'', title: el.getAttribute('title')||''
            }));
            return info;
        }""")
        print(json.dumps(dump, ensure_ascii=False, indent=1)[:2500], flush=True)
    finally:
        page.close()
finally:
    pw.stop()
