"""zombie_clean 僵尸标签页清理单测（P-016 防复发，v1.1-③）。

**纯 mock**：monkeypatch ``sourcing.zombie_clean._http_get_json/_http_close`` 为
FakeCDP 层，**绝不真实连接 9223/9555**（避免动真实浏览器）。

覆盖：
- 列表解析与统计字段（targets_seen/pages_seen/kept/closed/skipped）；
- 保留规则：保留采集目标页（opprotunity/rank-product、有米云 console.youshu.youcloud.com）、
  关闭僵尸页、跳过 404 关闭失败、跳过 browser_ui/devtools/chrome:// about:blank 等；
- 幂等：空列表无副作用；重复清理结果一致；
- 防御：保留集为空（找不到任何采集目标页）→ 不关闭任何页面（safe_aborted）；
- 失败容错：/json/list 连接失败/非数组 → 返回统计不抛；单个关闭失败只计数。
"""

import urllib.error

import pytest

import sourcing.zombie_clean as zc


# --------------------------------------------------------------------------- fixtures
# 模拟 CDP target 对象（/json/list 元素）：{id, type, url, title}

PAGE_OPPORTUNITY = {"id": "t-opp", "type": "page", "url": "https://store.weixin.qq.com/shop/goods/opprotunity", "title": "机会品"}
PAGE_RANK = {"id": "t-rank", "type": "page", "url": "https://compass.jinritemai.com/shop/chance/rank-product", "title": "商品榜"}
PAGE_HOME = {"id": "t-home", "type": "page", "url": "https://store.weixin.qq.com/shop/home", "title": "商机中心 home"}
PAGE_CORE = {"id": "t-core", "type": "page", "url": "https://compass.jinritemai.com/shop", "title": "罗盘核心数据页"}
PAGE_YOUMI = {"id": "t-youmi", "type": "page", "url": "https://console.youshu.youcloud.com/goods/sale?site_id=10502&startDate=2026-08-21&endDate=2026-08-28", "title": "有米云商品榜"}
PAGE_BLANK = {"id": "t-blank", "type": "page", "url": "about:blank", "title": ""}
PAGE_NEWTAB = {"id": "t-newtab", "type": "page", "url": "chrome://newtab/", "title": "新标签页"}
PAGE_NO_URL = {"id": "t-nourl", "type": "page", "url": None, "title": ""}
UI_OMNIBOX = {"id": "t-ui", "type": "browser_ui", "url": "chrome://omnibox-popup/", "title": ""}
UI_DEVTOOLS = {"id": "t-devtools", "type": "devtools", "url": "devtools://devtools/bundled/devtools_app.html", "title": "DevTools"}


class FakeCDP:
    """模拟 CDP HTTP 层：/json/list 返回给定 targets；/json/close 按 target id 给结果。

    close_behavior: {target_id: "ok" | "404" | "error"}，缺省 "ok"。
    """

    def __init__(self, targets, list_error=None, close_behavior=None):
        self.targets = list(targets)
        self.list_error = list_error
        self.close_behavior = close_behavior or {}
        self.close_calls = []  # 记录被请求关闭的 target id（按调用顺序）

    def get_json(self, url, timeout):
        if self.list_error is not None:
            raise self.list_error
        return self.targets

    def close(self, url, timeout):
        tid = url.rsplit("/", 1)[-1]
        self.close_calls.append(tid)
        mode = self.close_behavior.get(tid, "ok")
        if mode == "ok":
            return
        if mode == "404":
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        raise urllib.error.URLError(f"close failed: {tid}")


def _clean(monkeypatch, fake, **kwargs):
    """装配 fake HTTP 层并调用 clean_zombie_targets（monkeypatch 后自动还原）。"""
    monkeypatch.setattr(zc, "_http_get_json", fake.get_json)
    monkeypatch.setattr(zc, "_http_close", fake.close)
    return zc.clean_zombie_targets(**kwargs)


# --------------------------------------------------------------------------- 列表解析 + 保留规则


def test_list_parsing_and_keep_rules(monkeypatch):
    """混合列表：保留目标页、关闭僵尸页、跳过非页面与非 http(s)（含 404 目标类型）。"""
    fake = FakeCDP(
        [
            PAGE_OPPORTUNITY,
            PAGE_RANK,
            PAGE_HOME,
            PAGE_CORE,
            UI_OMNIBOX,     # browser_ui → 跳过不报错
            UI_DEVTOOLS,    # devtools → 跳过不报错
            PAGE_NEWTAB,    # chrome:// → 非 http(s)，跳过
            PAGE_BLANK,     # about:blank → 非 http(s)，跳过
            PAGE_NO_URL,    # 无 url → 跳过
        ]
    )
    stats = _clean(monkeypatch, fake, port=9223)
    assert stats["ok"] is True
    assert stats["port"] == 9223
    assert stats["targets_seen"] == 9
    assert stats["pages_seen"] == 7  # opp/rank/home/core/newtab/blank/nourl
    assert stats["kept"] == 2        # opprotunity + rank-product
    assert stats["closed"] == 2      # home + core（僵尸页）
    assert stats["close_failed"] == 0
    assert stats["skipped"] == 5     # ui + devtools + newtab + blank + nourl
    assert stats["safe_aborted"] is False
    assert sorted(stats["closed_ids"]) == ["t-core", "t-home"]
    assert sorted(fake.close_calls) == ["t-core", "t-home"]


def test_close_404_counted_not_fatal(monkeypatch):
    """/json/close 返回 404（如 browser_ui 类 target）→ close_failed 计数，不抛。"""
    fake = FakeCDP([PAGE_OPPORTUNITY, PAGE_HOME], close_behavior={"t-home": "404"})
    stats = _clean(monkeypatch, fake, port=9223)
    assert stats["ok"] is True
    assert stats["kept"] == 1
    assert stats["closed"] == 0
    assert stats["close_failed"] == 1
    assert any("404" in e for e in stats["errors"])
    assert fake.close_calls == ["t-home"]


def test_close_network_error_tolerated(monkeypatch):
    """单个关闭网络失败只计数，其余僵尸页照常关闭。"""
    fake = FakeCDP(
        [PAGE_OPPORTUNITY, PAGE_HOME, PAGE_CORE],
        close_behavior={"t-home": "error"},
    )
    stats = _clean(monkeypatch, fake, port=9223)
    assert stats["ok"] is True
    assert stats["closed"] == 1          # t-core 关闭成功
    assert stats["close_failed"] == 1    # t-home 网络错误
    assert stats["errors"] and "t-home" in stats["errors"][0]
    assert stats["closed_ids"] == ["t-core"]


# --------------------------------------------------------------------------- 幂等


def test_empty_list_idempotent(monkeypatch):
    """空列表：无任何关闭副作用，重复执行结果一致。"""
    fake = FakeCDP([])
    stats = _clean(monkeypatch, fake, port=9223)
    assert stats["ok"] is True
    assert stats["targets_seen"] == 0
    assert stats["pages_seen"] == 0
    assert stats["kept"] == 0
    assert stats["closed"] == 0
    assert fake.close_calls == []
    assert stats["safe_aborted"] is True  # 保留集为空 → 防御性未关闭任何页

    # 幂等：再次执行结果一致
    fake2 = FakeCDP([])
    stats2 = _clean(monkeypatch, fake2, port=9223)
    assert stats2 == stats


# --------------------------------------------------------------------------- 防御：保留集为空不动任何页


def test_defensive_abort_when_no_kept_pages(monkeypatch):
    """只有僵尸页、无任何采集目标页 → 保留集为空，不关闭任何页面。"""
    fake = FakeCDP([PAGE_HOME, PAGE_CORE])
    stats = _clean(monkeypatch, fake, port=9223)
    assert stats["kept"] == 0
    assert stats["safe_aborted"] is True
    assert stats["closed"] == 0
    assert fake.close_calls == []


def test_explicit_empty_keep_aborts(monkeypatch):
    """调用方显式传空保留集 → 同样防御性中止（绝不关闭页面）。"""
    fake = FakeCDP([PAGE_HOME])
    stats = _clean(monkeypatch, fake, port=9223, keep_url_fragments=[])
    assert stats["safe_aborted"] is True
    assert stats["closed"] == 0
    assert fake.close_calls == []


# --------------------------------------------------------------------------- 失败容错


def test_fetch_failure_returns_stats_no_raise(monkeypatch):
    """/json/list 连接失败（浏览器未启动）→ 返回统计 dict 不抛异常。"""
    fake = FakeCDP([], list_error=urllib.error.URLError("Connection refused: 127.0.0.1:9223"))
    stats = _clean(monkeypatch, fake, port=9223)
    assert stats["ok"] is False
    assert stats["error"]
    assert stats["closed"] == 0
    assert fake.close_calls == []


def test_list_not_array_tolerated(monkeypatch):
    """/json/list 返回非数组 → 返回统计不抛（error 说明原因）。"""

    class FakeNotArray(FakeCDP):
        def get_json(self, url, timeout):
            return {"not": "a list"}

    fake = FakeNotArray([])
    stats = _clean(monkeypatch, fake, port=9223)
    assert stats["ok"] is False
    assert "非数组" in stats["error"]
    assert stats["closed"] == 0


# --------------------------------------------------------------------------- 保留片段（默认/自定义/大小写）


def test_default_keep_fragments_by_port():
    """默认保留片段按端口：9223→opprotunity/rank-product；9555→有米云。"""
    assert zc.default_keep_fragments(9223) == ["opprotunity", "rank-product"]
    assert zc.default_keep_fragments(9555) == ["console.youshu.youcloud.com"]
    assert zc.default_keep_fragments(9999) == ["opprotunity", "rank-product"]  # 兜底


def test_youmi_port_keeps_youcloud_page(monkeypatch):
    """9555 有米云：默认保留 console.youshu.youcloud.com，其余 http(s) 页关闭。"""
    junk = {"id": "t-junk", "type": "page", "url": "https://example.com/", "title": "junk"}
    fake = FakeCDP([PAGE_YOUMI, junk])
    stats = _clean(monkeypatch, fake, port=9555)
    assert stats["kept"] == 1
    assert stats["closed"] == 1
    assert fake.close_calls == ["t-junk"]


def test_custom_keep_fragments_case_insensitive(monkeypatch):
    """自定义保留片段 + 大小写不敏感子串匹配。"""
    upper = {"id": "t-upper", "type": "page", "url": "https://CONSOLE.YOUSHU.YOUCLOUD.COM/GOODS", "title": ""}
    fake = FakeCDP([upper, PAGE_HOME])
    stats = _clean(monkeypatch, fake, port=9223, keep_url_fragments=["console.youshu.youcloud.com"])
    assert stats["kept"] == 1
    assert stats["closed"] == 1
    assert fake.close_calls == ["t-home"]


# --------------------------------------------------------------------------- 统计契约


def test_stats_keys_stable(monkeypatch):
    """统计 dict 键稳定（调用方/报告依赖）。"""
    fake = FakeCDP([PAGE_OPPORTUNITY])
    stats = _clean(monkeypatch, fake, port=9223)
    for key in (
        "ok", "port", "targets_seen", "pages_seen", "kept", "closed",
        "close_failed", "skipped", "safe_aborted", "closed_ids", "errors", "error",
    ):
        assert key in stats
