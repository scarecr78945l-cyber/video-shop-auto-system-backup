"""M5 前置探测 v5：投放 dashboard 主 frame 内容（只读）。"""
import asyncio
import sys

sys.path.insert(0, ".")
from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        if "/shop/promotion" not in pg.url:
            await pg.goto("https://store.weixin.qq.com/shop/promotion/", timeout=25000)
        await pg.wait_for_timeout(6000)
        print("URL:", pg.url[:110])
        body = await pg.locator("body").inner_text(timeout=15000)
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        print(f"正文行数: {len(lines)}")
        # 找托管/余额/投放相关内容
        for l in lines:
            if any(k in l for k in ["托管", "余额", "投放", "商品", "素材", "预算", "ROI", "曝光", "花费", "成交"]):
                print("  |", l[:80])
        # 若无托管字样，打印全部
        if not any("托管" in l for l in lines):
            print("== 全正文 ==")
            for l in lines[:40]:
                print("  |", l[:70])
        await browser.close()


asyncio.run(main())
