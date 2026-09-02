# -*- coding: utf-8 -*-
"""进淘宝同款商品详情页扒多张主图（低频，用后即删）"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "pdd-scrape"

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        # 用第一个真正的锅刷同款（非内存条/显卡）
        items = json.loads((OUT / "taobao_same_items.json").read_text(encoding="utf-8"))
        brush = next((it for it in items if "锅刷" in it["title"] or "刷锅" in it["title"]), items[0])
        item_id = re.search(r"id=(\d+)", brush["href"]).group(1)
        print(f"进入同款商品: {brush['title'][:30]} id={item_id}")

        url = f"https://item.taobao.com/item.htm?id={item_id}"
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(10000)
        print("详情 URL:", page.url[:80], "| title:", page.title()[:50])

        # 提取主图（轮播）
        imgs = page.evaluate("""() => {
            const urls = [];
            // img 标签（大图）
            document.querySelectorAll('img').forEach(el => {
                const s = el.getAttribute('src') || el.getAttribute('data-src') || el.getAttribute('data-ks-lazyload') || '';
                const r = el.getBoundingClientRect();
                if (s && s.startsWith('http') && r.width > 150) urls.push(s);
            });
            // 页面 JS 里的主图数组（imgPicUrl / imageList / 等）
            const html = document.documentElement.outerHTML;
            const re = /"(?:imageUrl|imgPicUrl|picUrl|imageList|gallery)":[^"\\[]*\\[?[^]]*"https:[^"]+"/g;
            let m;
            while ((m = re.exec(html)) && urls.length < 15) {
                const mm = m[0].match(/https:[^"']+/g);
                if (mm) mm.forEach(u => { if (!urls.includes(u)) urls.push(u); });
            }
            // 常见图床字段
            const re2 = /"h[dt]?_thumb_url":\\s*"(https:[^"]+)"/g;
            while ((m = re2.exec(html)) && urls.length < 15) {
                if (!urls.includes(m[1])) urls.push(m[1]);
            }
            return [...new Set(urls)].slice(0, 12);
        }""")
        print(f"主图 {len(imgs)} 张")
        for i, u in enumerate(imgs[:8]):
            print(f"  [{i}] {u[:110]}")
        (OUT / f"taobao_{item_id}_main.json").write_text(
            json.dumps(imgs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已存: taobao_{item_id}_main.json")
    finally:
        page.close()
finally:
    pw.stop()
