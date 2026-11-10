# -*- coding: utf-8 -*-
"""有米云深采 Stage 2: 对匹配商品进 overview/leaflet/video 抓真实素材图并下载。

- 读 youmi_matched.json (pid/gid/title/img)，按 bigram 分过滤（≥15，防误配）。
- 每商品访问 /overview + /leaflet + /video，提取真实素材 URL（过滤 UI 资产），去重下载 ≤10 张。
- 低频 + 批暂停 + 连续失败熔断（P-040 有米云限流纪律）。
- 输出：backend/data/images/youmi_deep/<pid>/img_<i>.<ext>
"""
import json
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
DEEP = ROOT / "backend" / "data" / "images" / "youmi_deep"
MATCHED = Path(__file__).resolve().parent / "youmi_matched.json"
LOG = Path(__file__).resolve().parent / "youmi_deep.log"

INTERVAL = 3
BATCH_SIZE = 10
BATCH_PAUSE = 60
MAX_CONSEC_FAIL = 3
MAX_IMGS = 10

# 真实素材域名/特征；排除 UI 资产
INCLUDE_RE = re.compile(r"(lp-ag-v2\.umcdn\.cn|brand-static\.umcdn\.cn|static-youcloud\.umcdn\.cn|static-ag\.umcdn\.cn)")
EXCLUDE_RE = re.compile(r"/(caas|logo|icon|icons)/|private\.png|\.svg|youshu/private")


def is_real(u):
    return bool(INCLUDE_RE.search(u)) and not EXCLUDE_RE.search(u)


def bigrams(s):
    s = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def extract_images(page, url, timeout=60000):
    """导航到详情 tab，滚动触发懒加载，广抓 background-image + img 真实素材 URL。"""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(6000)
    except Exception:
        return []
    # 滚动 3 次触发懒加载
    for _ in range(3):
        page.evaluate("() => window.scrollBy(0, 1200)")
        page.wait_for_timeout(1200)
    page.wait_for_timeout(1500)
    urls = page.evaluate("""() => {
        const out = [];
        const add = (u) => { if (u && u.startsWith('http') && u.length > 40) out.push(u); };
        document.querySelectorAll('img').forEach(el => {
            let u = el.getAttribute('src') || el.getAttribute('data-src') || el.getAttribute('data-original') || '';
            if (u.startsWith('data:') || u.startsWith('blob:')) u = '';
            add(u);
        });
        document.querySelectorAll('[style*="background-image"], .ys-bg-img, [class*="recommendation-card"], [class*="cover"], [class*="Cover"]').forEach(el => {
            const st = el.getAttribute('style') || '';
            const m = st.match(/url\\(\\s*["']?(https?:\\/\\/[^"')\\s]+)/);
            if (m) add(m[1]);
        });
        document.querySelectorAll('video source').forEach(s => { const u = s.getAttribute('src')||''; if (u.startsWith('http') && !u.endsWith('.mp4') || u) add(u); });
        return [...new Set(out)];
    }""")
    return [u for u in urls if is_real(u)]


def base_key(u):
    """去 auth_key/query 的 base URL（同图不同签名去重）。"""
    from urllib.parse import urlsplit
    p = urlsplit(u)
    return f"{p.netloc}{p.path}"


def download(url, dest: Path):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://console.youshu.youcloud.com/"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) <= 3000:
            return False
        # 尺寸/比例过滤：min 边 ≥400 且 0.75~1.33（方正商品图）；宽横幅/小图丢弃
        import io
        from PIL import Image
        try:
            with Image.open(io.BytesIO(data)) as im:
                w, h = im.size
                mn, mx = min(w, h), max(w, h)
                if mn < 400 or mx / mn > 1.4:
                    return False
                ext = (im.format or "jpg").lower()
        except Exception:
            ext = "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        dest = dest.with_suffix("." + ext)
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def main():
    con1 = sqlite3.connect(str(ROOT / "backend/data/db/m1-sourcing.db"))
    titles = {r[0]: (r[1] or "") for r in con1.execute("SELECT id, title FROM products").fetchall()}
    con1.close()

    matched = json.loads(MATCHED.read_text(encoding="utf-8"))
    # 过滤：bigram 分 ≥15
    kept = []
    for m in matched:
        pid = m["pid"]
        ot = titles.get(pid, "")
        sc = len(bigrams(ot) & bigrams(m.get("title", "")))
        if sc >= 15:
            kept.append((pid, m["gid"], sc))
    print(f"matched {len(matched)} → 高分保留 {len(kept)}", flush=True)

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        consec_fail = 0
        try:
            for i, (pid, gid, sc) in enumerate(kept, 1):
                if i > 1 and (i - 1) % BATCH_SIZE == 0:
                    print(f"   ⏸ 批暂停 {BATCH_PAUSE}s（有米云限流纪律）", flush=True)
                    time.sleep(BATCH_PAUSE)
                out_dir = DEEP / str(pid)
                out_dir.mkdir(parents=True, exist_ok=True)
                urls = []
                seen = set()
                for tab in ("overview", "leaflet", "video"):
                    u = extract_images(page, f"https://console.youshu.youcloud.com/goods/{gid}/{tab}")
                    print(f"  #{pid} [{tab}] real imgs: {len(u)}", flush=True)
                    for x in u:
                        k = base_key(x)
                        if k in seen:
                            continue
                        seen.add(k)
                        urls.append(x)
                print(f"=== [{i}/{len(kept)}] #{pid} (sc={sc}) 素材 {len(urls)} 张，下载中…", flush=True)
                # 清旧
                for f in out_dir.glob("img_*"):
                    f.unlink()
                dl = 0
                for j, u in enumerate(urls[:MAX_IMGS]):
                    if download(u, out_dir / f"img_{j}.jpg"):
                        dl += 1
                print(f"   #{pid} 下载 {dl}/{min(len(urls), MAX_IMGS)} → {out_dir}", flush=True)
                if dl == 0:
                    consec_fail += 1
                    if consec_fail >= MAX_CONSEC_FAIL:
                        print("   ⛔ 连续无图，熔断停止", flush=True)
                        break
                else:
                    consec_fail = 0
                time.sleep(INTERVAL)
        finally:
            page.close()
    finally:
        pw.stop()
    print("done")


if __name__ == "__main__":
    main()
