# -*- coding: utf-8 -*-
"""完整重跑：官方相机识图 详细分步日志 + 完整结果卡片（用后即删）"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

IMGS = {
    1: Path("data/tmp_taobao_input/1_1688.jpg"),
    22: Path("data/tmp_taobao_input/22_1688.jpg"),
}

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        for pid, img in IMGS.items():
            print(f"\n{'='*50}\n=== #{pid} 图片: {img.name} ===", flush=True)
            # 1) 打开首页
            page.goto("https://www.taobao.com", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(7000)
            print("[1] 首页已打开", flush=True)

            # 2) hover 相机图标
            cam = page.locator("[class*='image-search-icon-wrapper']").first
            print(f"[2] 相机图标 count={cam.count()}", flush=True)
            cam.hover(timeout=5000)
            page.wait_for_timeout(1000)
            cam.click(timeout=5000)
            page.wait_for_timeout(2500)
            print("[2] 已点击相机图标", flush=True)

            # 3) 上传图片
            ub = page.locator("text=上传图片").first
            print(f"[3] 上传按钮 count={ub.count()}", flush=True)
            if ub.count() > 0:
                with page.expect_file_chooser(timeout=8000) as fc:
                    ub.click(timeout=5000)
                fc.value.set_files(str(img))
                print("[3] 文件已设置:", img.name, flush=True)
            else:
                page.locator("input[type=file]").first.set_input_files(str(img), timeout=30000)
                print("[3] 兜底 set_input_files", flush=True)

            # 4) 等待 + 观察
            for i in range(12):
                page.wait_for_timeout(1500)
                n = page.locator(".tb-pick-content-item").count()
                if n > 0:
                    print(f"[4] t+{(i+1)*1.5:.0f}s 识图卡片出现: {n} 个", flush=True)
                    break
            print(f"[4] 最终 URL: {page.url[:80]}", flush=True)

            # 5) 完整提取所有卡片（图+标题+同款标签）
            cards = page.evaluate("""() => {
                const out = [];
                document.querySelectorAll('.tb-pick-content-item').forEach(el => {
                    const a = el.querySelector('a[href*="item.taobao.com"]');
                    const href = a ? a.getAttribute('href') : '';
                    const m = href.match(/item\\.taobao\\.com\\/item\\.htm\\?id=(\\d+)/);
                    if (!m) return;
                    const img = el.querySelector('img');
                    const src = img ? (img.getAttribute('src')||img.getAttribute('data-src')||'') : '';
                    const t = (el.textContent||'').replace(/\\s+/g,' ').trim();
                    out.push({id: m[1], img: src.slice(0, 80), title: t.slice(0, 45)});
                });
                return out;
            }""")
            print(f"[5] 识图卡片共 {len(cards)} 个:")
            for it in cards[:15]:
                print(f"    id={it['id']} img={it['img'][:45]}")
                print(f"         {it['title']}")
            page.screenshot(path=f"rerun_{pid}.png", full_page=False)
    finally:
        page.close()
finally:
    pw.stop()
