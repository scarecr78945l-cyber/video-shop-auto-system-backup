# -*- coding: utf-8 -*-
"""拼多多搜索同款 → 进第一个商品 → 扒主图（独立目录 _experiment/pdd-scrape/，用后即删）

流程：关键词搜索 → 结果第一商品 → 详情页 → 提取主图数组。
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "pdd-scrape"
OUT.mkdir(exist_ok=True)


def search_first(page, keyword: str):
    """搜索关键词，返回结果中第一个商品链接/ID。"""
    url = f"https://mobile.yangkeduo.com/search_result.html?search_key={quote(keyword)}"
    page.goto(url, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    print("搜索 URL:", page.url[:80])
    print("标题:", page.title()[:40])

    # 找商品链接（goods_id 或 /goods.html?goods_id=）
    ids = page.evaluate("""() => {
        const outs = [];
        document.querySelectorAll('a[href*="goods"], [data-goods-id], [goods_id]').forEach(el => {
            const href = el.getAttribute('href') || '';
            const m = href.match(/goods_id=(\\d+)/) || href.match(/goods\\.html\\?(\\d+)/);
            const gid = m ? m[1] : (el.getAttribute('data-goods-id') || '');
            if (gid) outs.push(gid);
        });
        // 页面文本里找 goods_id 数字
        if (!outs.length) {
            const body = page.document.documentElement.outerHTML;
            const re = /goods_id=(\\d{10,})/g;
            let m; const set = new Set();
            while ((m = re.exec(body)) && set.size < 5) set.add(m[1]);
            return [...set];
        }
        return [...new Set(outs)].slice(0, 5);
    }""")
    print("候选商品 ID:", ids)
    return ids[0] if ids else None


def scrape_goods_images(page, goods_id: str):
    """打开商品详情页，提取主图数组。"""
    url = f"https://mobile.yangkeduo.com/goods.html?goods_id={goods_id}"
    page.goto(url, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    print("详情 URL:", page.url[:80])
    print("标题:", page.title()[:50])

    imgs = page.evaluate("""() => {
        const urls = [];
        // 1) img 标签大图
        document.querySelectorAll('img').forEach(el => {
            const src = el.getAttribute('src') || el.getAttribute('data-src') || '';
            if (src && src.startsWith('http') && src.length > 40) urls.push(src);
        });
        // 2) JS 数据主图字段（拼接 window 原始数据）
        const html = document.documentElement.outerHTML;
        const re = /"(?:hd_thumb_url|thumb_url|imageUrl|hdThumbUrl)":\\s*"([^"]{40,})"/g;
        let m;
        while ((m = re.exec(html)) && urls.length < 20) {
            if (!urls.includes(m[1])) urls.push(m[1]);
        }
        return [...new Set(urls)];
    }""")
    print(f"提取到 {len(imgs)} 张图")
    return imgs


def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else "不锈钢锅刷"
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        page = browser.contexts[0].new_page()
        try:
            gid = search_first(page, keyword)
            if not gid:
                print("未找到商品（可能仍未登录/风控）")
                return
            print(f"\n第一个商品 ID: {gid}")
            imgs = scrape_goods_images(page, gid)
            # 保存主图列表
            (OUT / f"{gid}_images.json").write_text(
                json.dumps(imgs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"主图列表已存: {OUT / f'{gid}_images.json'}")
            for i, u in enumerate(imgs[:6]):
                print(f"  [{i}] {u[:100]}")
        finally:
            page.close()
    finally:
        pw.stop()


if __name__ == "__main__":
    main()
