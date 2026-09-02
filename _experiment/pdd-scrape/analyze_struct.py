# -*- coding: utf-8 -*-
"""精确分析：s.taobao.com/image 识图后的页面结构（找同款结果区）（用后即删）"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

IMG = Path("data/tmp_taobao_input/1_1688.jpg")

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://s.taobao.com/image", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        page.locator("input[type=file]").first.set_input_files(str(IMG), timeout=30000)
        page.wait_for_timeout(12000)
        print("识图后 URL:", page.url[:90])

        # 页面大区块结构（找"同款/相似"区域）
        sections = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('div,section').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width < 200 || r.height < 100) return;
                const t = (el.textContent||'').replace(/\\s+/g,' ').trim();
                // 只看含关键词或标题区的块
                if (/同款|相似|猜你喜欢|找到|为您|图片搜索|识图/.test(t.slice(0,300))) {
                    out.push({cls:(el.getAttribute('class')||'').slice(0,60), rect:`${Math.round(r.width)}x${Math.round(r.height)}`, head: t.slice(0,80)});
                }
            });
            return out.slice(0, 15);
        }""")
        print("\n=== 含'同款/相似/推荐'的区块 ===")
        for s in sections:
            print(json.dumps(s, ensure_ascii=False))

        # 页面可见文本开头
        body = page.evaluate("() => document.body.innerText || ''")
        print("\n正文前 300:", body[:300])
        page.screenshot(path="taobao_image_struct.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
