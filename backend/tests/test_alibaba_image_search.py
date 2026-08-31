"""P-027：1688 以图搜款唯一化测试（废弃标题搜索）。"""

import pytest

from sourcing.collectors.alibaba import AlibabaQuoteCollector
from sourcing.collectors.base import CollectorError
from sourcing.models import SourceItem


def _item(image_urls=None, raw=None):
    return SourceItem(
        source="fixtures", board="b", platform_item_id="x",
        title="测试商品 水杯泡腾片", category="日用",
        image_urls=image_urls or [], raw=raw or {},
    )


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
    from sourcing.config import CollectorConfig
    from sourcing.collectors.browser import SharedBrowser

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
