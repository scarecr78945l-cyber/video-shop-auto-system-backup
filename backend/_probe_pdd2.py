# -*- coding: utf-8 -*-
"""探测拼多多搜索结果页 + 识图入口（用后即删）"""
import json
from urllib.parse import quote
from playwright.sync_api import sync_playwright

kw = quote("不锈钢锅刷")
pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].new_page()
    try:
        url = f"https://mobile.yangkeduo.com/search_result.html?search_key={kw}"
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        print("final URL:", page.url[:100])
        body = page.evaluate("() => document.body.innerText || ''")
        print("文本长度:", len(body))
        print("含'不锈钢锅刷':", '不锈钢锅刷' in body)
        # 找商品卡片
        cards = page.evaluate("""() => {
            const outs = [];
            document.querySelectorAll('a[href*="goods"], [class*="item"], [class*="goods"], [class*="card"]').forEach((el, i) => {
                if (i >= 10) return;
                const r = el.getBoundingClientRect();
                const href = el.getAttribute('href')||'';
                const t = (el.textContent||'').trim().slice(0, 40);
                if (r.width > 80 && r.height > 80) outs.push({tag: el.tagName, href: href.slice(0,60), t, rect:`${Math.round(r.width)}x${Math.round(r.height)}`});
            });
            return outs.slice(0, 10);
        }""")
        print("候选商品卡片:", len(cards))
        for c in cards[:5]:
            print(json.dumps(c, ensure_ascii=False))
        # 截图
        page.screenshot(path="_pdd_search.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
