"""有米云采集器：商品销售榜（独立特制浏览器，CDP 9555，console.youshu.youcloud.com）。

实测页面为 Element UI 表格，按列索引提取：
  #(0) 商品(1) 推广方式(3) 店铺(4) 价格（元）(5) 新增销量(7) 累计销量(10)
列映射可配置（selectors.columns），页面改版只改配置。
数字支持中文单位：593万+ → 5930000；1000万-2500万 → 10000000。

两种取数方式：
- 配置了 url_template → 新开页导航到榜单 URL；
- 未配置 → 直接读取浏览器当前活动页（用户已手动打开榜单页，推荐）。
"""

from __future__ import annotations

import re

from ..config import CollectorConfig
from ..models import SourceItem
from .base import Collector, CollectorError
from .browser import SharedBrowser, detect_page_changed

DEFAULT_SELECTORS = {
    "home_url": "https://console.youshu.youcloud.com/",
    "row": ".el-table__body-wrapper tr",
    "columns": {"rank": 0, "title": 1, "price": 5, "sales": 7},
    "next_page": ".el-pagination .btn-next, .el-pagination__next",
    "login_gate": ".login-modal, [class*='login']",
    "verify_gate": ".captcha, [class*='verify']",
}


def parse_num(text: str) -> float:
    """解析数字，支持中文单位：593万+ → 5930000；1.2亿 → 120000000；'2.01' → 2.01。"""
    text = (text or "").replace(",", "").strip()
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


class YoumiCollector(Collector):
    source = "youmi"
    default_boards = ["商品榜"]

    def __init__(self, config: CollectorConfig):
        super().__init__(config)
        self.selectors = {**DEFAULT_SELECTORS, **config.selectors}
        urls = {b.name: b.url_template for b in config.boards if b.url_template}
        self.board_urls = {**{"商品榜": ""}, **urls}
        self.browser = SharedBrowser(config.cdp_port, config.chrome_path)

    def collect_board(self, board: str, limit: int = 200) -> list[SourceItem]:
        url = self.board_urls.get(board, "")
        if url:
            page = self.browser.page()
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                return self._collect_from_page(page, board, limit)
            finally:
                page.close()
        # 未配置 url_template：直接读有米云浏览器中的榜单页（按域名定位）
        return self._collect_from_page(
            self.browser.current_page("console.youshu.youcloud.com"), board, limit
        )

    def _collect_from_page(self, page, board: str, limit: int) -> list[SourceItem]:
        try:
            if page.locator(self.selectors["login_gate"]).first.is_visible(timeout=2000):
                raise CollectorError("有米云登录态失效，需人工登录", "AUTH_REQUIRED")
            if page.locator(self.selectors["verify_gate"]).first.is_visible(timeout=2000):
                raise CollectorError("有米云触发安全验证", "VERIFICATION_REQUIRED")
            if detect_page_changed(page, [self.selectors["row"]]):
                raise CollectorError(
                    f"有米云页面疑似改版或未在榜单页（{board}），"
                    "请在有米云浏览器打开商品销售榜页，或运行 inspect-page 更新选择器",
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

                    def cell(idx: int) -> str:
                        # 商品标题渲染在隐藏的 el-popover 里，inner_text 拿不到，用 textContent
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
                    items.append(
                        SourceItem(
                            source=self.source,
                            board=board,
                            platform_item_id=f"{board}:{title[:40]}",
                            title=title,
                            price=round(parse_num(cell(cols["price"])), 2),
                            sales=int(parse_num(cell(cols["sales"]))),
                            rank=int(parse_num(cell(cols["rank"])) or len(items) + 1),
                            image_urls=self._extract_images(r),
                            raw={"board": board},
                        )
                    )
                if len(items) >= limit:
                    break
                next_btn = page.locator(self.selectors["next_page"])
                if next_btn.count() == 0 or not next_btn.first.is_enabled():
                    break
                next_btn.first.click(timeout=5000)
                page.wait_for_timeout(800)
            if not items:
                raise CollectorError(f"有米云榜单 {board} 空转（无有效行）", "NO_MATCH")
            return items
        except CollectorError:
            raise
        except Exception as e:
            raise CollectorError(f"有米云采集失败（{board}）：{e}", "UNEXPECTED") from e

    def _locate_columns(self, page) -> dict[str, int]:
        """按表头动态定位列索引；显式配置的 columns 优先。"""
        configured = self.selectors.get("columns")
        if configured:
            return {k: int(v) for k, v in configured.items()}
        heads = page.locator(".el-table__header th").all_text_contents()
        cols: dict[str, int] = {}
        # 只取前 13 个表头（Element UI fixed 列会产生重复表头，取第一组）
        for i, h in enumerate(heads[:14]):
            t = h.strip()
            if t == "#":
                cols.setdefault("rank", i)
            elif "商品" in t:
                cols.setdefault("title", i)
            elif "价格" in t:
                cols.setdefault("price", i)
            elif t == "新增销量":
                cols.setdefault("sales", i)
        if "title" not in cols:
            raise CollectorError(
                "有米云表格未显示「商品」列（用户可能在列设置里隐藏了）。"
                "请在浏览器列设置勾选商品列，或配置 selectors.columns 指定列索引",
                "PAGE_CHANGED",
            )
        for k in ("rank", "price", "sales"):
            if k not in cols:
                cols[k] = 0
        return cols

    def probe(self) -> bool:
        try:
            page = self.browser.page()
            page.goto(self.selectors.get("home_url", "https://console.youshu.youcloud.com/"), timeout=20000)
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
