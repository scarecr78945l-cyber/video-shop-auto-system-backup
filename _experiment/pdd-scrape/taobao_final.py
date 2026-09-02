# -*- coding: utf-8 -*-
"""完善版：官方相机识图 → tb-pick-content-item + 关键词过滤 → 取最相关同款（用后即删）"""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

# 用各自的 1688 高清图作输入
INPUTS = {
    1: Path("data/tmp_taobao_input/1_1688.jpg"),
    22: Path("data/tmp_taobao_input/22_1688.jpg"),
    40: Path("data/tmp_taobao_input/40_1688.jpg"),
}
TITLES = {
    1: "不锈钢锅刷不伤锅具去污柔韧耐用长柄可挂式厨房清洁刷",
    22: "袋鼠妈妈内衣洗衣液内裤专用去血渍去渍抑菌除螨母婴可用好物大瓶",
    40: "学生隐形错题胶带透明隐形胶带可书写无痕不留胶修补胶带装饰胶布",
}


def title_keywords(title):
    t = re.sub(r"【[^】]*】", " ", title or "")
    t = re.sub(r"(价格带.*|抖店|官方|正品|同款|包邮|秒杀|爆款)", " ", t)
    t = re.sub(r"[a-zA-Z0-9\-_·，。！!、]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return [t[i:i+2] for i in range(len(t)-1)][:12]


def run(pid):
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            page.goto("https://www.taobao.com", timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            page.evaluate("""() => {
                const box = document.querySelector('input[class*="imageSearch"]') || document.querySelector('input[class*="search"]');
                if (box) box.focus();
            }""")
            page.wait_for_timeout(2000)
            page.evaluate("""() => {
                const icon = document.querySelector('[class*="image-search-icon-wrapper"]');
                if (icon) icon.click();
            }""")
            page.wait_for_timeout(3000)
            page.locator("input[type=file]").first.set_input_files(str(INPUTS[pid]), timeout=30000)
            page.wait_for_timeout(12000)

            cards = page.evaluate("""() => {
                const out = [];
                document.querySelectorAll('.tb-pick-content-item').forEach(el => {
                    const a = el.querySelector('a[href*="item.taobao.com"]');
                    const href = a ? a.getAttribute('href') : '';
                    const m = href.match(/item\\.taobao\\.com\\/item\\.htm\\?id=(\\d+)/);
                    if (!m) return;
                    // 过滤掉"不喜欢该商品"占位卡（无真实标题的商品）
                    const title = (el.textContent||'').replace(/\\s+/g,' ').trim();
                    if (title.includes('不喜欢该商品') && !/[锅刷洗菜洗锅清洁棉浴巾]/.test(title)) return;
                    out.push({id: m[1], title: title.slice(0, 55)});
                });
                return out;
            }""")
            kws = title_keywords(TITLES[pid])
            scored = [(sum(1 for k in kws if k in it["title"]), it) for it in cards]
            scored.sort(key=lambda x: -x[0])
            print(f"\n=== #{pid} {TITLES[pid][:15]} 关键词={kws[:5]} ===")
            print(f"识图卡片 {len(cards)} 个")
            for n, it in scored[:6]:
                print(f"  [{n}] {it['id']} {it['title'][:42]}")
        finally:
            page.close()
    finally:
        pw.stop()


if __name__ == "__main__":
    for pid in [1, 22, 40]:
        run(pid)
