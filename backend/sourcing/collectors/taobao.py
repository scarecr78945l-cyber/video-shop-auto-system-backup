"""淘宝参考素材采集器：同款素材（图片）收集，供素材模块消费。"""

from __future__ import annotations

from ..config import CollectorConfig
from ..models import SourceItem
from .base import CollectorError, QuoteCollector
from .browser import SharedBrowser, detect_page_changed

DEFAULT_SELECTORS = {
    "search_input": "input[placeholder*='搜索'], input[class*='search']",
    "search_btn": "button[class*='search'], .search-btn",
    # A6（v1.1）：result_row 仅用于改版检测（detect_page_changed），
    # 保留宽泛 [class*='item'] 兜底防改版误报 PAGE_CHANGED——登记「待真实页面校准」
    "result_row": ".items .item, [class*='item']",
    "result_title": ".title, [class*='title']",
    # A6（v1.1）：image 收窄到结果行内图片，避免全页 img 收集导航/广告图；
    # 窄选择器未命中时 quote() 回退全页 img（原行为，见代码注释）
    "image": ".items .item img, [class*='item'] img",
    "next_page": ".next, [class*='next']",
    "login_gate": ".login-modal, [class*='login']",
    "verify_gate": ".captcha, [class*='verify']",
}


class TaobaoReferenceCollector(QuoteCollector):
    source = "taobao"

    def __init__(self, config: CollectorConfig):
        super().__init__(config)
        self.selectors = {**DEFAULT_SELECTORS, **config.selectors}
        self.browser = SharedBrowser(config.cdp_port, config.chrome_path)

    def quote(self, item: SourceItem, max_images: int = 12) -> list[dict]:
        """按标题搜索同款，收集参考图 URL。"""
        page = self.browser.page()
        try:
            page.goto(self.selectors.get("home_url", "https://www.taobao.com"), timeout=45000)
            if page.locator(self.selectors["login_gate"]).first.is_visible(timeout=3000):
                raise CollectorError("淘宝登录态失效，需人工登录", "AUTH_REQUIRED")
            box = page.locator(self.selectors["search_input"]).first
            box.fill(item.title[:40])
            page.locator(self.selectors["search_btn"]).first.click(timeout=5000)
            page.wait_for_timeout(3000)
            if detect_page_changed(page, [self.selectors["result_row"]]):
                raise CollectorError("淘宝页面疑似改版，请更新选择器", "PAGE_CHANGED")

            urls: list[str] = []
            seen: set[str] = set()
            img_loc = page.locator(self.selectors["image"])
            if img_loc.count() == 0:
                # A6 兜底：窄选择器未命中（页面改版/结构差异）时回退全页 img，保持原行为
                img_loc = page.locator("img")
            for _ in range(5):
                for img in img_loc.all():
                    src = img.get_attribute("src") or img.get_attribute("data-src") or ""
                    if src.startswith("http") and src not in seen:
                        seen.add(src)
                        urls.append(src)
                    if len(urls) >= max_images:
                        break
                if len(urls) >= max_images:
                    break
                next_btn = page.locator(self.selectors["next_page"])
                if next_btn.count() == 0 or not next_btn.first.is_enabled():
                    break
                next_btn.first.click(timeout=5000)
                page.wait_for_timeout(800)
            if not urls:
                raise CollectorError("淘宝同款无参考素材", "NO_MATCH")
            return [{"kind": "reference_images", "urls": urls}]
        except CollectorError:
            raise
        except Exception as e:
            raise CollectorError(f"淘宝参考采集失败：{e}", "UNEXPECTED") from e
        finally:
            page.close()

    def probe(self) -> bool:
        try:
            page = self.browser.page()
            page.goto("https://www.taobao.com", timeout=20000)
            ok = not page.locator(self.selectors["login_gate"]).first.is_visible(timeout=2000)
            page.close()
            return ok
        except Exception:
            return False
