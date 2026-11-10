# -*- coding: utf-8 -*-
"""Diagnose: dump first board row structure (td count, text, links)."""
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
            const rows = document.querySelectorAll('.el-table__body-wrapper tr');
            const out = {rowCount: rows.length};
            if (rows.length) {
                const r = rows[0];
                const tds = r.querySelectorAll('td');
                out.tdCount = tds.length;
                out.tds = [...tds].slice(0,4).map(td => (td.innerText||'').trim().slice(0,40));
                out.links = [...r.querySelectorAll('a[href]')].slice(0,4).map(a => a.getAttribute('href'));
                out.bgCount = r.querySelectorAll('.ys-bg-img').length;
            }
            return out;
        }""")
        print(json.dumps(dump, ensure_ascii=False, indent=1), flush=True)
    finally:
        page.close()
finally:
    pw.stop()
