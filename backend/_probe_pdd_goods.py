# -*- coding: utf-8 -*-
"""探测：拼多多商品详情页主图结构（不登录直接访问 goods.html，用后即删）"""
import json
import re
from playwright.sync_api import sync_playwright

# 随便一个拼多多商品 ID（先探测结构，后续用搜索结果的真实 ID）
GOODS_ID = "100061265081"
pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].new_page()
    try:
        url = f"https://mobile.yangkeduo.com/goods.html?goods_id={GOODS_ID}"
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        print("final URL:", page.url[:90])
        print("title:", page.title()[:60])

        # 1) 页内 img 主图（轮播）
        imgs = page.evaluate("""() => {
            const outs = [];
            document.querySelectorAll('img').forEach((el, i) => {
                if (i > 25) return;
                const src = el.getAttribute('src') || el.getAttribute('data-src') || '';
                const r = el.getBoundingClientRect();
                if (src && r.width > 200 && r.height > 200) {
                    outs.push({i, src: src.slice(0, 120), rect: `${Math.round(r.width)}x${Math.round(r.height)}`});
                }
            });
            return outs;
        }""")
        print(f"\n页内大图: {len(imgs)}")
        for im in imgs[:6]:
            print(json.dumps(im, ensure_ascii=False))

        # 2) JS 数据里的主图数组（window.rawData / goods 数据）
        data = page.evaluate("""() => {
            const hits = {};
            const keys = ['hd_thumb_url', 'thumb_url', 'imageUrl', 'gallery', 'main_image', 'hdThumbUrl', 'image_url'];
            for (const k of keys) {
                const re = new RegExp('"' + k + '":\\s*"([^"]+)"', 'g');
                let m, arr = [];
                while ((m = re.exec(document.documentElement.outerHTML)) && arr.length < 4) arr.push(m[1]);
                if (arr.length) hits[k] = arr;
            }
            return hits;
        }""")
        print("\nJS 数据主图字段:")
        for k, v in data.items():
            print(f"  {k}: {v[:3]}")

        # 3) 页面截图
        page.screenshot(path="_pdd_goods.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
