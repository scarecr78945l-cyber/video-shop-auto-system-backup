# -*- coding: utf-8 -*-
"""淘宝以图搜款 → 扒同款主图（固化工具 v3，Codex 攻坚成果）

正确流程（Codex 发现的两阶段）：
  1. 首页点相机图标（[data-spm="image_search_icon"]）打开识图面板；
  2. 向 #image-search-custom-file-input 注入 PNG/JPG（set_input_files）；
  3. 等 #image-search-upload-button 获得 upload-button-active（canvas 压缩完成）；
  4. 再点"搜索"按钮（关键第二步）→ window.open 识图结果页；
  5. 结果页提取同款商品链接 → 进详情页扒多张主图 → 下载。

低频限速（间隔 3s+），防风控（P-039）。
"""
import json
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

CAMERA = '[data-spm="image_search_icon"]'
FILE_INPUT = "#image-search-custom-file-input"
SEARCH_BUTTON = "#image-search-upload-button"

MAIN_IMAGES = Path(__file__).resolve().parent.parent.parent / "backend" / "data" / "images" / "listing"
RESULT_JSON = Path(__file__).resolve().parent / "taobao_img_results.jsonl"
INTERVAL = 3


def canonical_product_url(url: str):
    parsed = urlsplit(url)
    item_id = parse_qs(parsed.query).get("id", [None])[0]
    host = parsed.netloc.lower()
    if not item_id:
        return None
    if host in ("item.taobao.com", "detail.taobao.com", "detail.tmall.com"):
        return f"https://item.taobao.com/item.htm?id={item_id}"
    return None


def image_search(context, image: Path, page, timeout_ms=45000):
    """两阶段识图：注入 → 等按钮激活 → 点搜索 → 返回结果页 + 同款链接。"""
    page.goto("https://www.taobao.com/", wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(3000)
    page.locator(CAMERA).click(timeout=timeout_ms)
    page.locator(FILE_INPUT).set_input_files(str(image), timeout=timeout_ms)
    # 阶段1完成条件：canvas 压缩完成，按钮变"搜索"(upload-button-active)
    page.wait_for_function(
        """() => {
            const b = document.querySelector('#image-search-upload-button');
            return b && b.classList.contains('upload-button-active');
        }""",
        timeout=timeout_ms,
    )
    # 关键第二步：点"搜索"按钮 → window.open 结果页
    with page.expect_popup(timeout=timeout_ms) as popup_info:
        page.locator(SEARCH_BUTTON).click(timeout=timeout_ms)
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    popup.wait_for_function(
        """() => [...document.querySelectorAll('a[href]')].some(a =>
          /item\\.taobao\\.com|detail\\.tmall\\.com|detail\\.taobao\\.com/.test(a.href))""",
        timeout=timeout_ms,
    )
    hrefs = popup.locator("a[href]").evaluate_all(
        "els => [...new Set(els.map(a => a.href).filter(h => "
        "/item\\.taobao\\.com|detail\\.tmall\\.com|detail\\.taobao\\.com/.test(h)))]"
    )
    urls = []
    for h in hrefs:
        c = canonical_product_url(h)
        if c and c not in urls:
            urls.append(c)
    return popup, urls


def scrape_detail(page, url: str, out_dir: Path, max_imgs=5):
    """进同款详情页扒主图并下载。"""
    page.goto(url, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    imgs = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('img').forEach(el => {
            const s = el.getAttribute('src')||el.getAttribute('data-src')||el.getAttribute('data-ks-lazyload')||'';
            if (s.includes('alicdn') && !s.includes('tps-') && s.length > 60) out.push(s);
        });
        return [...new Set(out)].slice(0, 8);
    }""")
    out_dir.mkdir(parents=True, exist_ok=True)
    dl = 0
    for i, u in enumerate(imgs[:max_imgs]):
        full = "https:" + u if u.startswith("//") else u
        ext = ".webp" if "webp" in full else ".jpg"
        dest = out_dir / f"tb_main_{i}{ext}"
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0", "Referer": url})
            data = urllib.request.urlopen(req, timeout=15).read()
            if len(data) > 2000:
                dest.write_bytes(data)
                dl += 1
        except Exception:
            pass
    return len(imgs), dl


def main():
    tasks = {
        1: Path("data/tmp_taobao_input/1_clean.png"),
        22: Path("data/tmp_taobao_input/22_clean.png"),
        40: Path("data/tmp_taobao_input/40_clean.png"),
    }
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            for pid, img in tasks.items():
                print(f"=== #{pid} ===", flush=True)
                popup = None
                try:
                    popup, urls = image_search(ctx, img, page)
                    rec = {"pid": pid, "ok": True, "result_url": popup.url[:120],
                           "related": len(urls), "first": urls[0] if urls else None}
                    print(f"  识图同款 {len(urls)} → 第一个 {urls[0] if urls else '?'}", flush=True)
                    # 进第一个同款扒主图
                    if urls:
                        out_dir = MAIN_IMAGES / str(pid)
                        n, dl = scrape_detail(page, urls[0], out_dir)
                        rec["detail_images"] = n
                        rec["downloaded"] = dl
                        print(f"  详情主图 {n} 张，下载 {dl} → {out_dir}", flush=True)
                    with open(RESULT_JSON, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"  ✗ {type(e).__name__}: {str(e)[:90]}", flush=True)
                    with open(RESULT_JSON, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"pid": pid, "ok": False, "error": str(e)[:120]}, ensure_ascii=False) + "\n")
                finally:
                    if popup and not popup.is_closed():
                        popup.close()
                time.sleep(INTERVAL)
        finally:
            page.close()
    finally:
        pw.stop()
    print(f"\n结果: {RESULT_JSON}")


if __name__ == "__main__":
    main()