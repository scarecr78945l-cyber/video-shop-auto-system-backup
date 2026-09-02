# -*- coding: utf-8 -*-
"""淘宝以图搜精准版：白底单品图 + 精确定位结果区 + 关键词过滤（用后即删）"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

# 用白底单品图（main_1）而非场景图 detail_0 —— 聚焦商品本体，识图更准
IMG = Path(__file__).resolve().parent.parent.parent / "backend" / "data" / "images" / "listing" / "1" / "main_1.png"
print("搜图输入:", IMG.name, "存在:", IMG.exists())

# 同款关键词（从商品标题/类目自动生成，这里先用锅刷类）
CATEGORY_KW = ["锅刷", "刷锅", "洗锅", "钢丝", "清洁刷", "厨房", "洗碗", "炊帚", "刷子", "清洁"]

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://s.taobao.com/image", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        fi = page.locator("input[type=file]").first
        fi.set_input_files(str(IMG), timeout=30000)
        page.wait_for_timeout(12000)

        # 精准提取：识图结果区（不含"猜你喜欢"）
        result = page.evaluate("""() => {
            const out = {related: [], rec: []};
            const seen = new Set();
            // 遍历候选卡片
            document.querySelectorAll('[class*="item"],[class*="card"],[class*="Card"],[class*="goods"] li,a[href*="item.taobao.com"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width < 150 || r.height < 150) return;
                const a = el.tagName === 'A' ? el : el.querySelector('a[href]');
                const href = a ? (a.getAttribute('href')||'') : '';
                const m = href.match(/item\\.taobao\\.com\\/item\\.htm\\?id=(\\d+)/);
                if (!m) return;
                const t = (el.textContent || '').replace(/\\s+/g,' ').trim().slice(0, 60);
                const img = el.querySelector('img');
                const src = img ? (img.getAttribute('src')||img.getAttribute('data-src')||'') : '';
                if (seen.has(m[1])) return;
                seen.add(m[1]);
                out.related.push({id: m[1], title: t, img: src.slice(0,110)});
            });
            return out;
        }""")
        # 按关键词过滤
        related = [it for it in result["related"] if any(k in it["title"] for k in CATEGORY_KW)]
        print(f"识图结果 {len(result['related'])} → 关键词过滤后同款 {len(related)}")
        for it in related[:10]:
            print(f"  [{it['id']}] {it['title'][:45]}")
        (Path(__file__).parent / "pdd-scrape" / "taobao_precise_items.json").write_text(
            json.dumps(related, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        page.close()
finally:
    pw.stop()
