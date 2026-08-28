"""视频号采集器单元测试（fixtures 离线全链路 + signer 接口 + 错误分类，R-M2-17）。

覆盖（任务书验收）：
  ① fixtures 模式 list_hot_videos 解析：字段完整（source_platform="视频号"）/ 热度降序 / limit
  ② signer 接口：MockSignatureProvider 注入后 resolve_direct_url 结果包含注入签名；
     sign() 返回 {"headers", "query"} 结构
  ③ RealSignatureProvider 未实现：sign() 抛 NotImplementedError（清晰报错，不留假算法）；
     resolve 注入未实现签名器 → PLATFORM_REJECT（R-M2-03 签名失效分类）
  ④ resolve_direct_url fixtures 直链：命中返回样本直链；未知 video_id → NO_MATCH
  ⑤ 错误分类（fixtures 注入异常数据）：空列表→NO_MATCH、文件缺失→UNEXPECTED、空 video_id→NO_MATCH
  ⑥ login_state：fixtures 模式与 auto 模式（注入失败探测）无浏览器均返回 logged_in=False 不抛
  ⑦ auto 模式错误分类（fake page 注入，零浏览器）：登录门→AUTH_REQUIRED、
     页面结构变化→PLATFORM_REJECT、无有效条目→NO_MATCH、连接超时→TIMEOUT、
     正常解析出条目、直链解析空→PLATFORM_REJECT

纪律：pytest 必须带独立 basetemp `--basetemp=".pytest-tmp-m2"`（宪法第 12 节 / P-011）；
全程零真实浏览器、零登录态、零外网（R-M2-17）；只操作 fixtures/materials 样本与本包代码。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from materials.collectors.signer import MockSignatureProvider, RealSignatureProvider
from materials.collectors.wechat_video import (
    WechatVideoCollector,
    WechatVideoError,
)
from materials.config import WechatVideoConfig
from materials.downloader import (
    AUTH_REQUIRED,
    NO_MATCH,
    PLATFORM_REJECT,
    TIMEOUT,
    UNEXPECTED,
)

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND / "fixtures" / "materials"


def make_collector(
    fixtures_mode: bool = True,
    fixtures_dir: Path | None = None,
    **collector_kwargs,
) -> WechatVideoCollector:
    cfg = WechatVideoConfig(fixtures_mode=fixtures_mode)
    return WechatVideoCollector(cfg, fixtures_dir=fixtures_dir or FIXTURES_DIR, **collector_kwargs)


# ===========================================================================
# ① fixtures 模式 list_hot_videos：字段完整 / 热度排序 / limit
# ===========================================================================
class TestFixturesListHotVideos:
    def test_fields_complete(self):
        items = make_collector().list_hot_videos(limit=10)
        assert len(items) >= 5
        for it in items:
            assert it["source_platform"] == "视频号"
            assert it["source_url"]
            assert it["source_author"]
            assert it["title"]
            assert it["video_id"]
            assert isinstance(it["heat_score"], float)

    def test_heat_sorted_desc(self):
        items = make_collector().list_hot_videos(limit=10)
        heats = [it["heat_score"] for it in items]
        assert heats == sorted(heats, reverse=True)

    def test_limit(self):
        assert len(make_collector().list_hot_videos(limit=3)) == 3
        assert len(make_collector().list_hot_videos(limit=0)) == 6  # limit=0 表示不限

    def test_video_id_stable(self):
        items = make_collector().list_hot_videos(limit=10)
        assert items[0]["video_id"] == "wxv_fixture_1001"


# ===========================================================================
# ②/③ signer 接口：Mock 注入生效；Real 未实现清晰报错（验收标准第 3 条）
# ===========================================================================
class TestSigner:
    def test_mock_sign_returns_headers_and_query(self):
        signer = MockSignatureProvider(
            fixed_query={"sign": "MOCK_SIGN"}, fixed_headers={"X-Mock": "1"}
        )
        signed = signer.sign({"video_id": "x"}, "http://u")
        assert signed == {"headers": {"X-Mock": "1"}, "query": {"sign": "MOCK_SIGN"}}

    def test_mock_injection_visible_in_direct_url(self):
        collector = make_collector()
        signer = MockSignatureProvider(fixed_query={"sign": "MOCK_SIGN"}, fixed_headers={"X-Mock": "1"})
        url = collector.resolve_direct_url("wxv_fixture_1001", signer=signer)
        assert url.startswith("https://fixtures.local/materials/videos/wxv_fixture_1001.mp4")
        assert "sign=MOCK_SIGN" in url

    def test_mock_empty_injection_keeps_url(self):
        collector = make_collector()
        signer = MockSignatureProvider()
        url = collector.resolve_direct_url("wxv_fixture_1001", signer=signer)
        assert url == "https://fixtures.local/materials/videos/wxv_fixture_1001.mp4"

    def test_real_signer_not_implemented(self):
        real = RealSignatureProvider(config={"version": "uncalibrated"})
        with pytest.raises(NotImplementedError):
            real.sign({"video_id": "x"}, "http://u")

    def test_real_signer_in_resolve_maps_to_platform_reject(self):
        # R-M2-03：签名器未实现 → 签名失效分类 PLATFORM_REJECT（不留假算法）
        collector = make_collector()
        real = RealSignatureProvider()
        with pytest.raises(WechatVideoError) as ei:
            collector.resolve_direct_url("wxv_fixture_1001", signer=real)
        assert ei.value.error_code == PLATFORM_REJECT


# ===========================================================================
# ④ resolve_direct_url fixtures 直链
# ===========================================================================
class TestResolveDirectUrlFixtures:
    def test_hit_returns_fixture_direct_url(self):
        collector = make_collector()
        url = collector.resolve_direct_url("wxv_fixture_1001")
        assert url == "https://fixtures.local/materials/videos/wxv_fixture_1001.mp4"

    def test_unknown_video_id_no_match(self):
        collector = make_collector()
        with pytest.raises(WechatVideoError) as ei:
            collector.resolve_direct_url("wxv_does_not_exist")
        assert ei.value.error_code == NO_MATCH

    def test_empty_video_id_no_match(self):
        collector = make_collector()
        with pytest.raises(WechatVideoError) as ei:
            collector.resolve_direct_url("")
        assert ei.value.error_code == NO_MATCH


# ===========================================================================
# ⑤ 错误分类（fixtures 注入异常数据各分支）
# ===========================================================================
class TestErrorClassificationFixtures:
    def test_empty_items_no_match(self, tmp_path):
        d = tmp_path / "materials"
        d.mkdir(parents=True)
        (d / "wechat_video_hot.json").write_text(
            '{"board": "热门", "items": []}', encoding="utf-8"
        )
        collector = make_collector(fixtures_dir=d)
        with pytest.raises(WechatVideoError) as ei:
            collector.list_hot_videos()
        assert ei.value.error_code == NO_MATCH

    def test_missing_fixture_file_unexpected(self, tmp_path):
        collector = make_collector(fixtures_dir=tmp_path)  # 目录内无样本文件
        with pytest.raises(WechatVideoError) as ei:
            collector.list_hot_videos()
        assert ei.value.error_code == UNEXPECTED

    def test_all_items_invalid_no_match(self, tmp_path):
        d = tmp_path / "materials"
        d.mkdir(parents=True)
        (d / "wechat_video_hot.json").write_text(
            '{"items": [{"video_id": "", "title": ""}]}', encoding="utf-8"
        )
        collector = make_collector(fixtures_dir=d)
        with pytest.raises(WechatVideoError) as ei:
            collector.list_hot_videos()
        assert ei.value.error_code == NO_MATCH


# ===========================================================================
# ⑥ login_state：无浏览器返回 False 不抛
# ===========================================================================
class TestLoginState:
    def test_fixtures_mode_no_browser_no_raise(self):
        st = make_collector().login_state()
        assert st["logged_in"] is False
        assert "error" in st

    def test_auto_mode_probe_failure_returns_false_no_raise(self):
        def bad_probe():
            raise RuntimeError("connection refused")

        collector = make_collector(fixtures_mode=False, probe=bad_probe)
        st = collector.login_state()
        assert st["logged_in"] is False
        assert st["error"]

    def test_auto_mode_probe_false_returns_false(self):
        collector = make_collector(fixtures_mode=False, probe=lambda: False)
        st = collector.login_state()
        assert st["logged_in"] is False

    def test_auto_mode_probe_ok_returns_true(self):
        collector = make_collector(fixtures_mode=False, probe=lambda: True)
        st = collector.login_state()
        assert st["logged_in"] is True
        assert st["error"] is None


# ===========================================================================
# ⑦ auto 模式错误分类（fake page 注入，零真实浏览器）
# ===========================================================================
class _FakeEl:
    def __init__(self, text: str = "", href: str = ""):
        self._text = text
        self._href = href

    def inner_text(self, timeout=None):  # noqa: ARG002 - playwright 兼容签名
        return self._text

    def get_attribute(self, name: str):
        return self._href if name == "href" else None

    def is_visible(self):
        return True


class _FakeLocator:
    def __init__(self, els: list):
        self._els = els

    @property
    def first(self):
        return self._els[0] if self._els else _FakeEl()

    def count(self):
        return len(self._els)

    def all(self):
        return list(self._els)


class _FakeRow:
    """fake 行：title/author/heat/href 按选择器关键字返回对应文本。"""

    def __init__(self, title: str = "", author: str = "", heat: str = "", href: str = ""):
        self.title = title
        self.author = author
        self.heat = heat
        self.href = href

    def locator(self, selector: str):
        if "title" in selector:
            return _FakeLocator([_FakeEl(self.title)])
        if "author" in selector:
            return _FakeLocator([_FakeEl(self.author)])
        if "like" in selector:
            return _FakeLocator([_FakeEl(self.heat)])
        if "video" in selector or "sph" in selector:
            return _FakeLocator([_FakeEl("", self.href)])
        return _FakeLocator([])


class _FakePage:
    def __init__(self, rows: list | None = None, login: bool = False, js_result: str = "", open_error: Exception | None = None):
        self._rows = rows or []
        self._login = login
        self._js_result = js_result
        self.open_error = open_error
        self.closed = False

    def locator(self, selector: str):
        if "login" in selector or "qrcode" in selector or "captcha" in selector or "verify" in selector:
            return _FakeLocator([_FakeEl()] if self._login else [])
        if "feed-item" in selector:
            return _FakeLocator(self._rows)
        return _FakeLocator([])

    def goto(self, url: str, timeout=None, wait_until=None):  # noqa: ARG002
        if self.open_error is not None:
            raise self.open_error

    def wait_for_timeout(self, ms: int):  # noqa: ARG002
        pass

    def evaluate(self, js: str):  # noqa: ARG002
        return self._js_result

    def close(self):
        self.closed = True


class TestAutoErrorClassification:
    def test_login_gate_auth_required(self):
        page = _FakePage(rows=[], login=True)
        collector = make_collector(fixtures_mode=False, page_factory=lambda: page)
        with pytest.raises(WechatVideoError) as ei:
            collector.list_hot_videos()
        assert ei.value.error_code == AUTH_REQUIRED

    def test_page_changed_platform_reject(self):
        page = _FakePage(rows=[])
        collector = make_collector(fixtures_mode=False, page_factory=lambda: page)
        with pytest.raises(WechatVideoError) as ei:
            collector.list_hot_videos()
        assert ei.value.error_code == PLATFORM_REJECT

    def test_no_valid_items_no_match(self):
        page = _FakePage(rows=[_FakeRow(title="", href="")])
        collector = make_collector(fixtures_mode=False, page_factory=lambda: page)
        with pytest.raises(WechatVideoError) as ei:
            collector.list_hot_videos()
        assert ei.value.error_code == NO_MATCH

    def test_connect_timeout(self):
        def slow_factory():
            raise TimeoutError("connect timeout")

        collector = make_collector(fixtures_mode=False, page_factory=slow_factory)
        with pytest.raises(WechatVideoError) as ei:
            collector.list_hot_videos()
        assert ei.value.error_code == TIMEOUT

    def test_auto_parses_items_and_sorts(self):
        rows = [
            _FakeRow(
                title="标题A", author="达人A", heat="1.2万",
                href="https://channels.weixin.qq.com/video/wxv_auto_a",
            ),
            _FakeRow(
                title="标题B", author="达人B", heat="500",
                href="https://channels.weixin.qq.com/video/wxv_auto_b",
            ),
        ]
        collector = make_collector(fixtures_mode=False, page_factory=lambda: _FakePage(rows=rows))
        items = collector.list_hot_videos()
        assert [it["title"] for it in items] == ["标题A", "标题B"]
        assert items[0]["heat_score"] == 12000.0
        assert items[1]["heat_score"] == 500.0
        assert items[0]["video_id"] == "wxv_auto_a"
        assert items[0]["source_platform"] == "视频号"
        assert items[0]["source_author"] == "达人A"

    def test_resolve_auto_direct_url_ok(self):
        page = _FakePage(js_result="https://cdn.example/v.mp4")
        collector = make_collector(fixtures_mode=False, page_factory=lambda: page)
        url = collector.resolve_direct_url("wxv_auto_1")
        assert url == "https://cdn.example/v.mp4"

    def test_resolve_auto_empty_direct_url_platform_reject(self):
        collector = make_collector(fixtures_mode=False, page_factory=lambda: _FakePage(js_result=""))
        with pytest.raises(WechatVideoError) as ei:
            collector.resolve_direct_url("wxv_auto_1")
        assert ei.value.error_code == PLATFORM_REJECT

    def test_resolve_auto_login_gate_auth_required(self):
        collector = make_collector(fixtures_mode=False, page_factory=lambda: _FakePage(login=True))
        with pytest.raises(WechatVideoError) as ei:
            collector.resolve_direct_url("wxv_auto_1")
        assert ei.value.error_code == AUTH_REQUIRED

    def test_resolve_auto_goto_timeout(self):
        page = _FakePage(js_result="", open_error=TimeoutError("page load slow"))
        collector = make_collector(fixtures_mode=False, page_factory=lambda: page)
        with pytest.raises(WechatVideoError) as ei:
            collector.resolve_direct_url("wxv_auto_1")
        assert ei.value.error_code == TIMEOUT
