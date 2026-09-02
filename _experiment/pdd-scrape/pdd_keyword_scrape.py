# -*- coding: utf-8 -*-
"""拼多多：关键词搜同款 → 第一个商品详情 → 扒主图（用后即删）"""
import json
import re
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "pdd-scrape"
OUT.mkdir(exist_ok=True)


def main():
    keyword = "不锈钢锅刷"
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            # 1) 关键词搜索
            url = f"https://mobile.yangkeduo.com/search_result.html?search_key={quote(keyword)}"
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(9000)

            # 提取商品 ID：从 DOM / JS 数据
            ids = page.evaluate("""() => {
                const set = new Set();
                // DOM 里 data 属性
                document.querySelectorAll('[data-goods-id], [goods_id], [data-id]').forEach(el=>{
                    const v = el.getAttribute('data-goods-id')||el.getAttribute('goods_id')||el.getAttribute('data-id');
                    if (v && v.length>8) set.add(v);
                });
                // 页面 html 里 goods_id 数字
                const html = document.documentElement.outerHTML;
                const re = /goods_id=(\\d{10,})/g; let m;
                while ((m=re.exec(html)) && set.size<8) set.add(m[1]);
                return [...set];
            }""")
            print("商品 ID:", ids)
            if not ids:
                print("未取到商品 ID")
                return

            gid = ids[0]
            print(f"第一个商品: {gid}")

            # 2) 打开详情页
            detail_url = f"https://mobile.yangkeduo.com/goods.html?goods_id={gid}"
            page.goto(detail_url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(9000)
            print("详情URL:", page.url[:80], "| title:", page.title()[:40])

            # 3) 提取主图数组（img 大图 + JS 字段）
            imgs = page.evaluate("""() => {
                const urls = [];
                document.querySelectorAll('img').forEach(el=>{
                    const s = el.getAttribute('src')||el.getAttribute('data-src')||'';
                    const r = el.getBoundingClientRect();
                    if (s && s.startsWith('http') && s.length>40) urls.push(s);
                });
                const html = document.documentElement.outerHTML;
                const re = /"(?:hd_thumb_url|thumb_url|imageUrl|hdThumbUrl|gallery)":\\s*"([^"]{40,})"/g;
                let m; 
                while ((m=re.exec(html)) && urls.length<20) { if(!urls.includes(m[1])) urls.push(m[1]); }
                return [...new Set(urls)];
            }""")
            print(f"主图 {len(imgs)} 张")
            for i, u in enumerate(imgs[:8]):
                print(f"  [{i}] {u[:110]}")
            (OUT / f"{gid}_main_images.json").write_text(
                json.dumps(imgs, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"已存: {OUT / f'{gid}_main_images.json'}")

            # 4) 商品标题
            title = page.evaluate("() => document.title")
            print("商品标题:", title[:60])
        finally:
            page.close()
    finally:
        pw.stop()


if __name__ == "__main__":
    main()
