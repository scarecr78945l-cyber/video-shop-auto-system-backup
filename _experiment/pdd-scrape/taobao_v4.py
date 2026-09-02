# -*- coding: utf-8 -*-
"""淘宝以图搜款 → 高清同款主图（全量工具 v4，基于 Codex 两阶段状态机 + P-045）

相对 v3 的改进：
  1. HD 原图：剥掉 alicdn 处理后缀（_q50/_760x760q30/_.webp）取原始高清图；
  2. 候选标题提取 + 关键词（中文 bigram）打分，避开推荐流污染的第 1 位；
  3. 全量 65 商品任务清单来自 m4-listing.db pending 任务 + m1 商品标题；
  4. 查询图 = 主项目真实素材 listing/<pid>/main_0.png（实测带文字也精准）；
  5. 风控熔断：连续 N 次无结果/异常即停（P-039 纪律），低频 3s 间隔；
  6. 断点续跑：tb_main_0.* 已存在且日志 ok 则跳过。

输出：backend/data/images/listing/<pid>/tb_main_<i>.<ext>（高清原图）
日志：taobao_v4_results.jsonl（每商品一行）
"""
import json
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright
from playwright._impl._errors import TargetClosedError

CAMERA = '[data-spm="image_search_icon"]'
FILE_INPUT = "#image-search-custom-file-input"
SEARCH_BUTTON = "#image-search-upload-button"

ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_IMAGES = ROOT / "backend" / "data" / "images" / "listing"
DB_M4 = ROOT / "backend" / "data" / "db" / "m4-listing.db"
DB_M1 = ROOT / "backend" / "data" / "db" / "m1-sourcing.db"
RESULT_JSON = Path(__file__).resolve().parent / "taobao_v4_results.jsonl"

INTERVAL = 3            # 商品间低频间隔（秒），P-039/P-040 纪律
MAX_CONSEC_FAIL = 3     # 连续失败熔断阈值
BATCH_SIZE = 0          # 0=不分批；>0 每批后暂停 BATCH_PAUSE 秒
BATCH_PAUSE = 0
MAX_IMGS = 5            # 每商品下载高清主图数
CANDIDATES_N = 10       # 参与打分的候选数
PRODUCTS = None         # None=全量 65；或 [pid,...]

# alicdn 处理后缀（webp 包装 / q 压缩 / 尺寸缩放）
_PROC_Q = re.compile(r"_(?:\d+[a-z]*x\d+[a-z]*)?q\d+(?:\.[a-z]{3,4})?$")
_PROC_SIZE = re.compile(r"_\d+[a-z]*x\d+[a-z]*(?:\.[a-z]{3,4})?$")


def hd_url(u: str) -> str:
    """剥掉 alicdn 处理后缀，返回原始高清 URL。"""
    if u.startswith("//"):
        u = "https:" + u
    if u.endswith("_.webp"):
        u = u[: -len("_.webp")]
    changed = True
    while changed:
        changed = False
        for pat in (_PROC_Q, _PROC_SIZE):
            m = pat.search(u)
            if m:
                u = u[: m.start()]
                changed = True
                break
    return u


def canonical_product_url(url: str):
    parsed = urlsplit(url)
    item_id = parse_qs(parsed.query).get("id", [None])[0]
    host = parsed.netloc.lower()
    if not item_id:
        return None
    if host in ("item.taobao.com", "detail.taobao.com", "detail.tmall.com"):
        return f"https://item.taobao.com/item.htm?id={item_id}"
    return None


def bigrams(s: str) -> set:
    s = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def pick_best(cards, product_title: str):
    """cards: [(url, title)] → 按中文 bigram 重叠打分选最优（url, title, score）。"""
    pt = bigrams(product_title)
    scored = []
    for url, title in cards:
        if not title:
            continue
        ct = bigrams(title)
        inter = len(pt & ct)
        if inter > 0:
            scored.append((inter, url, title))
    scored.sort(key=lambda x: -x[0])
    if scored:
        inter, url, title = scored[0]
        return url, title, inter
    return cards[0][0] if cards else None, (cards[0][1] if cards else ""), 0


def image_search(context, image: Path, page, timeout_ms=45000):
    """两阶段识图 → 返回 (popup, [(canonical_url, title), ...])。"""
    page.goto("https://www.taobao.com/", wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(6000)
    # 显式等相机图标就绪（页面 JS 未就绪时点击会超时）
    page.locator(CAMERA).first.wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(1000)
    page.locator(CAMERA).click(timeout=timeout_ms)
    page.locator(FILE_INPUT).set_input_files(str(image), timeout=timeout_ms)
    page.wait_for_function(
        """() => {
            const b = document.querySelector('#image-search-upload-button');
            return b && b.classList.contains('upload-button-active');
        }""",
        timeout=timeout_ms,
    )
    with page.expect_popup(timeout=timeout_ms) as popup_info:
        page.locator(SEARCH_BUTTON).click(timeout=timeout_ms)
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    popup.wait_for_function(
        """() => [...document.querySelectorAll('a[href]')].some(a =>
          /item\\.taobao\\.com|detail\\.tmall\\.com|detail\\.taobao\\.com/.test(a.href))""",
        timeout=timeout_ms,
    )
    cards = popup.evaluate("""() => {
        const out = [];
        const seen = new Set();
        document.querySelectorAll('a[href]').forEach(a => {
            const h = a.href || '';
            if (!/item\\.taobao\\.com|detail\\.tmall\\.com|detail\\.taobao\\.com/.test(h)) return;
            if (seen.has(h)) return; seen.add(h);
            let title = (a.innerText||'').trim();
            let card = a.closest('[class*="card"],[class*="Card"],[class*="item"],[class*="Item"],[class*="content"]');
            if (card) {
                const t = card.querySelector('[class*="Title"],[class*="title"],[class*="titleWrap"],[class*="title-line"]');
                if (t) title = (t.innerText||'').trim();
            }
            out.push({url:h, title:title});
        });
        return out.slice(0, %d);
    }""" % CANDIDATES_N)
    result = []
    for c in cards:
        u = canonical_product_url(c["url"])
        if u and (u, c["title"]) not in result:
            result.append((u, c["title"]))
    return popup, result


def scrape_detail(page, url: str, out_dir: Path):
    """进同款详情页扒高清主图并下载。返回 (found, downloaded, sizes)。"""
    page.goto(url, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    imgs = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('img').forEach(el => {
            const s = el.getAttribute('src')||el.getAttribute('data-src')||el.getAttribute('data-ks-lazyload')||'';
            if (s.includes('alicdn') && !s.includes('tps-') && s.length > 60) out.push(s);
        });
        return [...new Set(out)];
    }""")
    hd = []
    for u in imgs:
        h = hd_url(u)
        if h not in hd:
            hd.append(h)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 清理旧 tb_main（重跑时覆盖）
    for f in out_dir.glob("tb_main_*"):
        f.unlink()
    dl = 0
    sizes = []
    for i, full in enumerate(hd[:MAX_IMGS]):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0", "Referer": url})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
            if len(data) <= 3000:
                continue
            # alicdn 常返回 webp 字节；按内容识别真实格式（P-045b 修正扩展名）
            import io
            from PIL import Image as PILImage
            ext = "jpg"
            try:
                with PILImage.open(io.BytesIO(data)) as im:
                    ext = (im.format or "jpg").lower()
            except Exception:
                pass
            dest = out_dir / f"tb_main_{i}.{ext}"
            dest.write_bytes(data)
            dl += 1
            sizes.append(len(data))
        except Exception:
            pass
    return len(hd), dl, sizes


def load_tasks():
    """65 个 pending 上架任务 → [(product_id, title)]。"""
    con = sqlite3.connect(str(DB_M4))
    pids = [r[0] for r in con.execute(
        "SELECT product_id FROM listing_tasks WHERE status='pending' ORDER BY product_id").fetchall()]
    con.close()
    con1 = sqlite3.connect(str(DB_M1))
    rows = con1.execute("SELECT id, title FROM products").fetchall()
    con1.close()
    by_id = {r[0]: (r[1] or "") for r in rows}
    return [(p, by_id.get(p, "")) for p in pids]


def already_done(pid: int) -> bool:
    d = MAIN_IMAGES / str(pid)
    if not d.exists():
        return False
    if not list(d.glob("tb_main_*")):
        return False
    if RESULT_JSON.exists():
        for line in RESULT_JSON.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("pid") == pid and r.get("ok"):
                return True
    return False


def main():
    tasks = PRODUCTS if PRODUCTS is not None else [p for p, _ in load_tasks()]
    titles = {p: t for p, t in load_tasks()}
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        consec_fail = 0
        batch_done = 0
        try:
            for idx, pid in enumerate(tasks, 1):
                if already_done(pid):
                    print(f"[{idx}/{len(tasks)}] #{pid} 已存在，跳过", flush=True)
                    continue
                img = MAIN_IMAGES / str(pid) / "main_0.png"
                if not img.exists():
                    print(f"[{idx}/{len(tasks)}] #{pid} ✗ 无查询图 {img}", flush=True)
                    continue
                # 分批暂停：降低平台接口频率（P-039/P-040 纪律）
                if BATCH_SIZE > 0 and batch_done > 0 and batch_done % BATCH_SIZE == 0:
                    print(f"   ⏸ 批次 {batch_done//BATCH_SIZE} 完成，暂停 {BATCH_PAUSE}s 降频…", flush=True)
                    time.sleep(BATCH_PAUSE)
                title = titles.get(pid, "")
                print(f"=== [{idx}/{len(tasks)}] #{pid} 识图… ===", flush=True)
                rec = {"pid": pid, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
                ok = False
                for attempt in range(2):  # 浏览器竞争导致页面关闭时重试 1 次（非风控失败）
                    popup = None
                    if page.is_closed():
                        page = ctx.new_page()
                    try:
                        popup, cards = image_search(ctx, img, page)
                        rec["related"] = len(cards)
                        if not cards:
                            raise RuntimeError("0 related")
                        best_url, best_title, score = pick_best(cards, title)
                        rec["candidates"] = [t for _, t in cards[:3]]
                        rec["best_url"] = best_url
                        rec["best_title"] = best_title[:80]
                        rec["score"] = score
                        print(f"   同款 {len(cards)} 候选 → 最优 '{best_title[:40]}' (score {score})", flush=True)
                        if best_url:
                            out_dir = MAIN_IMAGES / str(pid)
                            n, dl, sizes = scrape_detail(page, best_url, out_dir)
                            rec["detail_images"] = n
                            rec["downloaded"] = dl
                            rec["sizes"] = sizes
                            print(f"   详情主图 {n}，高清下载 {dl} → {out_dir}", flush=True)
                        rec["ok"] = True
                        ok = True
                        break
                    except Exception as e:
                        msg = str(e)
                        closed = isinstance(e, TargetClosedError) or "closed" in msg
                        if attempt == 0 and (closed or page.is_closed()):
                            print(f"   ↻ 页面关闭，重建重试… ({str(e)[:60]})", flush=True)
                            try:
                                page.close()
                            except Exception:
                                pass
                            page = ctx.new_page()
                            time.sleep(3)
                            continue
                        rec["error"] = msg[:150]
                        break
                if not ok:
                    rec["ok"] = False
                    rec.setdefault("error", rec.get("error") or "unknown")
                    consec_fail += 1
                    print(f"   ✗ {rec['error'][:90]} (连续失败 {consec_fail})", flush=True)
                    if consec_fail >= MAX_CONSEC_FAIL:
                        rec["stop"] = "risk-stop"
                        print("   ⛔ 连续失败达阈值，熔断停止（风控纪律 P-039）", flush=True)
                        with open(RESULT_JSON, "a", encoding="utf-8") as f:
                            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        break
                else:
                    consec_fail = 0
                    batch_done += 1
                with open(RESULT_JSON, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                time.sleep(INTERVAL)
        finally:
            try:
                page.close()
            except Exception:
                pass
    finally:
        pw.stop()
    print(f"\n结果: {RESULT_JSON}")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:]]
    for a in argv:
        if a.startswith("--interval="):
            INTERVAL = int(a.split("=", 1)[1])
        elif a.startswith("--batch-size="):
            BATCH_SIZE = int(a.split("=", 1)[1])
        elif a.startswith("--batch-pause="):
            BATCH_PAUSE = int(a.split("=", 1)[1])
    pids = [a for a in argv if not a.startswith("--")]
    if pids:
        PRODUCTS = [int(x) for x in pids[0].split(",")]
    main()
