"""抖店电商罗盘采集器：商品榜单 / 店铺飙升榜（抖音电商官方数据工具，Aurora 表格）。

- 共享浏览器（config.doudian.cdp_port 默认 9223）
- 商品榜单页：市场 → 市场排行 → 商品榜单（/shop/chance/rank-product，默认「总榜」tab）
- 表格列：排名(0,变化标记) 商品(1) 店铺(2) 支付金额(3) 点击(4) 成交件数(5) 转化率(6)
- 飙升榜（A3，2026-08-29 实测）：市场 → 市场排行 → 店铺榜单（/shop/chance/rank-shop）
  页内「飙升榜」tab（与总榜同 URL，页内切换；表头含「订单提升量」，店铺维度榜单）
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

# A3（2026-08-29 实测）：board 名 → 导航后需点击的页内 tab 文本。
# 罗盘各榜单入口为「同页内 tab 切换」（URL 不区分榜单）：如店铺榜单页 rank-shop 的
# tab 全集为 总榜/飙升榜/搜索榜/同行低退榜，默认落在「总榜」，采集前必须切到目标 tab。
# 商品榜（rank-product）默认即「总榜」，无需切换 → 不进映射，行为零变化。
BOARD_TABS: dict[str, str] = {"飙升榜": "飙升榜"}


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
            # A3：需要页内 tab 的榜单（如飙升榜=店铺榜单页内 tab）先切到目标 tab 再采集；
            # 无映射的榜单（商品榜，默认总榜）直接跳过，零影响。
            self._ensure_board_tab(page, board)
            # Aurora 表格首行是隐藏表头（height:0），用行数判断而非 is_visible
            if page.locator(self.selectors["row"]).count() < 2:
                raise CollectorError(
                    f"抖店罗盘页面疑似改版或未在榜单页（{board}），"
                    "请打开 市场 → 市场排行 → 对应榜单页，或运行 inspect-page 校准",
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
                    # 跳过表头行（第一行 cell 是表头文本）；A3：店铺榜首行为「未上榜」占位店铺
                    head0 = tds[0].inner_text(timeout=800).strip() if tds else ""
                    if head0 in ("排名", "未上榜"):
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
                            # A3：shop 列用动态定位（商品榜=列2；店铺榜=店铺信息列1，原硬编码列2 会取到「订单提升量」）
                            raw={"board": board, "shop": cell(cols.get("shop", 2))[:40]},
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
        """按表头动态定位列索引；config 显式配置的 columns 优先。

        A4：只认 config.selectors 里的 columns（config 为空 → 走动态表头定位）。
        DEFAULT_SELECTORS 的 columns 仅作文档兜底，不再短路动态定位。
        A3：适配店铺榜单（rank-shop）表头——「商品曝光人数/商品点击人数/TOP成交商品」等
        指标列含「商品」字样但非商品名/实测为空，需排除；店铺信息列作 title 兜底
        （店铺维度榜单：店铺名即榜单主体）。
        """
        configured = self.config.selectors.get("columns")
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
            elif "商品" in t and not any(x in t for x in ("人数", "曝光", "点击", "TOP")):
                cols.setdefault("title", i)
            elif "店铺信息" in t:
                # A3：店铺榜单（rank-shop）无商品名列，「TOP成交商品」列实测为空，
                # 店铺名（店铺信息列）作 title 兜底（采集语义=店铺维度榜单）。
                cols.setdefault("shop", i)
                cols.setdefault("title", i)
            elif "店铺" in t:
                cols.setdefault("shop", i)
            elif "支付金额" in t or "成交额" in t:
                cols.setdefault("pay", i)
            elif "成交件数" in t or "销量" in t or "成交订单数" in t:
                cols.setdefault("sales", i)
        if "title" not in cols:
            raise CollectorError("抖店罗盘表格未找到「商品」列，请确认在榜单页", "PAGE_CHANGED")
        cols.setdefault("rank", 0)
        cols.setdefault("pay", 3)
        cols.setdefault("sales", 0)
        return cols

    # A3：按精确可见文本点击页内 tab（仿旧系统 _click_exact_text，作用域限当前页）。
    # 用 dispatchEvent 模拟用户点击，避开遮挡元素；返回是否命中可点节点。
    _CLICK_TAB_JS = """(label) => {
        const visible = node => Boolean(node && (
            node.offsetWidth || node.offsetHeight || node.getClientRects().length
        ));
        const nodes = Array.from(document.querySelectorAll(
            '[role="tab"], button, a, li, span, div'
        )).filter(node => visible(node) && (node.textContent || '').trim() === label);
        const direct = nodes.find(node => node.matches(
            'button, a, li, [role="tab"]'
        )) || nodes.find(node => getComputedStyle(node).cursor === 'pointer') || nodes[0];
        const target = direct && (direct.closest(
            'button, a, li, [role="tab"], [class*="tab"]'
        ) || direct);
        if (!target) return false;
        target.scrollIntoView({block: 'center', inline: 'center'});
        for (const type of ['mouseover', 'mousedown', 'mouseup']) {
            target.dispatchEvent(new MouseEvent(type, {
                bubbles: true, cancelable: true, view: window
            }));
        }
        target.click();
        return true;
    }"""

    def _ensure_board_tab(self, page, board: str) -> None:
        """导航后把页面切到 board 对应的页内 tab（A3：飙升榜=店铺榜单页内 tab）。"""
        tab = BOARD_TABS.get(board)
        if not tab:
            return
        try:
            clicked = page.evaluate(self._CLICK_TAB_JS, tab)
        except Exception as e:
            raise CollectorError(f"抖店罗盘切换榜单 tab 失败（{board}→{tab}）：{e}", "PAGE_CHANGED") from e
        if not clicked:
            raise CollectorError(
                f"抖店罗盘未找到榜单 tab「{tab}」（{board}），"
                "请确认已打开 市场 → 市场排行 → 店铺榜单 页",
                "PAGE_CHANGED",
            )
        page.wait_for_timeout(3000)  # 等 tab 切换后表格数据渲染（首次导航加载慢，A3 实测加固）

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
