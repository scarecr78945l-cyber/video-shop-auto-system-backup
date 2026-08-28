"""抖店电商罗盘采集器：商品榜单（抖音电商官方数据工具，Aurora 表格）。

- 共享浏览器（config.doudian.cdp_port 默认 9223）
- 商品榜单页：市场 → 市场排行 → 商品榜单（/shop/chance/rank-product）
- 表格列：排名(0,变化标记) 商品(1) 店铺(2) 支付金额(3) 点击(4) 成交件数(5) 转化率(6)
- 标题在隐藏元素里，用 textContent 提取；价格取标题「价格带 ¥XX」；销量取成交件数(区间取最小)
- 取数方式：配置 url_template → 导航；否则复用罗盘浏览器中已打开的榜单页
"""

from __future__ import annotations

import re

from ..config import CollectorConfig
from ..models import SourceItem
from .base import Collector, CollectorError
from .browser import SharedBrowser, detect_page_changed

DEFAULT_SELECTORS = {
    "home_url": "https://compass.jinritemai.com/shop/chance/rank-product",
    "row": ".aurora-table-tbody tr",
    "columns": {"title": 1, "sales": 5},
    "next_page": ".aurora-pagination-next, [class*='pagination'] [class*='next']",
    "login_gate": ".login, [class*='login']",
    "verify_gate": ".captcha, [class*='verify'], [class*='captcha']",
}


def parse_num(text: str) -> float:
    """解析数字，支持中文单位与货币符号：¥1,000万 → 10000000；10万-25万 → 100000；'2.01' → 2.01。"""
    text = (text or "").replace(",", "").replace("¥", "").strip()
    if not text:
        return 0.0
    m = re.match(r"([\d.]+)\s*([万亿]?)", text)
    if not m:
        return 0.0
    v = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        v *= 10000
    elif unit == "亿":
        v *= 100000000
    return v


def price_from_title(title: str) -> float | None:
    """从标题提取「价格带 ¥XX」，取首个价格。"""
    m = re.search(r"价格带\s*¥?\s*([\d.]+)", title or "")
    return float(m.group(1)) if m else None


class DoudianCollector(Collector):
    source = "doudian"
    default_boards = ["商品榜", "飙升榜"]

    def __init__(self, config: CollectorConfig):
        super().__init__(config)
        self.selectors = {**DEFAULT_SELECTORS, **config.selectors}
        urls = {b.name: b.url_template for b in config.boards if b.url_template}
        self.board_urls = {**{"商品榜": "", "飙升榜": ""}, **urls}
        self.browser = SharedBrowser(config.cdp_port, config.chrome_path)

    def collect_board(self, board: str, limit: int = 200) -> list[SourceItem]:
        url = self.board_urls.get(board, "")
        if url:
            try:
                page = self.browser.page()
                try:
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_timeout(4500)
                    return self._collect_from_page(page, board, limit)
                finally:
                    page.close()
            except CollectorError:
                # 导航失败（弹窗/加载慢/页面变化）→ 回退读罗盘已打开的榜单页
                pass
        return self._collect_from_page(
            self.browser.current_page("compass.jinritemai.com"), board, limit
        )

    def _collect_from_page(self, page, board: str, limit: int) -> list[SourceItem]:
        try:
            if page.locator(self.selectors["login_gate"]).first.is_visible(timeout=2000):
                raise CollectorError("抖店罗盘登录态失效，需人工登录", "AUTH_REQUIRED")
            if page.locator(self.selectors["verify_gate"]).first.is_visible(timeout=2000):
                raise CollectorError("抖店罗盘触发安全验证", "VERIFICATION_REQUIRED")
            # Aurora 表格首行是隐藏表头（height:0），用行数判断而非 is_visible
            if page.locator(self.selectors["row"]).count() < 2:
                raise CollectorError(
                    f"抖店罗盘页面疑似改版或未在商品榜单页（{board}），"
                    "请打开 市场 → 市场排行 → 商品榜单，或运行 inspect-page 校准",
                    "PAGE_CHANGED",
                )

            cols = self._locate_columns(page)
            items: list[SourceItem] = []
            seen: set[str] = set()
            for _ in range(30):
                rows = page.locator(self.selectors["row"]).all()
                for r in rows:
                    if len(items) >= limit:
                        break
                    tds = r.locator("td").all()
                    if len(tds) <= max(cols.values()):
                        continue
                    # 跳过表头行（第一行 cell 是表头文本）
                    head0 = tds[0].inner_text(timeout=800).strip() if tds else ""
                    if head0 == "排名":
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
                    price = price_from_title(title) or round(parse_num(cell(cols.get("pay", 3))), 2)
                    items.append(
                        SourceItem(
                            source=self.source,
                            board=board,
                            platform_item_id=f"{board}:{title[:40]}",
                            title=title,
                            price=price or 0.0,
                            sales=int(parse_num(cell(cols["sales"]))),
                            rank=len(items) + 1,
                            image_urls=self._extract_images(r),
                            raw={"board": board, "shop": cell(2)[:40]},
                        )
                    )
                if len(items) >= limit:
                    break
                next_btn = page.locator(self.selectors["next_page"])
                if next_btn.count() == 0 or not next_btn.first.is_enabled():
                    break
                next_btn.first.click(timeout=5000)
                page.wait_for_timeout(1000)
            if not items:
                raise CollectorError(f"抖店罗盘榜单 {board} 空转（无有效行）", "NO_MATCH")
            return items
        except CollectorError:
            raise
        except Exception as e:
            raise CollectorError(f"抖店罗盘采集失败（{board}）：{e}", "UNEXPECTED") from e

    def _locate_columns(self, page) -> dict[str, int]:
        """按表头动态定位列索引；显式配置的 columns 优先。"""
        configured = self.selectors.get("columns")
        if configured:
            cols = {k: int(v) for k, v in configured.items()}
            cols.setdefault("pay", 3)
            return cols
        heads = page.locator(".aurora-table-header-cell, .aurora-table-th, th").all_text_contents()
        cols: dict[str, int] = {}
        for i, h in enumerate(heads[:10]):
            t = h.strip()
            if t == "排名":
                cols.setdefault("rank", i)
            elif "商品" in t:
                cols.setdefault("title", i)
            elif "店铺" in t:
                cols.setdefault("shop", i)
            elif "支付金额" in t or "成交额" in t:
                cols.setdefault("pay", i)
            elif "成交件数" in t or "销量" in t:
                cols.setdefault("sales", i)
        if "title" not in cols:
            raise CollectorError("抖店罗盘表格未找到「商品」列，请确认在商品榜单页", "PAGE_CHANGED")
        cols.setdefault("rank", 0)
        cols.setdefault("pay", 3)
        cols.setdefault("sales", 0)
        return cols

    def probe(self) -> bool:
        try:
            page = self.browser.page()
            page.goto(self.selectors.get("home_url", "https://compass.jinritemai.com/shop/chance/rank-product"), timeout=20000)
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
