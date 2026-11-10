# -*- coding: utf-8 -*-
"""Stage 1 (v2): 复用采集器动态表头定位，30 天商品榜收集 + 匹配 65 商品。
每行提取：干净标题（text_content）+ goods_id + 主图 URL。
"""
import json
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
con4 = sqlite3.connect(str(ROOT / "backend/data/db/m4-listing.db"))
pids = [r[0] for r in con4.execute("SELECT product_id FROM listing_tasks WHERE status='pending'").fetchall()]
con4.close()
con1 = sqlite3.connect(str(ROOT / "backend/data/db/m1-sourcing.db"))
titles = {r[0]: (r[1] or "") for r in con1.execute("SELECT id, title FROM products").fetchall()}
con1.close()


def bigrams(s):
    s = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def clean_title(t):
    t = re.sub(r"(抖店|复制|¥\d+(\.\d+)?|ID\s*\d+|【|】|拍一发二|抢|划算|福利|爆款|同款)", "", t)
    return t.strip()


ours = {p: clean_title(titles[p]) for p in pids}
print("our products:", len(ours), flush=True)

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9566")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        end = date.today(); start = end - timedelta(days=30)
        page.goto(f"https://console.youshu.youcloud.com/goods/sale?site_id=10502"
                  f"&startDate={start.isoformat()}&endDate={end.isoformat()}",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)
        # 动态表头定位（复用采集器 _locate_columns 逻辑）
        heads = page.locator(".el-table__header th").all_text_contents()
        title_col = None
        for i, h in enumerate(heads[:14]):
            if "商品" in h.strip():
                title_col = i
                break
        print("title_col:", title_col, "| heads:", [h.strip()[:4] for h in heads[:6]], flush=True)

        board = []
        for pg in range(6):
            rows = page.locator(".el-table__body-wrapper tr").all()
            for r in rows:
                gid = ""
                for a in r.locator('a[href*="/overview"]').all():
                    m = re.search(r"/goods/([^/]+)/overview", a.get_attribute("href") or "")
                    if m:
                        gid = m.group(1)
                        break
                if not gid:
                    continue
                title = ""
                if title_col is not None:
                    try:
                        title = (r.locator("td").nth(title_col).text_content(timeout=1500) or "").strip()
                    except Exception:
                        title = ""
                if not title:
                    try:
                        title = (r.inner_text(timeout=1500) or "").strip()[:40]
                    except Exception:
                        title = ""
                img = ""
                try:
                    st = r.locator(".ys-bg-img").first.get_attribute("style") or ""
                    m = re.search(r'url\(\s*["\']?(https?://[^"\')\s]+)', st)
                    if m:
                        img = m.group(1)
                except Exception:
                    pass
                board.append({"title": title, "gid": gid, "img": img})
            if pg < 5:
                nxt = page.locator(".el-pagination .btn-next, .el-pagination__next").first
                try:
                    if nxt.count() and nxt.is_enabled():
                        page.evaluate("(el) => el.click()", nxt.element_handle())
                        page.wait_for_timeout(2500)
                    else:
                        break
                except Exception:
                    break
        print(f"board rows: {len(board)}", flush=True)
        # match
        matched = []
        for pid, ot in ours.items():
            o_bg = bigrams(ot)
            best = None
            for b in board:
                if not b["title"]:
                    continue
                inter = len(o_bg & bigrams(b["title"]))
                if inter >= 5 and (best is None or inter > best[0]):
                    best = (inter, b)
            if best:
                matched.append((pid, ot, best[0], best[1]))
        print(f"matched: {len(matched)}/{len(ours)}", flush=True)
        for pid, ot, sc, b in matched:
            print(f"  #{pid} '{ot[:22]}' sc={sc} → '{b['title'][:26]}' gid={b['gid'][:14]} img={'Y' if b['img'] else 'N'}", flush=True)
        # save for stage2
        out = Path(__file__).resolve().parent / "youmi_matched.json"
        out.write_text(json.dumps(
            [{"pid": p, "gid": b["gid"], "title": b["title"], "img": b["img"]} for p, _, _, b in matched],
            ensure_ascii=False), encoding="utf-8")
        print("saved", out)
    finally:
        page.close()
finally:
    pw.stop()
