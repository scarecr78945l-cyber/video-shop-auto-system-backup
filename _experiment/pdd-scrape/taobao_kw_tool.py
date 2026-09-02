# -*- coding: utf-8 -*-
"""淘宝同款主图工具（固化 v2）：关键词搜索 → 第一个同款 → 详情页扒主图（用后即删验收版）

用户指正（P-045）：淘宝找同款用**关键词搜索**即可精准，不必以图搜款。
流程：商品标题 → 清洗提核心词 → s.taobao.com/search → 第一个同款 → 详情页主图 → 下载。
"""
import json
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
MAIN_IMAGES = HERE.parent.parent / "backend" / "data" / "images" / "listing"
RESULT_JSON = HERE / "taobao_kw_results.jsonl"
INTERVAL = 8  # 秒，防阿里风控

# 待验收 3 个商品（标题来自 DB）
PRODUCTS = {
    1: "不锈钢锅刷不伤锅具去污柔韧耐用长柄可挂式厨房清洁刷",
    22: "公仔牌顽渍净洗衣粉轻松搓洗去污渍除菌除螨3倍洁净去渍家用去黄",
    40: "学生隐形错题胶带透明隐形胶带可书写无痕不留胶修补胶带装饰胶布",
}


def clean_keyword(title):
    t = re.sub(r"【[^】]*】", " ", title or "")
    t = re.sub(r"(价格带.*|抖店|官方|正品|同款|包邮|秒杀|爆款|轻松搓洗|去污|除菌|除螨|家用|去黄|多功能|专用|神器)", " ", t)
    t = re.sub(r"[a-zA-Z0-9\-_·，。！!、]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # 若清洗后太短（<3字），回退用前 12 字
    if len(t) < 3:
        t = re.sub(r"\s+", " ", title).strip()[:12]
    return t


def scrape_one(page, pid, title):
    kw = clean_keyword(title)
    rec = {"pid": pid, "kw": kw}
    print(f"=== #{pid} 关键词「{kw}」===", flush=True)

    # 1) 关键词搜索
    page.goto(f"https://s.taobao.com/search?q={quote(kw)}", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)

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
        return out.slice(0, 10);
    }""")
    rec["related"] = len(items)
    if not items:
        rec["error"] = "NO_MATCH"
        return rec
    first = items[0]
    rec["first_id"] = first["id"]
    rec["first_title"] = first["title"][:40]
    print(f"  同款 {len(items)} → 第一个 id={first['id']} {first['title'][:30]}", flush=True)

    # 2) 详情页扒主图
    page.goto(f"https://item.taobao.com/item.htm?id={first['id']}", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)
    urls = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('img').forEach(el => {
            const s = el.getAttribute('src') || el.getAttribute('data-src') || el.getAttribute('data-ks-lazyload') || '';
            if (s.includes('alicdn') && !s.includes('tps-') && s.length > 60) out.push(s);
        });
        return [...new Set(out)].slice(0, 8);
    }""")
    rec["main_count"] = len(urls)
    print(f"  详情页主图 {len(urls)} 张", flush=True)

    # 3) 下载前 5 张
    out_dir = MAIN_IMAGES / str(pid)
    out_dir.mkdir(parents=True, exist_ok=True)
    dl_ok = 0
    for i, u in enumerate(urls[:5]):
        full = "https:" + u if u.startswith("//") else u
        ext = ".webp" if "webp" in full else ".jpg"
        dest = out_dir / f"tb_main_{i}{ext}"
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://item.taobao.com/"})
            data = urllib.request.urlopen(req, timeout=15).read()
            if len(data) > 2000:
                dest.write_bytes(data)
                dl_ok += 1
        except Exception as e:
            print(f"    下载[{i}] ERR {str(e)[:40]}", flush=True)
    rec["downloaded"] = dl_ok
    print(f"  下载 {dl_ok} 张 → {out_dir}", flush=True)
    return rec


def main():
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            for i, (pid, title) in enumerate(PRODUCTS.items()):
                rec = scrape_one(page, pid, title)
                with open(RESULT_JSON, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if i < len(PRODUCTS) - 1:
                    print(f"  间隔 {INTERVAL}s ...", flush=True)
                    time.sleep(INTERVAL)
        finally:
            page.close()
    finally:
        pw.stop()
    print(f"\n结果: {RESULT_JSON}")


if __name__ == "__main__":
    main()
