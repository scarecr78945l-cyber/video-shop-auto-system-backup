# -*- coding: utf-8 -*-
"""淘宝以图搜款 → 扒同款主图（固化工具 v1，低频限速防 P-039 阿里风控）

用法: python -X utf8 taobao_image_search.py <pid1> <pid2> ...
输入: backend/data/images/listing/<pid>/main_1.png（白底单品图，识图最准）
流程: 识图搜同款 → 取第一个同款 → 进详情页扒主图数组 → 下载到
      backend/data/images/listing/<pid>/tb_main_<i>.<ext>
限速: 每商品间隔 SEARCH_INTERVAL 秒（默认 8s）；每商品一次识图 + 一次详情页
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
# 主项目素材目录（复用已有白底图）
MAIN_IMAGES = HERE.parent.parent / "backend" / "data" / "images" / "listing"

SEARCH_INTERVAL = 8  # 秒，防阿里风控（P-039）
DOWNLOAD_TIMEOUT = 15
RESULT_JSON = HERE / "taobao_results.jsonl"


def scrape_one(page, pid: int) -> dict:
    """单商品：识图 → 第一个同款 → 详情页主图。"""
    img = MAIN_IMAGES / str(pid) / "main_1.png"
    if not img.exists():
        return {"pid": pid, "error": "NO_MAIN1"}
    rec = {"pid": pid}

    # 1) 识图搜同款
    page.goto("https://s.taobao.com/image", timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    fi = page.locator("input[type=file]").first
    fi.set_input_files(str(img), timeout=30000)
    page.wait_for_timeout(12000)

    related = page.evaluate("""() => {
        const out = [];
        const seen = new Set();
        document.querySelectorAll('[class*="item"],[class*="card"],[class*="Card"],a[href*="item.taobao.com"]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width < 150 || r.height < 150) return;
            const a = el.tagName === 'A' ? el : el.querySelector('a[href]');
            const href = a ? (a.getAttribute('href')||'') : '';
            const m = href.match(/item\\.taobao\\.com\\/item\\.htm\\?id=(\\d+)/);
            if (!m || seen.has(m[1])) return;
            seen.add(m[1]);
            const t = (el.textContent || '').replace(/\\s+/g,' ').trim().slice(0, 60);
            out.push({id: m[1], title: t});
        });
        return out;
    }""")
    rec["related"] = len(related)
    if not related:
        rec["error"] = "NO_MATCH"
        return rec
    first = related[0]
    rec["first_id"] = first["id"]
    rec["first_title"] = first["title"][:40]
    print(f"  #{pid} 同款 {len(related)} → 第一个 id={first['id']} {first['title'][:30]}", flush=True)

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
    print(f"      详情页主图 {len(urls)} 张", flush=True)

    # 3) 下载
    out_dir = MAIN_IMAGES / str(pid)
    out_dir.mkdir(parents=True, exist_ok=True)
    dl_ok = 0
    for i, u in enumerate(urls[:5]):
        full = "https:" + u if u.startswith("//") else u
        ext = ".webp" if "webp" in full else ".jpg"
        dest = out_dir / f"tb_main_{i}{ext}"
        try:
            import urllib.request
            req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://item.taobao.com/"})
            data = urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT).read()
            if len(data) > 2000:
                dest.write_bytes(data)
                dl_ok += 1
        except Exception as e:
            print(f"      下载[{i}] ERR {str(e)[:40]}", flush=True)
    rec["downloaded"] = dl_ok
    print(f"      下载 {dl_ok} 张 → {out_dir}", flush=True)
    return rec


def main():
    pids = [int(x) for x in sys.argv[1:]]
    if not pids:
        print("用法: taobao_image_search.py <pid1> <pid2> ...")
        return
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            for i, pid in enumerate(pids):
                print(f"=== #{pid} ({i+1}/{len(pids)}) ===", flush=True)
                rec = scrape_one(page, pid)
                with open(RESULT_JSON, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if i < len(pids) - 1:
                    print(f"  间隔 {SEARCH_INTERVAL}s（防风控）...", flush=True)
                    time.sleep(SEARCH_INTERVAL)
        finally:
            page.close()
    finally:
        pw.stop()
    print(f"\n结果已存: {RESULT_JSON}")


if __name__ == "__main__":
    main()
