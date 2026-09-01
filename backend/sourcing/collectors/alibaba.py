"""1688 逐 SKU 真实询价采集器（搜图结果页读价，不下单）。

P-027（2026-08-31 用户裁定）：以图搜款唯一方式，废弃标题搜索；无图 → NO_MATCH。
P-028（2026-08-31 真实链路修复，本文件当前实现）：
  1688 首页「以图搜款」上传后实际跳转到独立搜图页
    air.1688.com/kapp/1688-search/pc-image-search/?imageAddress=<图URL>
  ——直接导航该 URL 即可免上传出结果（实测 2s 渲染 60 张结果卡片）；
  结果卡片 `data-renderkey` 携带 offerId（形如 1_0_normal_b2b-xxx_1052811778069，末段即 ID），
  据此直链 detail.1688.com/offer/<id>.html，读详情页价格区（.price-info 取最小）为最低有效成本；
  订单确认页读价（点「立即下单」）因 SKU 选择浮层结构不稳定，降级为失败静默回退。
  （旧链路：首页 set_input_files 上传 → 页面跳 air 页但旧选择器 .card-item 匹配 0 行
   → 误判 PAGE_CHANGED → 询价全失败；本文件已废弃该路径。）

fixtures 模式见 fixtures.FixtureQuoteCollector。
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from ..config import CollectorConfig
from ..models import Quote, SourceItem
from .base import CollectorError, QuoteCollector
from .browser import SharedBrowser

DEFAULT_SELECTORS = {
    # 以图搜款结果页（air.1688.com，免上传：imageAddress 参数直链）
    "search_url": "https://air.1688.com/kapp/1688-search/pc-image-search/",
    # 结果卡片：CSS Modules 哈希类名，按语义前缀匹配（后缀改版不失效）
    "result_row": "[class*='searchOfferItem']",
    "result_title": "[class*='titleText']",
    "supplier_name": "[class*='shopName']",
    "result_price": ".offer-price-row, [class*='offerPriceRow']",
    # 商品详情页价格区（主读价路径；多档价格取最小）
    "detail_price": ".price-info, .price-comp, .price-component",
    # 订单确认页读价（降级保留；SKU 浮层时代不稳定）
    "order_price": ".order-price, .price-box",
    "confirm_btn": ".confirm-btn, button:has-text('确认')",
    "login_gate": ".login-modal, [class*='login']",
    "verify_gate": ".captcha, [class*='verify']",
}

# 结果卡片 offerId 承载属性（data-renderkey 实测格式：1_0_normal_b2b-<uid>_<offerId>）
_OFFER_ID_ATTRS = ("data-renderkey", "data-aplus-report")


class AlibabaQuoteCollector(QuoteCollector):
    source = "alibaba"

    def __init__(self, config: CollectorConfig):
        super().__init__(config)
        self.selectors = {**DEFAULT_SELECTORS, **config.selectors}
        self.browser = SharedBrowser(config.cdp_port, config.chrome_path)

    def quote(self, item: SourceItem, max_suppliers: int = 5) -> list[Quote]:
        """以图搜款（唯一方式，P-027）→ 直链商品详情页读价（P-028）。

        无图时尝试从 raw 携带的候选图（taobao_image_urls/榜单图）取首图；
        仍无图 → NO_MATCH「无图不可以图搜款」且**不打开浏览器**（省资源），不退回标题搜索。
        """
        image_url = self._resolve_image_url(item)
        if not image_url:
            raise CollectorError(
                "无图不可以图搜款（标题搜索已废弃 P-027）：需采集器携带商品图",
                "NO_MATCH",
            )
        page = self.browser.page()
        try:
            page.goto(
                self._build_search_url(image_url),
                timeout=60000,
                wait_until="domcontentloaded",
            )
            if not self._wait_results(page):
                # P-036 回退：图 URL 签名失效（umcdn auth_key 403，见 pitfall-log P-036）
                # → 下载本地图 → 1688 首页上传搜图（不依赖签名 URL，彻底根治时效问题）
                tmp_img = self._download_image(image_url)
                try:
                    page.goto(
                        "https://www.1688.com/", timeout=45000,
                        wait_until="domcontentloaded",
                    )
                    page.wait_for_timeout(1500)
                    upload = page.locator("input[type=file]").first
                    upload.set_input_files(tmp_img, timeout=30000)
                finally:
                    tmp_img.unlink(missing_ok=True)
                page.wait_for_timeout(3000)
                if not self._wait_results(page):
                    raise CollectorError("1688 搜图结果未渲染（页面改版或加载失败）", "PAGE_CHANGED")
            if page.locator(self.selectors["login_gate"]).first.is_visible(timeout=2000):
                raise CollectorError("1688 登录态失效，需人工登录", "AUTH_REQUIRED")
            if page.locator(self.selectors["verify_gate"]).first.is_visible(timeout=2000):
                raise CollectorError("1688 触发安全验证", "VERIFICATION_REQUIRED")

            quotes: list[Quote] = []
            # P-038（2026-09-01 实测）：先在搜图结果页**一次性提取全部卡片数据**
            # （offerId/标题/供应商），再逐个 goto detail 读价——
            # 旧实现循环内逐卡 goto，首次导航后其余卡片 ElementHandle 引用旧页面
            # 全部失效（get_attribute 30s 超时）→ 每商品实际只询到 1 家。
            rows = page.locator(self.selectors["result_row"]).all()[:max_suppliers]
            card_data: list[tuple[str, str, str]] = []
            for row in rows:
                try:
                    offer_id = self._offer_id_from_row(row)
                    title = (
                        row.locator(self.selectors["result_title"])
                        .first.inner_text(timeout=2000)
                        .strip()
                    )
                    supplier = (
                        row.locator(self.selectors["supplier_name"])
                        .first.inner_text(timeout=1500)
                        .strip()
                        or "unknown"
                    )
                    if not offer_id or not title:
                        continue
                    card_data.append((offer_id, title, supplier))
                except Exception:
                    continue

            for offer_id, title, supplier in card_data:
                try:
                    detail_url = f"https://detail.1688.com/offer/{offer_id}.html"
                    # wait_until="commit"：只等导航开始（不等 domcontentloaded，detail 页
                    # 资源重加载慢会拖慢询价；渲染由固定等待兜底）
                    page.goto(detail_url, timeout=45000, wait_until="commit")
                    page.wait_for_timeout(1500)
                    # REC-迁移-02（C2）：探测必填上架参数缺失（M4 attrs_complete 门禁消费）
                    missing = self._detect_missing_attrs(page)
                    unit_cost = self._read_detail_price(page)
                    if unit_cost <= 0:  # 详情页价格区改版兜底 → 订单确认页读价（降级）
                        unit_cost = self._read_order_confirm_price(page)
                    if unit_cost > 0:
                        quotes.append(
                            Quote(
                                supplier_name=supplier,
                                sku_name=title[:120],
                                unit_cost=round(unit_cost, 2),
                                raw_url=detail_url,
                                missing_attrs=missing,
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
            page.goto(
                self.selectors.get("search_url", "https://air.1688.com/"),
                timeout=20000,
            )
            ok = not page.locator(self.selectors["login_gate"]).first.is_visible(timeout=2000)
            page.close()
            return ok
        except Exception:
            return False

    # ------------------------------------------------------------ 搜图链路
    @staticmethod
    def _build_search_url(image_url: str) -> str:
        """构造以图搜款结果页直链（P-028：免上传，imageAddress 参数）。"""
        return (
            DEFAULT_SELECTORS["search_url"]
            + "?imageAddress="
            + quote(image_url, safe="")
        )

    def _wait_results(self, page, timeout_ms: int = 20000) -> bool:
        """轮询结果卡片渲染（搜图需先上传图片到 CDN 再返回结果，非即时）。

        实测 air 直链 2s 内渲染卡片：先固定等待 2s 再轮询（间隔 1s，上限 20s），
        避免首帧 count() 空转与长轮询拖慢询价。
        """
        import time

        page.wait_for_timeout(2000)
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                if page.locator(self.selectors["result_row"]).count() > 0:
                    return True
            except Exception:
                pass
            page.wait_for_timeout(1000)
        return False

    @staticmethod
    def _offer_id_from_row(row) -> str:
        """从结果卡片数据属性提取 offerId（P-028）。

        实测 data-renderkey="1_0_normal_b2b-221674209657250c6e_1052811778069"
        → 末段下划线数字即 offerId；data-aplus-report 同款尾段兜底。
        """
        for attr in _OFFER_ID_ATTRS:
            try:
                v = row.get_attribute(attr) or ""
            except Exception:
                v = ""
            m = re.search(r"_(\d{10,})(?:[^0-9]|$)", v)
            if m:
                return m.group(1)
        return ""

    # ------------------------------------------------------------ 读价
    def _read_detail_price(self, page) -> float:
        """商品详情页价格区读最低价（主路径）。

        实测 .price-info 含多档（新人价 ¥8.00 / 老客价 ¥10.00 / ¥12.00），
        取最小数值作为「最低有效成本」；价格区改版时回退宽泛 [class*='price-info']。
        P-038：价格文本可能被字体渲染拆成逐字符换行（"¥\\n2\\n.80"），
        解析前先合并换行（否则 regex 只取到整数位，价格偏低）。
        """
        loc = page.locator(self.selectors["detail_price"])
        if loc.count() == 0:
            loc = page.locator("[class*='price-info']")
        prices: list[float] = []
        for i in range(min(loc.count(), 12)):
            try:
                txt = loc.nth(i).inner_text(timeout=1500).replace("\n", "")
                m = re.search(r"¥\s*([\d.]+)", txt)
                if m:
                    prices.append(float(m.group(1)))
            except Exception:
                continue
        return min(prices) if prices else 0.0

    def _read_order_confirm_price(self, page) -> float:
        """订单确认页读价（降级：点「立即下单」；SKU 浮层时代不稳定，失败返回 0）。

        保留旧能力：确认页直达时读 order_price；任何一步异常静默返回 0，
        由调用方决定是否采用（不阻断询价主链路）。
        """
        try:
            buy = page.locator(
                "button:has-text('立即下单'), button:has-text('马上订购')"
            )
            if buy.count() > 0:
                buy.first.click(timeout=5000)
                page.wait_for_timeout(2500)
            loc = page.locator(self.selectors["order_price"])
            if loc.count() == 0:
                loc = page.locator("[class*='price']")
            txt = loc.first.inner_text(timeout=3000)
            return self._parse_price(txt)
        except Exception:
            return 0.0

    @staticmethod
    def _parse_price(text: str) -> float:
        m = re.search(r"[\d.]+", (text or "").replace(",", ""))
        return float(m.group()) if m else 0.0

    # ------------------------------------------------------------ 图源解析
    @staticmethod
    def _resolve_image_url(item: SourceItem) -> str:
        """以图搜款首图来源解析（P-027：废弃标题搜索后必须带图）。

        优先级：item.image_urls → raw['taobao_image_urls'] → raw['image_url'] → raw['board_image']。
        返回首个 http(s) 图 URL；无 → 空串（调用方抛 NO_MATCH）。
        """
        candidates: list[str] = []
        candidates += list(item.image_urls or [])
        raw = item.raw or {}
        for key in ("taobao_image_urls", "image_url", "board_image", "alibaba_image_urls"):
            v = raw.get(key)
            if isinstance(v, str):
                candidates.append(v)
            elif isinstance(v, list):
                candidates += [str(x) for x in v if isinstance(x, str)]
        for url in candidates:
            url = url.strip()
            if url.startswith("http://") or url.startswith("https://"):
                return url
        return ""

    @staticmethod
    def _download_image(url: str) -> Path:
        """下载图片到临时文件（P-026/P-036：以图搜款上传用；失败抛 CollectorError）。"""
        import tempfile
        import urllib.request

        try:
            tmp = Path(tempfile.gettempdir()) / f"1688_upload_{abs(hash(url))}.jpg"
            urllib.request.urlretrieve(url, tmp)
            return tmp
        except Exception as exc:
            raise CollectorError(f"1688 以图搜款图片下载失败: {type(exc).__name__}", "NO_MATCH") from exc

    # REC-迁移-02（C2）：上架必填参数清单（对照 old-system-assets/listing-requirements.json missing_field_labels）
    REQUIRED_ATTR_LABELS = [
        "适用年龄", "包装清单", "重量", "容量", "适用场景", "类别", "功能",
    ]

    @classmethod
    def _detect_missing_attrs(cls, page) -> list[str]:
        """从商品页属性区探测缺失的必填参数；探测失败返回空列表（不阻断）。"""
        missing: list[str] = []
        try:
            body_text = ""
            # 常见属性容器：class 含 attr/param/spec 的区块；宽松取整页文本（兜底）
            for sel in (".attr-list", ".parameters", "[class*='attr']", "[class*='param']", "[class*='spec']"):
                loc = page.locator(sel).first
                if loc.count() > 0:
                    body_text += " " + loc.inner_text(timeout=1500)
            if not body_text.strip():
                body_text = page.locator("body").first.inner_text(timeout=3000)
            for label in cls.REQUIRED_ATTR_LABELS:
                if label not in body_text:
                    missing.append(label)
        except Exception:
            return []  # 探测失败不阻断询价（保持向后兼容）
        return missing
