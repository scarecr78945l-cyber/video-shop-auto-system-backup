# -*- coding: utf-8 -*-
"""淘宝详情页：从 JS 数据提主图数组（用后即删）"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "pdd-scrape"
ITEM_ID = "1053586196750"

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        url = f"https://item.taobao.com/item.htm?id={ITEM_ID}"
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(10000)

        # 读页面 HTML 里的主图相关 JS 数据
        html = page.evaluate("() => document.documentElement.outerHTML")
        print("HTML 长度:", len(html))

        # 多种主图字段
        patterns = [
            r'"imgfileList"\s*:\s*\[(.*?)\]',
            r'"imageList"\s*:\s*\[(.*?)\]',
            r'"mainPicUrl"\s*:\s*"(https:[^"]+)"',
            r'"picUrl"\s*:\s*"(https:[^"]+)"',
            r'"hpicUrl"\s*:\s*"(https:[^"]+)"',
            r'"items"\s*:\s*\[(.*?)\]',
        ]
        found = {}
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                found[pat[:25]] = m.group(1)[:400]

        # 用 js 直接找 window 数据里的图片 URL
        urls = page.evaluate("""() => {
            const set = new Set();
            // 遍历 window 常用数据对象
            const cands = [window.__INIT_DATA__, window.__INIT_TB_DATA__, window.INIT_DATA];
            for (const c of cands) {
                try {
                    const s = JSON.stringify(c);
                    const re = /https?:\\/\\/[^"']*\\.(?:jpg|jpeg|png|webp)[^"']*/g;
                    let m;
                    while ((m = re.exec(s)) && set.size < 15) {
                        if (!m[0].includes('tps-') || set.size < 2) set.add(m[0]);
                    }
                } catch(e) {}
            }
            return [...set];
        }""")
        print("\nJS 数据主图:", len(urls))
        for u in list(urls)[:8]:
            print("  ", u[:110])

        # 页面里所有含 alicdn 的大图（非 tps- logo）
        page_imgs = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('img').forEach(el => {
                const s = el.getAttribute('src') || el.getAttribute('data-src') || el.getAttribute('data-ks-lazyload') || '';
                if (s.includes('alicdn') && !s.includes('tps-') && s.length > 60) out.push(s);
            });
            return [...new Set(out)].slice(0, 10);
        }""")
        print("\n页面 alicdn 大图:", len(page_imgs))
        for u in page_imgs[:8]:
            print("  ", u[:110])
        page.screenshot(path="taobao_detail.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
