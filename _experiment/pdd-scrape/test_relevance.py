# -*- coding: utf-8 -*-
"""改进：取最相关同款而非第一个——用商品标题关键词匹配（用后即删）

验证 #22（洗衣液）和 #40（错题胶带）用关键词过滤后是否取到精准同款。
"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

MAIN_IMAGES = Path(__file__).resolve().parent.parent.parent / "backend" / "data" / "images" / "listing"


def title_keywords(title: str) -> list[str]:
    """从商品标题提取 2-4 字核心词（去营销词/品牌/数字/后缀）。"""
    t = title or ""
    t = re.sub(r"【[^】]*】", " ", t)          # 去【】
    t = re.sub(r"(价格带.*|抖店|官方|正品|同款|拍一发二|包邮|秒杀|爆款|热销)", " ", t)
    t = re.sub(r"[a-zA-Z0-9\-_·，。！!、]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # 切成 2-4 字片段（避免单字/太长）
    words = []
    for i in range(len(t) - 1):
        w = t[i:i+2]
        if w not in words:
            words.append(w)
    return words[:12]


def score(related, keywords):
    """按标题命中关键词数排序。"""
    scored = []
    for it in related:
        n = sum(1 for k in keywords if k in it["title"])
        scored.append((n, it))
    scored.sort(key=lambda x: -x[0])
    return scored


def main():
    titles = {
        1: "不锈钢锅刷不伤锅具去污柔韧耐用长柄可挂式厨房清洁刷",
        22: "袋鼠妈妈内衣洗衣液内裤专用去血渍去渍抑菌除螨母婴可用好物大瓶",
        40: "学生隐形错题胶带透明隐形胶带可书写无痕不留胶修补胶带装饰胶布",
    }
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            for pid, title in titles.items():
                img = MAIN_IMAGES / str(pid) / "main_1.png"
                page.goto("https://s.taobao.com/image", timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                page.locator("input[type=file]").first.set_input_files(str(img), timeout=30000)
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
                        out.push({id: m[1], title: (el.textContent||'').replace(/\\s+/g,' ').trim().slice(0,60)});
                    });
                    return out;
                }""")
                kws = title_keywords(title)
                ranked = score(related, kws)
                print(f"\n=== #{pid} {title[:20]} 关键词={kws[:6]}")
                for n, it in ranked[:5]:
                    print(f"  [{n}] {it['id']} {it['title'][:40]}")
        finally:
            page.close()
    finally:
        pw.stop()


if __name__ == "__main__":
    main()
