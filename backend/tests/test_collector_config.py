"""S3b 选择器校准动作实施测试（A1/A2/A3/A4，零浏览器零登录态）。

- A1 config.selectors 迁移：5 来源 config.selectors 与采集器 DEFAULT_SELECTORS 一致；
  合并逻辑 {**DEFAULT_SELECTORS, **config.selectors} 行为零变化；config 覆盖优先。
  （youmi/doudian 刻意不含 columns → A4 动态列定位天然启用）
- A2 有米云 URL 日期动态化：{start_date}/{end_date} 占位符替换（YYYY-MM-DD，
  end=当天、start=当天-lookback_days）；无占位符模板原样；lookback 边界。
- A3 抖店飙升榜 fixtures：doudian.json「飙升榜」样本可被 FixtureCollector 回放。
- A4 动态列定位：config.selectors.columns 为空时 _locate_columns 走动态表头定位
  （mock 表头页），配置了 columns 时用配置值（保持现状）。
"""

import re
from datetime import date
from pathlib import Path

import pytest

from sourcing.collectors.alibaba import DEFAULT_SELECTORS as ALIBABA_DEFAULTS
from sourcing.collectors.base import CollectorError
from sourcing.collectors.doudian import DEFAULT_SELECTORS as DOUDIAN_DEFAULTS
from sourcing.collectors.doudian import DoudianCollector
from sourcing.collectors.fixtures import FixtureCollector
from sourcing.collectors.opportunities import DEFAULT_SELECTORS as OPPORTUNITY_DEFAULTS
from sourcing.collectors.taobao import DEFAULT_SELECTORS as TAOBAO_DEFAULTS
from sourcing.collectors.youmi import DEFAULT_SELECTORS as YOUMI_DEFAULTS
from sourcing.collectors.youmi import YoumiCollector, render_board_url
from sourcing.config import load_config

BACKEND = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- A1
# config.selectors 迁移（R-23 落地）


def test_a1_selectors_migrated_into_config_all_sources():
    """5 来源 config.selectors 与采集器 DEFAULT_SELECTORS 逐键一致（youmi/doudian 除 columns）。"""
    cfg = load_config()
    assert cfg.opportunities.selectors == OPPORTUNITY_DEFAULTS
    assert cfg.alibaba.selectors == ALIBABA_DEFAULTS
    assert cfg.taobao.selectors == TAOBAO_DEFAULTS
    # youmi/doudian：除 columns 外逐键一致（columns 留给 A4 动态定位）
    assert cfg.youmi.selectors == {k: v for k, v in YOUMI_DEFAULTS.items() if k != "columns"}
    assert cfg.doudian.selectors == {k: v for k, v in DOUDIAN_DEFAULTS.items() if k != "columns"}


def test_a1_columns_not_migrated_for_youmi_doudian():
    """A4 前提：youmi/doudian 的 config.selectors 不含 columns → 动态列定位天然启用。"""
    cfg = load_config()
    assert "columns" not in cfg.youmi.selectors
    assert "columns" not in cfg.doudian.selectors
    # opportunities 的 columns 允许结构化 int 值（dict[str, Any] 承载）
    cols = cfg.opportunities.selectors["columns"]
    assert cols == {"title": 0, "source": 1, "status": 2}
    assert all(isinstance(v, int) for v in cols.values())


def test_a1_merged_selectors_unchanged_with_default_config():
    """config 与默认同值 → 合并结果与纯 DEFAULT_SELECTORS 完全一致（行为零变化）。"""
    cfg = load_config()
    assert YoumiCollector(cfg.youmi).selectors == YOUMI_DEFAULTS
    assert DoudianCollector(cfg.doudian).selectors == DOUDIAN_DEFAULTS
    # 其余来源同样验证合并结果 = 默认
    from sourcing.collectors.alibaba import AlibabaQuoteCollector
    from sourcing.collectors.opportunities import OpportunitiesCollector
    from sourcing.collectors.taobao import TaobaoReferenceCollector

    assert OpportunitiesCollector(cfg.opportunities).selectors == OPPORTUNITY_DEFAULTS
    assert AlibabaQuoteCollector(cfg.alibaba).selectors == ALIBABA_DEFAULTS
    assert TaobaoReferenceCollector(cfg.taobao).selectors == TAOBAO_DEFAULTS


def test_a1_config_selector_override_wins():
    """config.selectors 覆盖键生效（改配置即可改选择器），未覆盖键保持默认。"""
    cfg = load_config(
        youmi={"selectors": {"row": ".custom-row"}},
        doudian={"selectors": {"next_page": ".custom-next"}},
    )
    col = YoumiCollector(cfg.youmi)
    assert col.selectors["row"] == ".custom-row"
    assert col.selectors["login_gate"] == YOUMI_DEFAULTS["login_gate"]  # 未覆盖键回默认
    col2 = DoudianCollector(cfg.doudian)
    assert col2.selectors["next_page"] == ".custom-next"
    assert col2.selectors["row"] == DOUDIAN_DEFAULTS["row"]


# --------------------------------------------------------------------------- A2
# 有米云 URL 日期动态化


def test_a2_render_board_url_placeholders():
    """{start_date}/{end_date} 替换为 YYYY-MM-DD：end=当天、start=当天-lookback_days。"""
    url = render_board_url(
        "https://console.youshu.youcloud.com/goods/sale?site_id=10502"
        "&startDate={start_date}&endDate={end_date}",
        lookback_days=7,
        today=date(2026, 8, 28),
    )
    assert url.endswith("&startDate=2026-08-21&endDate=2026-08-28")
    assert "2026-08-21" in url and "2026-08-28" in url


def test_a2_render_board_url_no_placeholders():
    """无占位符模板原样返回（兼容其他来源/旧模板）。"""
    tpl = "https://compass.jinritemai.com/shop/chance/rank-product"
    assert render_board_url(tpl, lookback_days=7, today=date(2026, 8, 28)) == tpl


def test_a2_render_board_url_lookback_boundaries():
    """lookback 边界：0 → start==end；1 → start=end-1；大回看正常。"""
    today = date(2026, 8, 28)
    tpl = "?a={start_date}&b={end_date}"
    assert render_board_url(tpl, lookback_days=0, today=today) == "?a=2026-08-28&b=2026-08-28"
    assert render_board_url(tpl, lookback_days=1, today=today) == "?a=2026-08-27&b=2026-08-28"
    assert render_board_url(tpl, lookback_days=30, today=today) == "?a=2026-07-29&b=2026-08-28"


def test_a2_config_url_template_has_placeholders():
    """config 里 youmi url_template 已占位符化，不再含硬编码日期。"""
    cfg = load_config()
    tpl = cfg.youmi.boards[0].url_template
    assert "{start_date}" in tpl and "{end_date}" in tpl
    assert "2026-08-22" not in tpl and "2026-08-28" not in tpl


def test_a2_config_lookback_default_and_override():
    """lookback_days 默认 7，可通过配置覆盖。"""
    cfg = load_config()
    assert cfg.youmi.lookback_days == 7
    assert cfg.doudian.lookback_days == 7  # CollectorConfig 级字段，各来源默认一致
    cfg2 = load_config(youmi={"lookback_days": 3})
    assert cfg2.youmi.lookback_days == 3


def test_a2_collector_goto_rendered_date():
    """采集器导航时用动态日期替换占位符（fake browser/page 记录 goto URL）。"""
    cfg = load_config()
    col = YoumiCollector(cfg.youmi)

    class FakePage:
        def __init__(self):
            self.goto_url = None

        def goto(self, url, **kwargs):
            self.goto_url = url

        def wait_for_timeout(self, ms):
            pass

        def close(self):
            pass

    class FakeBrowser:
        def __init__(self, page):
            self._page = page

        def page(self):
            return self._page

    fake = FakePage()
    col.browser = FakeBrowser(fake)
    col._collect_from_page = lambda page, board, limit: []  # 不触碰页面解析逻辑
    col.collect_board("商品榜", limit=10)

    assert fake.goto_url is not None
    m = re.search(r"startDate=(\d{4}-\d{2}-\d{2})&endDate=(\d{4}-\d{2}-\d{2})", fake.goto_url)
    assert m, fake.goto_url
    start, end = m.group(1), m.group(2)
    assert start < end  # 默认 7 天回看：start 早于 end
    # 动态日期 = 今天与今天-7（lookback_days 默认），不再硬编码固定日期
    from datetime import date, timedelta

    today = date.today()
    assert end == today.isoformat()
    assert start == (today - timedelta(days=7)).isoformat()


# --------------------------------------------------------------------------- A3
# 抖店飙升榜 fixtures 样本


def test_a3_doudian_fixtures_soaring_board():
    """fixtures 采集器 collect_board("飙升榜") 返回 3 条样本，字段与商品榜同构。"""
    from sourcing.config import SourcingConfig

    cfg = SourcingConfig(
        db_url="sqlite:///:memory:",
        fixtures_dir=BACKEND / "fixtures",
    )
    col = FixtureCollector("doudian", cfg)
    assert col.default_boards == ["商品榜", "飙升榜"]

    items = col.collect_board("飙升榜")
    assert len(items) == 3
    for i, it in enumerate(items, start=1):
        assert it.source == "doudian"
        assert it.board == "飙升榜"
        assert it.platform_item_id.startswith("dd-10")
        assert it.title
        assert it.price > 0
        assert it.sales > 0
        assert it.rank == i
        assert it.category
        assert it.image_urls and it.image_urls[0].startswith("https://")


def test_a3_doudian_fixtures_product_board_unchanged():
    """既有「商品榜」fixtures 不受影响（回归保护）。"""
    from sourcing.config import SourcingConfig

    cfg = SourcingConfig(db_url="sqlite:///:memory:", fixtures_dir=BACKEND / "fixtures")
    items = FixtureCollector("doudian", cfg).collect_board("商品榜")
    assert len(items) >= 5
    assert all(it.rank >= 1 for it in items)


# --------------------------------------------------------------------------- A4
# 动态列定位启用（youmi / doudian）


class FakeHeaderLocator:
    """模拟 Playwright Locator：all_text_contents 返回表头文本列表。"""

    def __init__(self, headers):
        self._headers = headers

    def all_text_contents(self):
        return list(self._headers)


class FakeHeaderPage:
    """模拟 Playwright Page：locator(任意选择器) 都返回同一份表头。"""

    def __init__(self, headers):
        self._headers = headers

    def locator(self, sel):
        return FakeHeaderLocator(self._headers)


def test_a4_youmi_dynamic_columns_when_config_empty():
    """youmi：config 无 columns → 按表头文本动态定位列索引。"""
    cfg = load_config()  # 默认 youmi.selectors 无 columns
    col = YoumiCollector(cfg.youmi)
    page = FakeHeaderPage(["#", "商品", "推广方式", "店铺", "价格（元）", "新增销量", "累计销量"])
    assert col._locate_columns(page) == {"rank": 0, "title": 1, "price": 4, "sales": 5}


def test_a4_youmi_dynamic_missing_title_raises():
    """youmi：表头无「商品」列 → PAGE_CHANGED 错误（动态定位兜底语义）。"""
    cfg = load_config()
    col = YoumiCollector(cfg.youmi)
    page = FakeHeaderPage(["#", "店铺", "价格（元）"])
    with pytest.raises(CollectorError) as ei:
        col._locate_columns(page)
    assert ei.value.error_code == "PAGE_CHANGED"


def test_a4_youmi_config_columns_override():
    """youmi：config 显式配置 columns → 直接使用配置值，不触碰页面。"""
    cfg = load_config(youmi={"selectors": {"columns": {"rank": 0, "title": 2, "price": 4, "sales": 6}}})
    col = YoumiCollector(cfg.youmi)
    assert col._locate_columns(object()) == {"rank": 0, "title": 2, "price": 4, "sales": 6}


def test_a4_doudian_dynamic_columns_when_config_empty():
    """doudian：config 无 columns → 按表头文本动态定位（含 shop/pay/sales）。"""
    cfg = load_config()  # 默认 doudian.selectors 无 columns
    col = DoudianCollector(cfg.doudian)
    page = FakeHeaderPage(["排名", "商品", "店铺", "支付金额", "点击", "成交件数", "转化率"])
    assert col._locate_columns(page) == {
        "rank": 0, "title": 1, "shop": 2, "pay": 3, "sales": 5,
    }


def test_a4_doudian_config_columns_override():
    """doudian：config 显式配置 columns → 配置值 + pay 兜底 3。"""
    cfg = load_config(doudian={"selectors": {"columns": {"title": 1, "sales": 5}}})
    col = DoudianCollector(cfg.doudian)
    assert col._locate_columns(object()) == {"title": 1, "sales": 5, "pay": 3}
