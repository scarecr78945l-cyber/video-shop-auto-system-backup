"""M4 浏览器自动化：商品列表页读取在售商品类目（已开通类目）。"""
import asyncio
import sys

sys.path.insert(0, ".")
from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        target = None
        for pg in ctx.pages:
            if "store.weixin.qq.com" in pg.url:
                target = pg
                break
        await target.goto("https://store.weixin.qq.com/shop/goods/list", timeout=30000, wait_until="domcontentloaded")
        await target.wait_for_timeout(9000)
        print("URL:", target.url[:100])
        body = await target.locator("body").inner_text(timeout=12000)
        lines = [l.strip() for l in body.splitlines() if l.strip() and len(l.strip()) < 60]
        # 过滤全局导航
        nav = ["首页", "店铺管理", "商品管理", "订单/配送", "售后管理", "推荐运营", "营销中心", "用户运营",
               "优选联盟", "平台服务", "资金结算", "店铺数据", "服务市场", "搜索", "成长中心", "开发文档",
               "商家社区", "微信小店官网", "下载客户端", "平台客服", "通知", "客服", "新增商品", "商品列表",
               "商品内容", "商品合集", "非卖商品", "商品成长", "商机中心"]
        items = [l for l in lines if l not in nav and not any(n in l for n in nav)]
        print(f"商品列表内容行: {len(items)}")
        for l in items[:40]:
            print("  |", l[:55])
        # 找表格行/类目列
        rows = await target.locator("tr, [class*=row], [class*=item]").count()
        print("行元素:", rows)
        await browser.close()


asyncio.run(main())
