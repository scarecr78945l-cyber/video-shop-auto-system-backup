"""1688 逐 SKU 真实询价采集器（订单确认页读价，不下单）。

半成品已验证：以图搜款 + 订单确认页询价，拿到真实链接与最低有效成本。
fixtures 模式见 fixtures.FixtureQuoteCollector。
"""

from __future__ import annotations

from ..config import CollectorConfig
from ..models import Quote, SourceItem
from .base import CollectorError, QuoteCollector
from .browser import SharedBrowser, detect_page_changed

DEFAULT_SELECTORS = {
    "search_input": "input[placeholder*='搜索'], input[class*='search']",
    "search_btn": "button[class*='search'], .search-btn",
    "image_upload": "input[type='file'], .upload-btn",
    "result_row": ".card-item, [class*='offer'] li",
    "result_title": ".title, [class*='title']",
    "order_price": ".order-price, .price-box, [class*='price']",
    "supplier_name": ".company-name, [class*='company']",
    "confirm_btn": ".confirm-btn, button:has-text('确认')",
    "login_gate": ".login-modal, [class*='login']",
    "verify_gate": ".captcha, [class*='verify']",
}


class AlibabaQuoteCollector(QuoteCollector):
    source = "alibaba"

    def __init__(self, config: CollectorConfig):
        super().__init__(config)
        self.selectors = {**DEFAULT_SELECTORS, **config.selectors}
        self.browser = SharedBrowser(config.cdp_port, config.chrome_path)

    def quote(self, item: SourceItem, max_suppliers: int = 5) -> list[Quote]:
        """以图搜款（或标题搜索）→ 进商品页 → 订单确认页读价。"""
        page = self.browser.page()
        try:
            page.goto(self.selectors.get("home_url", "https://www.1688.com"), timeout=45000)
            if page.locator(self.selectors["login_gate"]).first.is_visible(timeout=3000):
                raise CollectorError("1688 登录态失效，需人工登录", "AUTH_REQUIRED")

            quotes: list[Quote] = []
            if item.image_urls:
                # 以图搜款：上传首图
                upload = page.locator(self.selectors["image_upload"]).first
                upload.set_input_files_from_url(item.image_urls[0], timeout=30000)
                page.wait_for_timeout(3000)
            else:
                box = page.locator(self.selectors["search_input"]).first
                box.fill(item.title[:60])
                page.locator(self.selectors["search_btn"]).first.click(timeout=5000)
                page.wait_for_timeout(3000)

            if detect_page_changed(page, [self.selectors["result_row"]]):
                raise CollectorError("1688 页面疑似改版，请更新选择器", "PAGE_CHANGED")

            rows = page.locator(self.selectors["result_row"]).all()[:max_suppliers]
            for row in rows:
                try:
                    link = row.locator("a[href]").first.get_attribute("href")
                    title = row.locator(self.selectors["result_title"]).first.inner_text(timeout=2000).strip()
                    supplier = (
                        row.locator(self.selectors["supplier_name"]).first.inner_text(timeout=1500).strip()
                        or "unknown"
                    )
                    if not link or not title:
                        continue
                    # 进商品页 → 选规格 → 订单确认页读价（不下单）
                    page.goto(link, timeout=45000)
                    page.wait_for_timeout(2000)
                    confirm = page.locator(self.selectors["confirm_btn"])
                    if confirm.count() > 0:
                        confirm.first.click(timeout=5000)
                        page.wait_for_timeout(1500)
                    price_txt = page.locator(self.selectors["order_price"]).first.inner_text(timeout=3000)
                    unit_cost = self._parse_price(price_txt)
                    if unit_cost > 0:
                        quotes.append(
                            Quote(
                                supplier_name=supplier,
                                sku_name=title[:120],
                                unit_cost=round(unit_cost, 2),
                                raw_url=page.url,
                            )
                        )
                except Exception:
                    continue
            return quotes
        except CollectorError:
            raise
        except Exception as e:
            raise CollectorError(f"1688 询价失败：{e}", "UNEXPECTED") from e
        finally:
            page.close()

    def probe(self) -> bool:
        try:
            page = self.browser.page()
            page.goto("https://www.1688.com", timeout=20000)
            ok = not page.locator(self.selectors["login_gate"]).first.is_visible(timeout=2000)
            page.close()
            return ok
        except Exception:
            return False

    @staticmethod
    def _parse_price(text: str) -> float:
        import re

        m = re.search(r"[\d.]+", (text or "").replace(",", ""))
        return float(m.group()) if m else 0.0
