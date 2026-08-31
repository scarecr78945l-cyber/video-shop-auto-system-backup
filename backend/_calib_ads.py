"""M5 实机校准 v8：点击后提取主内容区（过滤全局导航）。"""
import asyncio
import sys

sys.path.insert(0, ".")
from playwright.async_api import async_playwright

GLOBAL_NAV = ["首页", "店铺管理", "商品管理", "订单/配送", "售后管理", "推荐运营", "营销中心",
              "用户运营", "优选联盟", "平台服务", "资金结算", "店铺数据", "服务市场", "搜索",
              "成长中心", "开发文档", "商家社区", "微信小店官网", "下载客户端", "平台客服", "通知",
              "AI小二", "客服"]


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        pg = await ctx.new_page()
        try:
            await pg.goto("https://store.weixin.qq.com/shop/promotion/#/dashboard", timeout=25000, wait_until="domcontentloaded")
            await pg.wait_for_timeout(5000)
            btn = pg.locator("text=添加待托管商品").first
            if await btn.count() == 0:
                btn = pg.locator("text=去添加").first
            await btn.click(timeout=8000)
            await pg.wait_for_timeout(7000)
            body = await pg.locator("body").inner_text(timeout=12000)
            lines = [l.strip() for l in body.splitlines() if l.strip()]
            print(f"总行数: {len(lines)}")
            print("== 主内容（过滤全局导航后）==")
            for l in lines:
                if l and l not in GLOBAL_NAV and not any(n in l for n in GLOBAL_NAV):
                    print("  |", l[:70])
        except Exception as e:
            print("ERR:", str(e)[:120])
        finally:
            await pg.close()
        await browser.close()


asyncio.run(main())
