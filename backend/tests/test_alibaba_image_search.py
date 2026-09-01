"""P-027/P-028：1688 以图搜款唯一化 + air 搜图直链询价测试。

- P-027：图源解析优先级、无图 NO_MATCH（不标题搜索、不打开浏览器）；
- P-028：_build_search_url 直链构造、_offer_id_from_row 提取、
  _read_detail_price 最低价、quote 全流程 mock（结果卡片 → detail 读价 → Quote）。
"""

import pytest

from sourcing.collectors.alibaba import AlibabaQuoteCollector
from sourcing.collectors.base import CollectorError
from sourcing.config import CollectorConfig
from sourcing.models import SourceItem


def _item(image_urls=None, raw=None):
    return SourceItem(
        source="fixtures", board="b", platform_item_id="x",
        title="测试商品 水杯泡腾片", category="日用",
        image_urls=image_urls or [], raw=raw or {},
    )


# ------------------------------------------------------------------ 图源解析（P-027）
def test_resolve_image_from_image_urls():
    """① 优先 item.image_urls。"""
    it = _item(image_urls=["https://img.example.com/a.jpg"])
    assert AlibabaQuoteCollector._resolve_image_url(it) == "https://img.example.com/a.jpg"


def test_resolve_image_from_raw_candidates():
    """② raw 候选图（taobao_image_urls/榜单图）兜底。"""
    it = _item(raw={"taobao_image_urls": ["https://tb.example.com/1.jpg"]})
    assert AlibabaQuoteCollector._resolve_image_url(it) == "https://tb.example.com/1.jpg"
    it2 = _item(raw={"image_url": "https://img2.example.com/b.jpg"})
    assert AlibabaQuoteCollector._resolve_image_url(it2) == "https://img2.example.com/b.jpg"


def test_resolve_image_none_returns_empty():
    """③ 无图 → 空串（不再退回标题搜索）。"""
    it = _item()
    assert AlibabaQuoteCollector._resolve_image_url(it) == ""


def test_quote_without_image_raises_no_match(monkeypatch):
    """④ 无图商品 → NO_MATCH（明确「无图不可以图搜款」，不标题搜索）。"""
    class FakeBrowser:
        def __init__(self, *a, **k):
            pass

        def page(self):
            raise AssertionError("无图时不应打开页面")

    monkeypatch.setattr("sourcing.collectors.alibaba.SharedBrowser", FakeBrowser)
    col = AlibabaQuoteCollector(CollectorConfig())
    with pytest.raises(CollectorError) as exc:
        col.quote(_item())
    assert exc.value.error_code == "NO_MATCH"
    assert "以图搜款" in str(exc.value)


# ------------------------------------------------------------------ P-028 mock 基础设施
class FakeSingle:
    """单个元素（inner_text / is_visible / count / set_input_files）。"""

    def __init__(self, text="", visible=False):
        self._text = text
        self._visible = visible

    def inner_text(self, timeout=0):
        return self._text

    def is_visible(self, timeout=0):
        return self._visible

    def count(self):
        return 1

    def set_input_files(self, *a, **k):
        pass  # P-036 本地图上传回退：no-op mock


class FakeMulti:
    def __init__(self, items):
        self._items = items

    def count(self):
        return len(self._items)

    def all(self):
        return self._items

    @property
    def first(self):
        return self._items[0] if self._items else FakeSingle()

    def nth(self, i):
        return self._items[i]


class FakeRow:
    def __init__(self, renderkey, title, shop):
        self._rk, self._t, self._s = renderkey, title, shop

    def get_attribute(self, name):
        return {
            "data-renderkey": self._rk,
            "data-aplus-report": "",
        }.get(name, "")

    def locator(self, sel):
        if "titleText" in sel:
            return FakeMulti([FakeSingle(self._t)])
        if "shopName" in sel:
            return FakeMulti([FakeSingle(self._s)])
        return FakeMulti([])


class FakePage:
    def __init__(self, rows=None, prices=None, login_visible=False):
        self._rows = rows or []
        self._prices = prices or []
        self._login = login_visible
        self.goto_calls: list[str] = []

    def goto(self, *a, **k):
        self.goto_calls.append(a[0])
        self.url = a[0]

    def wait_for_timeout(self, ms):
        pass

    def close(self):
        pass

    def locator(self, sel):
        if "searchOfferItem" in sel:
            return FakeMulti(self._rows)
        if "login" in sel:
            return FakeMulti([FakeSingle(visible=self._login)])
        if "price-info" in sel:
            return FakeMulti([FakeSingle(p) for p in self._prices])
        return FakeMulti([])


class FakeBrowser:
    def __init__(self, page):
        self._page = page

    def page(self):
        return self._page


def _make_collector(page, monkeypatch) -> AlibabaQuoteCollector:
    monkeypatch.setattr(
        "sourcing.collectors.alibaba.SharedBrowser",
        lambda *a, **k: FakeBrowser(page),
    )
    return AlibabaQuoteCollector(CollectorConfig())


# ------------------------------------------------------------------ P-028 链路
def test_p028_build_search_url_encodes_image_address():
    """P-028：搜图直链构造（免上传，imageAddress 参数 URL 编码）。"""
    url = AlibabaQuoteCollector._build_search_url(
        "https://cbu01.alicdn.com/img/a b.jpg"
    )
    assert url.startswith(
        "https://air.1688.com/kapp/1688-search/pc-image-search/?imageAddress="
    )
    assert "a%20b.jpg" in url


def test_p028_offer_id_from_row():
    """P-028：data-renderkey/data-aplus-report 末段数字提取 offerId。"""
    class R:
        def __init__(self, rk, ap=""):
            self._rk, self._ap = rk, ap

        def get_attribute(self, name):
            return {"data-renderkey": self._rk, "data-aplus-report": self._ap}.get(name, "")

    assert AlibabaQuoteCollector._offer_id_from_row(
        R("1_0_normal_b2b-221674209657250c6e_1052811778069")
    ) == "1052811778069"
    assert AlibabaQuoteCollector._offer_id_from_row(
        R("", "serverTrackId@gul_x_1052811778069^final")
    ) == "1052811778069"
    assert AlibabaQuoteCollector._offer_id_from_row(R("no-id")) == ""


def test_p028_read_detail_price_min():
    """P-028：detail 页多档价格取最小；无价格返回 0。"""
    class P:
        def __init__(self, t):
            self._t = t

        def inner_text(self, timeout=0):
            return self._t

    class L:
        def __init__(self, items):
            self._items = items

        def count(self):
            return len(self._items)

        def nth(self, i):
            return self._items[i]

    class PG:
        def __init__(self, exact, fallback):
            self._e, self._f = L(exact), L(fallback)

        def locator(self, sel):
            # 精确选择器（detail_price）走 exact；其他（含宽泛回退）走 fallback
            if sel == ".price-info, .price-comp, .price-component":
                return self._e
            return self._f

    col = AlibabaQuoteCollector(CollectorConfig())
    assert col._read_detail_price(PG([P("新人价¥8.00起"), P("¥10.00")], [])) == 8.0
    # 精确选择器空 → 回退宽泛
    assert col._read_detail_price(PG([], [P("¥5.50")])) == 5.5
    assert col._read_detail_price(PG([], [])) == 0.0


def test_quote_success_flow(monkeypatch):
    """P-028：完整询价流程——搜图页卡片 → detail 直链 → 读最低价 → Quote。"""
    rows = [
        FakeRow("1_0_normal_b2b-xxx_1052811778069", "玫瑰洗衣液", "米诺蒂儿公司"),
        FakeRow("1_1_normal_b2b-yyy_9998887776665", "另一款", "某工厂"),
    ]
    page = FakePage(rows=rows, prices=["新人价¥8.00起", "¥10.00"])
    col = _make_collector(page, monkeypatch)

    quotes = col.quote(_item(image_urls=["https://img.example.com/a.jpg"]))
    assert len(quotes) == 2
    q0 = quotes[0]
    assert q0.supplier_name == "米诺蒂儿公司"
    assert q0.unit_cost == 8.0
    assert q0.raw_url == "https://detail.1688.com/offer/1052811778069.html"
    assert q0.sku_name == "玫瑰洗衣液"
    # 首次导航 = 搜图直链；后续 = detail 页
    assert "air.1688.com" in page.goto_calls[0]
    assert "detail.1688.com/offer/9998887776665.html" in page.goto_calls[-1]


def test_quote_no_results_raises_page_changed(monkeypatch):
    """P-028/P-036：搜图结果未渲染 → 本地图上传回退 → 仍失败 → PAGE_CHANGED。"""
    from pathlib import Path

    page = FakePage(rows=[])
    col = _make_collector(page, monkeypatch)
    monkeypatch.setattr(col, "_wait_results", lambda page, timeout_ms=20000: False)
    monkeypatch.setattr(col, "_download_image", lambda url: Path("/tmp/fake.jpg"))
    with pytest.raises(CollectorError) as exc:
        col.quote(_item(image_urls=["https://img.example.com/a.jpg"]))
    assert exc.value.error_code == "PAGE_CHANGED"


def test_quote_fallback_to_local_upload(monkeypatch):
    """P-036：直链搜图无结果 → 下载本地图 → 首页上传 → 搜图成功返回报价。"""
    from pathlib import Path
    from sourcing.collectors.alibaba import AlibabaQuoteCollector as AC

    # 第一次 _wait_results False（直链失败），第二次 True（本地图上传成功）
    class FlipPage(FakePage):
        def __init__(self):
            super().__init__(rows=[], prices=["新人价¥8.00起"])
            self._waits = 0

    page = FlipPage()
    col = _make_collector(page, monkeypatch)

    def flaky_wait(page, timeout_ms=20000):
        page._waits += 1
        return page._waits >= 2  # 第二次 True

    monkeypatch.setattr(col, "_wait_results", flaky_wait)
    monkeypatch.setattr(
        col, "_download_image",
        lambda url: Path("/tmp/fake_upload.jpg"),
    )
    # rows 由第二次 wait 后返回——用 monkeypatch 让 locator 在第二次后返回卡片
    orig = page.locator

    def loc(sel):
        if "[class*='searchOfferItem']" in sel:
            # 卡片数据（offerId 从 renderkey 提取）
            if page._waits >= 2:
                return FakeMulti([FakeRow("1_0_normal_b2b-x_1052811778069", "玫瑰洗衣液", "米诺蒂儿公司")])
            return FakeMulti([])
        return orig(sel)

    page.locator = loc
    quotes = col.quote(_item(image_urls=["https://img.example.com/a.jpg"]))
    assert len(quotes) == 1
    assert quotes[0].raw_url == "https://detail.1688.com/offer/1052811778069.html"


def test_quote_login_gate_raises_auth_required(monkeypatch):
    """P-028：搜图页出现登录浮层 → AUTH_REQUIRED（转人工登录，不硬闯）。"""
    page = FakePage(rows=[FakeRow("1_0_normal_b2b-x_1052811778069", "t", "s")],
                    login_visible=True)
    col = _make_collector(page, monkeypatch)
    monkeypatch.setattr(col, "_wait_results", lambda page, timeout_ms=30000: True)
    with pytest.raises(CollectorError) as exc:
        col.quote(_item(image_urls=["https://img.example.com/a.jpg"]))
    assert exc.value.error_code == "AUTH_REQUIRED"
