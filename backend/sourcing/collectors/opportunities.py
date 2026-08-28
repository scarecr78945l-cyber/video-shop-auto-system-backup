"""视频号商机中心采集器：机会品列表（微信小店后台 /shop/goods/opprotunity）。

- 共享浏览器（CDP 9223，与抖店罗盘/1688/淘宝共用登录态）
- 商机中心按类目筛选显示机会品；采集器读当前筛选下的机会品列表
- 表格列：商品(0) 商机来源(1) 状态(2) 操作(3)
- 取数方式：配置 url_template → 导航；否则复用商机中心已打开的页面
"""

from __future__ import annotations

from ..config import CollectorConfig
from ..models import SourceItem
from .base import Collector, CollectorError
from .browser import SharedBrowser

DEFAULT_SELECTORS = {
    "home_url": "https://store.weixin.qq.com/shop/goods/opprotunity",
    "row": "table tbody tr",
    "columns": {"title": 0, "source": 1, "status": 2},
    "login_gate": "[class*='login']",
    "verify_gate": "[class*='captcha'], [class*='verify']",
}


class OpportunitiesCollector(Collector):
    source = "opportunities"
    default_boards = ["机会品"]

    def __init__(self, config: CollectorConfig):
        super().__init__(config)
        self.selectors = {**DEFAULT_SELECTORS, **config.selectors}
        urls = {b.name: b.url_template for b in config.boards if b.url_template}
        self.board_urls = {**{"机会品": ""}, **urls}
        self.browser = SharedBrowser(config.cdp_port, config.chrome_path)

    def collect_board(self, board: str, limit: int = 200) -> list[SourceItem]:
        url = self.board_urls.get(board, "")
        if url:
            page = self.browser.page()
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(3500)
                self._dismiss_modals(page)
                return self._collect_from_page(page, board, limit)
            finally:
                page.close()
        page = self.browser.current_page("store.weixin.qq.com")
        self._dismiss_modals(page)
        return self._collect_from_page(page, board, limit)

    @staticmethod
    def _dismiss_modals(page) -> None:
        """关闭升级公告等弹窗，避免遮挡内容。"""
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        try:
            page.evaluate(
                "() => { document.querySelectorAll('[class*=modal],[class*=Modal],"
                "[class*=dialog],[class*=Dialog],[class*=mask],[class*=popup]')"
                ".forEach(e => e.remove()); }"
            )
        except Exception:
            pass

    def _collect_from_page(self, page, board: str, limit: int) -> list[SourceItem]:
        try:
            if page.locator(self.selectors["row"]).count() == 0:
                raise CollectorError(
                    f"商机中心未找到机会品表格（{board}），请确认在商机中心页面",
                    "PAGE_CHANGED",
                )
            cols = self.selectors.get("columns") or DEFAULT_SELECTORS["columns"]
            items: list[SourceItem] = []
            seen: set[str] = set()
            rows = page.locator(self.selectors["row"]).all()
            for r in rows:
                if len(items) >= limit:
                    break
                tds = r.locator("td").all()
                if len(tds) <= max(cols.values()):
                    continue

                def cell(idx: int) -> str:
                    try:
                        return tds[idx].evaluate("el => (el.textContent || '').trim()") or ""
                    except Exception:
                        try:
                            return tds[idx].inner_text(timeout=1500) or ""
                        except Exception:
                            return ""

                title = cell(cols["title"]).strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                # 商机来源列可能含「价格区间」等展示信息
                items.append(
                    SourceItem(
                        source=self.source,
                        board=board,
                        platform_item_id=f"{board}:{title[:40]}",
                        title=title,
                        rank=len(items) + 1,
                        category="",
                        image_urls=self._extract_images(r),
                        raw={"board": board, "source": cell(cols.get("source", 1))[:80]},
                    )
                )
            if not items:
                raise CollectorError(
                    f"商机中心机会品列表为空（{board}），可尝试切换类目筛选后重采",
                    "NO_MATCH",
                )
            return items
        except CollectorError:
            raise
        except Exception as e:
            raise CollectorError(f"商机中心采集失败（{board}）：{e}", "UNEXPECTED") from e

    def probe(self) -> bool:
        try:
            page = self.browser.page()
            page.goto(self.selectors.get("home_url", "https://store.weixin.qq.com/shop/goods/opprotunity"), timeout=20000)
            ok = not page.locator(self.selectors["login_gate"]).first.is_visible(timeout=2000)
            page.close()
            return ok
        except Exception:
            return False

    @staticmethod
    def _extract_images(row) -> list[str]:
        urls = []
        try:
            for img in row.locator("img").all()[:4]:
                src = img.get_attribute("src") or img.get_attribute("data-src")
                if src and src.startswith("http"):
                    urls.append(src)
        except Exception:
            pass
        return urls
