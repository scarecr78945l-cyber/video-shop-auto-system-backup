# -*- coding: utf-8 -*-
"""关键词搜索验证：#22 公仔牌洗衣粉 淘宝关键词搜同款（用后即删）"""
import json
import re
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright

# 用户截图确认：关键词"公仔牌洗衣粉"精准。从商品标题提取品牌+品名核心词
TITLE = "公仔牌顽渍净洗衣粉轻松搓洗去污渍除菌除螨3倍洁净去渍家用去黄抖店"

def clean_keyword(title):
    t = re.sub(r"【[^】]*】", " ", title or "")
    t = re.sub(r"(价格带.*|抖店|官方|正品|同款|包邮|秒杀|爆款|轻松搓洗|去污|除菌|除螨|家用|去黄)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

KW = clean_keyword(TITLE)
print("关键词:", KW)

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        url = f"https://s.taobao.com/search?q={quote(KW)}"
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(9000)
        print("URL:", page.url[:80])

        items = page.evaluate("""() => {
            const out = [];
            const seen = new Set();
            document.querySelectorAll('a[href*="item.taobao.com"]').forEach(a => {
                const href = a.getAttribute('href') || '';
                const m = href.match(/item\\.taobao\\.com\\/item\\.htm\\?id=(\\d+)/);
                if (!m || seen.has(m[1])) return;
                seen.add(m[1]);
                const card = a.closest('[class*="item"],[class*="Card"],[class*="card"]') || a;
                out.push({id: m[1], title: (card.textContent||'').replace(/\\s+/g,' ').trim().slice(0,55)});
            });
            return out.slice(0, 12);
        }""")
        print(f"结果 {len(items)} 个")
        for it in items[:10]:
            print(f"  {it['id']} {it['title'][:45]}")
    finally:
        page.close()
finally:
    pw.stop()
