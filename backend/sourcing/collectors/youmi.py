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
from datetime import date, timedelta

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


def render_board_url(
    template: str, lookback_days: int = 7, today: date | None = None
) -> str:
    """渲染榜单 URL：把 {start_date}/{end_date} 占位符替换为 YYYY-MM-DD。

    - end = 当天（today，默认 date.today()）；start = end - lookback_days
    - 模板不含占位符 → 原样返回（兼容其他来源/旧模板）
    - 用 str.replace 而非 str.format，避免 URL 中其他花括号导致异常
    """
    if "{start_date}" not in template and "{end_date}" not in template:
        return template
    end = today or date.today()
    start = end - timedelta(days=max(0, lookback_days))
    return (
        template.replace("{start_date}", start.isoformat()).replace(
            "{end_date}", end.isoformat()
        )
    )


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


# A6（v1.1 迭代，2026-08-29）：S3c 真实采集实测 _extract_images imgs=0——
# 真实页面商品图疑似 lazy 加载：src 常为占位符（data:/blob:/空/相对路径），
# 旧实现 `src or data-src` 的 or 短路导致 data-src 永不读取。
# 按优先级读取 lazy 属性；data:/blob:/空/相对路径一律过滤，只收 http(s) 真实 URL。
LAZY_IMG_ATTRS: tuple[str, ...] = (
    "src",
    "data-src",
    "data-original",
    "data-lazy-src",
    "data-lazy",
    "srcset",
    "data-srcset",
)


def _first_http_url(attrs: dict[str, str | None]) -> str:
    """从一组图片属性中取第一个 http(s) URL；srcset 取首个候选；无则空串。

    - 按 LAZY_IMG_ATTRS 优先级逐个尝试，data:/blob: 占位符直接跳过（不短路），
      空值跳过——避免 `src=data:...` 占位导致 data-src/srcset 永不读取（S3c imgs=0 根因）；
    - srcset 形如 "https://a.jpg 1x, https://b.jpg 2x" → 取第一个候选；
    - 只收 http:// 与 https://（data:/blob:/相对路径/protocol-relative 均过滤；
      data: SVG 可能内嵌 http 命名空间，故先按前缀整值跳过，不扫描）。
    """
    for key in LAZY_IMG_ATTRS:
        raw = (attrs.get(key) or "").strip()
        if not raw or raw.startswith(("data:", "blob:")):
            continue
        m = re.search(r"https?://[^\s,]+", raw)
        if m:
            return m.group(0)
    return ""


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
            # A2：url_template 含 {start_date}/{end_date} 占位符 → 按 lookback_days 动态生成日期
            url = render_board_url(url, lookback_days=self.config.lookback_days)
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
                        # text_content 优先：等价 evaluate textContent（含隐藏 el-popover 标题），
                        # 且带超时；evaluate 无 timeout 参数，页面渲染进程挂起时 driver 无限阻塞
                        # （P-028 实测根因，2026-08-31 总控定）
                        try:
                            return tds[idx].text_content(timeout=1500) or ""
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
                            image_urls=self._extract_images(r, cols.get("title")),
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
        """按表头动态定位列索引；config 显式配置的 columns 优先。

        A4：只认 config.selectors 里的 columns（config 为空 → 走动态表头定位）。
        DEFAULT_SELECTORS 的 columns 仅作文档兜底，不再短路动态定位。
        """
        configured = self.config.selectors.get("columns")
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
    def _extract_images(row, title_cell: int | None = None) -> list[str]:
        """提取行内商品图 URL（A6 收敛：lazy 属性 + 收窄到商品列容器）。

        - lazy 加载兼容：src 为占位（data:/blob:/空/相对路径）时继续读
          data-src / data-original / data-lazy-src / data-lazy / srcset / data-srcset；
        - 收窄：优先取 title_cell 指定 td（商品列）内的 img（避免收集排名/推广方式
          等非商品图），该容器未命中再回退行内 img（防御，不依赖真实 DOM 结构——
          列容器取不到时行为与旧版一致）；
        - 只收 http(s) 真实 URL，去重，最多 4 张；任何异常返回空列表，不阻断采集。
        """
        try:
            locators: list = []
            if title_cell is not None:
                locators.append(row.locator("td").nth(title_cell).locator("img"))
            locators.append(row.locator("img"))  # 兜底：列容器未命中时回退行内（含 title_cell=None）
        except Exception:
            return []
        urls: list[str] = []
        seen: set[str] = set()
        try:
            for loc in locators:
                for img in loc.all()[:4]:
                    url = _first_http_url({k: img.get_attribute(k) for k in LAZY_IMG_ATTRS})
                    if url and url not in seen:
                        seen.add(url)
                        urls.append(url)
                if urls:
                    break  # 精确容器命中即止，不再取兜底行内
        except Exception:
            pass
        return urls[:4]
