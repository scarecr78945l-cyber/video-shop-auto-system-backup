# -*- coding: utf-8 -*-
"""Probe 有米云 商品销售榜: row structure, image count, product detail link."""
import json
import sys
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        end = date.today()
        start = end - timedelta(days=7)
        url = (f"https://console.youshu.youcloud.com/goods/sale?site_id=10502"
               f"&startDate={start.isoformat()}&endDate={end.isoformat()}")
        print("navigating:", url, flush=True)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        print("url now:", page.url[:90], flush=True)
        info = page.evaluate("""() => {
            const rows = document.querySelectorAll('.el-table__body-wrapper tr');
            const out = {rowCount: rows.length, firstRow: null};
            if (rows.length) {
                const r = rows[0];
                const tds = r.querySelectorAll('td');
                const imgs = r.querySelectorAll('.ys-bg-img');
                const bgUrls = [...imgs].slice(0,5).map(el => {
                    const st = el.getAttribute('style')||'';
                    const m = st.match(/url\\(\\s*["']?(https?:\\/\\/[^"')\\s]+)/);
                    return m ? m[1] : (el.className||'').slice(0,30);
                });
                const links = [...r.querySelectorAll('a[href]')].slice(0,4).map(a => ({
                    t: (a.innerText||'').slice(0,24), h: a.getAttribute('href')||''
                }));
                out.firstRow = {
                    tdCount: tds.length,
                    text: (r.innerText||'').replace(/\\s+/g,' ').slice(0,120),
                    bgImgCount: imgs.length, bgUrls,
                    links
                };
            }
            return out;
        }""")
        print(json.dumps(info, ensure_ascii=False, indent=1), flush=True)
    finally:
        page.close()
finally:
    pw.stop()
