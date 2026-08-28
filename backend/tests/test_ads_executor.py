"""M5 自动小店投放（商品托管）· 托管执行器测试（Mock 驱动，无真实浏览器）。

覆盖：ShopAdsSession（默认值/时区/非法登录态）、check_login（logged_in/expired/无特征）、
BrowserConnector 三件套（Mock 连接器/Playwright 骨架占位）、MockPageOps（冒烟+Protocol 合规/
脚本化动作/错误与缺失/截图写文件）、verify_page_signature（通过/缺失抛 PageChangedError
evidence 齐全/未配置不阻塞）、ShopAdsExecutor.add_product（happy path/截断/防风控间隔/
page_changed/AUTH_REQUIRED/NO_MATCH/TIMEOUT 映射）、run_batch（fake form 调用链/settings
缺失与方法缺失兜底/add_product 错误传播/settings 异常映射/submit blocked/真实 settings 集成）。

fixtures 全部在测试文件内自建（不依赖/不改写 conftest 既有内容）。

运行（P-001：必须带独立 basetemp，本模块统一 .pytest-tmp-m5）：
  python -m pytest tests/test_ads_executor.py -q --basetemp=".pytest-tmp-m5"
"""

import sys  # noqa: F401  （预留：sys.modules 场景调试用）
from datetime import datetime, timezone

import pytest

from ads.executor import (
    BrowserConnector,
    MockBrowserConnector,
    MockPageOps,
    PlaywrightBrowserConnector,
    ShopAdsExecutor,
    ShopAdsSession,
    check_login,
    verify_page_signature,
)
from ads.interfaces import PageChangedError, PageOps
from ads.settings import SubmitResult
from ads.ui_config import ShopAdsPages, ShopAdsSelectors, ShopAdsUiConfig

# ---------------------------------------------------------------- 测试工具

# fixtures 阶段注入的选择器值（key 与 ui_config.ShopAdsSelectors 完全对齐）
_FIXTURE_SELECTORS = {
    "home_add_button": "#home-add",
    "add_product_row": ".product-row",
    "add_product_checkbox": "input[data-pid='{pid}']",
    "add_product_bucket": ".bucket",
    "add_product_next": "#next-btn",
    "add_product_count_hint": ".count-hint",
    "settings_target_roi": "#target-roi",
    "settings_target_net_roi": "#target-net-roi",
    "settings_target_goods": "#target-goods",
    "settings_roi_input": "#roi-input",
    "settings_roi_recommended": "#roi-recommended",
    "settings_material_row": ".material-row",
    "settings_material_checkbox": ".material-checkbox[data-mid='{mid}']",
    "settings_submit": "#submit-btn",
    "settings_error_banner": ".error-banner",
}


def _make_ui(**overrides):
    """构造 UI 配置：选择器注入 fixtures 值；非选择器键走顶层配置字段
    （batch_size/item_interval_s/page_signature/screenshot_dir/pages 等）。"""
    selectors = dict(_FIXTURE_SELECTORS)
    top = {}
    for key, value in overrides.items():
        if key in _FIXTURE_SELECTORS:
            selectors[key] = value
        else:
            top[key] = value
    ui_kwargs = {
        "selectors": ShopAdsSelectors(**selectors),
        "batch_size": top.pop("batch_size", 50),
        "item_interval_s": top.pop("item_interval_s", 0.0),
        "screenshot_dir": top.pop("screenshot_dir", "data/ads/evidence-test"),
        "page_signature": top.pop("page_signature", {}),
    }
    pages = top.pop("pages", None)
    if pages is not None:
        ui_kwargs["pages"] = pages
    return ShopAdsUiConfig(**ui_kwargs)


# run_batch 编排断言用的假 SettingsForm（注入 ads.settings.SettingsForm）
class _FakeSettingsForm:
    """记录调用链的假 SettingsForm（run_batch 编排断言用，含 evidence 字段）。"""

    last_form = None  # 最近一次构造实例（供调用链断言）

    def __init__(self, page, ui_config, **kwargs):
        _FakeSettingsForm.last_form = self
        self.page = page
        self.ui = ui_config
        self.ctor_kwargs = dict(kwargs)
        self.calls = []
        self.evidence = []  # 模拟 settings.evidence（run_batch 会合并）

    def choose_target(self, target_type):
        self.calls.append(("choose_target", target_type))

    def fill_roi(self, roi):
        self.calls.append(("fill_roi", roi))

    def bind_materials(self, material_ids):
        self.calls.append(("bind_materials", list(material_ids)))

    def submit(self):
        self.calls.append(("submit",))
        return SubmitResult(passed=True)


class _BlockedSettingsForm(_FakeSettingsForm):
    """submit 返回 blocked（PLATFORM_REJECT，如余额不足）。"""

    def submit(self):
        self.calls.append(("submit",))
        return SubmitResult(passed=False, blocked_reason="余额不足", error_code="PLATFORM_REJECT")


class _IncompleteSettingsForm:
    """缺少 bind_materials 的假表单（方法缺失 → settings_unavailable）。"""

    def __init__(self, page, ui_config, **kwargs):
        self.calls = []
        self.evidence = []

    def choose_target(self, target_type):
        self.calls.append(("choose_target", target_type))

    def fill_roi(self, roi):
        self.calls.append(("fill_roi", roi))

    def submit(self):
        self.calls.append(("submit",))
        return SubmitResult(passed=True)
    # 注意：未定义 bind_materials（模拟必需方法缺失）


# ---------------------------------------------------------------- MockPageOps
def test_mock_smoke_and_protocol(tmp_path):
    mock = MockPageOps()
    assert isinstance(mock, PageOps)  # runtime_checkable Protocol 合规
    mock.goto("https://channels.weixin.qq.com/shop")
    mock.wait_for("#next-btn", timeout_ms=5000)
    mock.click("input[data-pid='1']")
    mock.fill("#roi-input", "2.00")
    mock.select_option("#target", "roi")
    assert mock.exists("#next-btn") is True
    assert mock.count("#next-btn") == 0  # 未设置 count → 0
    mock.set_count(".product-row", 3)
    assert mock.count(".product-row") == 3
    shot = mock.screenshot(str(tmp_path / "ev" / "1.png"))
    assert shot == str(tmp_path / "ev" / "1.png")
    assert (tmp_path / "ev" / "1.png").exists()  # 截图实际写临时文件
    assert (tmp_path / "ev" / "1.png").read_bytes() == b"mock-png"
    mock.close()
    assert mock.closed is True
    # history 文本与结构化 ops（含 ts 时间戳）
    assert mock.history[0] == "goto:https://channels.weixin.qq.com/shop"
    assert mock.history[-1] == "close:"
    assert [o["op"] for o in mock.ops] == [
        "goto", "wait_for", "click", "fill", "select_option", "screenshot", "close",
    ]
    assert all(isinstance(o["ts"], float) for o in mock.ops)
    assert mock.click_count("input[data-pid='1']") == 1
    assert mock.fill_value("#roi-input") == "2.00"
    assert mock.option_value("#target") == "roi"
    # 查询方法不写操作历史
    mock.exists("#x")
    mock.count(".y")
    mock.read_text("#z")
    assert mock.history[-1].startswith("close:")


def test_mock_script_actions():
    script = {
        "#roi-recommended": {"action": "text", "value": "2.40"},
        "#rows": {"count": 7},
        "#absent": {"exists": False},
    }
    mock = MockPageOps(script)
    assert mock.read_text("#roi-recommended") == "2.40"
    assert mock.count("#rows") == 7
    assert mock.exists("#absent") is False
    assert mock.count("#absent") == 0
    # set_script / set_text 叠加
    mock.set_script("#roi-input", action="text", value="3.00")
    assert mock.read_text("#roi-input") == "3.00"
    mock.set_text("#label", "账户余额：10000分")
    assert mock.read_text("#label") == "账户余额：10000分"
    # 无脚本/无文本 → ""
    assert mock.read_text("#nothing") == ""


def test_mock_error_and_missing():
    mock = MockPageOps({"#dead": {"action": "error"}})
    with pytest.raises(RuntimeError):
        mock.click("#dead")
    with pytest.raises(RuntimeError):
        mock.wait_for("#dead")
    assert mock.exists("#dead") is True  # error ≠ missing：存在但操作失败
    mock2 = MockPageOps()
    mock2.set_missing("#gone")
    with pytest.raises(RuntimeError):
        mock2.click("#gone")
    assert mock2.exists("#gone") is False
    assert mock2.count("#gone") == 0


# ---------------------------------------------------------------- ShopAdsSession
def test_session_defaults_and_timezone_normalize():
    sess = ShopAdsSession()
    assert sess.login_state == "unknown"
    assert sess.port == 9222
    assert "9222" in sess.cdp_url
    assert sess.created_at.tzinfo is not None  # UTC 带时区
    assert sess.created_at.utcoffset().total_seconds() == 0  # UTC 偏移 0
    # naive 输入自动补 UTC 时区
    naive = ShopAdsSession(created_at=datetime(2025, 1, 1, 0, 0, 0))
    assert naive.created_at.tzinfo is not None
    assert naive.created_at.utcoffset().total_seconds() == 0
    # 显式 UTC 时区保持不变
    aware = ShopAdsSession(created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert aware.created_at.tzinfo is not None


def test_session_invalid_login_state():
    with pytest.raises(ValueError):
        ShopAdsSession(login_state="half")
    with pytest.raises(ValueError):
        ShopAdsSession(login_state="")
    # 合法枚举可构造
    ShopAdsSession(login_state="logged_in")
    ShopAdsSession(login_state="expired")


# ---------------------------------------------------------------- BrowserConnector
def test_connector_mock():
    conn = MockBrowserConnector()
    page = conn.connect()
    assert isinstance(page, MockPageOps)
    assert isinstance(page, PageOps)
    assert isinstance(conn, BrowserConnector)
    # 注入预设页面 → 原样返回
    injected = MockPageOps()
    assert MockBrowserConnector(page=injected).connect() is injected


def test_connector_playwright_skeleton():
    conn = PlaywrightBrowserConnector()
    assert isinstance(conn, BrowserConnector)
    with pytest.raises(NotImplementedError, match="connect_over_cdp"):
        conn.connect()
    # 会话透传
    sess = ShopAdsSession(login_state="logged_in")
    assert PlaywrightBrowserConnector(session=sess).session is sess


# ---------------------------------------------------------------- check_login
def test_check_login_logged_in():
    ui = _make_ui(page_signature={"home": "#home-anchor", "add_product": "#add-anchor"})
    assert check_login(MockPageOps(), ui) == "logged_in"


def test_check_login_expired_and_unknown():
    # 锚点已配置但页面上缺失（特征选择器缺失）→ expired（AUTH_REQUIRED 语义）
    ui = _make_ui(page_signature={"home": "#home-anchor"})
    page = MockPageOps()
    page.set_missing("#home-anchor")
    assert check_login(page, ui) == "expired"
    # 未配置任何特征锚点（fixtures 默认）→ unknown（无法探测，不阻断流程）
    assert check_login(MockPageOps(), _make_ui()) == "unknown"
    # home 未配置时回退任意已配置锚点
    ui2 = _make_ui(page_signature={"add_product": "#add-anchor"})
    assert check_login(MockPageOps(), ui2) == "logged_in"


# ---------------------------------------------------------------- verify_page_signature
def test_verify_signature_ok():
    ui = _make_ui(page_signature={"add_product": "#add-anchor"})
    res = verify_page_signature(MockPageOps(), ui, "add_product")
    assert res["ok"] is True
    assert res["checked"] == ["#add-anchor"]
    assert res["missing"] == []
    assert res["page_key"] == "add_product"
    assert "current_url" in res
    # 多锚点（换行/逗号分隔）
    ui_multi = _make_ui(page_signature={"add_product": "#a1,#a2\n#a3"})
    res = verify_page_signature(MockPageOps(), ui_multi, "add_product")
    assert res["checked"] == ["#a1", "#a2", "#a3"]


def test_verify_signature_missing_raises_with_evidence(tmp_path):
    ui = _make_ui(
        screenshot_dir=str(tmp_path / "shots"),
        page_signature={"add_product": "#add-anchor"},
    )
    page = MockPageOps()
    page.goto("https://channels.weixin.qq.com/shop/add")
    page.set_missing("#add-anchor")
    with pytest.raises(PageChangedError) as exc_info:
        verify_page_signature(page, ui, "add_product")
    evidence = exc_info.value.evidence
    assert evidence["page_key"] == "add_product"
    assert evidence["missing"] == ["#add-anchor"]
    assert evidence["current_url"] == "https://channels.weixin.qq.com/shop/add"
    # 截图写到 screenshot_dir（目录自动创建）
    shot = evidence["screenshot_path"]
    assert shot.startswith(str(tmp_path / "shots"))
    assert (tmp_path / "shots").is_dir()
    assert (tmp_path / "shots").glob("page_changed_add_product_*.png")


def test_verify_signature_not_configured():
    res = verify_page_signature(MockPageOps(), _make_ui(), "home")
    assert res["ok"] is True
    assert res["note"] == "signature_not_configured"
    assert res["checked"] == []


# ---------------------------------------------------------------- ShopAdsExecutor.add_product
def test_add_product_happy_path():
    ui = _make_ui(pages=ShopAdsPages(add_product="https://channels.weixin.qq.com/shop/add"))
    page = MockPageOps()
    result = ShopAdsExecutor(page, ui).add_product([101, 102, 103])
    assert result["ok"] is True
    assert result["error_code"] == ""
    assert result["selected_count"] == 3
    assert result["truncated"] is False
    assert page.current_url == "https://channels.weixin.qq.com/shop/add"
    for pid in (101, 102, 103):
        assert page.click_count(f"input[data-pid='{pid}']") == 1
    assert page.click_count("#next-btn") == 1
    # evidence 每步含 op/selector/ms/url
    assert len(result["evidence"]) >= 5
    for entry in result["evidence"]:
        assert entry["op"] and entry["selector"] and entry["ms"] >= 0
        assert "url" in entry and "ts" in entry
    assert result["evidence"][0]["op"] == "goto"


def test_add_product_truncates_over_batch_size():
    ui = _make_ui(batch_size=5)
    page = MockPageOps()
    result = ShopAdsExecutor(page, ui).add_product(list(range(1, 9)))  # 8 个 > 5
    assert result["ok"] is True
    assert result["selected_count"] == 5
    assert result["truncated"] is True
    for pid in range(1, 6):
        assert page.click_count(f"input[data-pid='{pid}']") == 1
    for pid in range(6, 9):
        assert page.click_count(f"input[data-pid='{pid}']") == 0  # 截断未勾选
    assert page.click_count("#next-btn") == 1


def test_add_product_interval_effect():
    ui = _make_ui(item_interval_s=0.05)
    page = MockPageOps()
    result = ShopAdsExecutor(page, ui).add_product([1, 2, 3])
    assert result["ok"] is True
    # 防风控间隔生效：相邻商品勾选时间戳差 ≥ item_interval_s（Mock ops ts 验证）
    clicks = [o for o in page.ops if o["op"] == "click" and o["selector"].startswith("input[data-pid")]
    assert [c["selector"] for c in clicks] == [
        "input[data-pid='1']", "input[data-pid='2']", "input[data-pid='3']",
    ]
    assert clicks[1]["ts"] - clicks[0]["ts"] >= 0.045
    assert clicks[2]["ts"] - clicks[1]["ts"] >= 0.045
    # evidence 留痕 interval 条目
    intervals = [e for e in result["evidence"] if e["op"] == "interval"]
    assert len(intervals) == 2
    assert all(e["interval_s"] == 0.05 for e in intervals)


def test_add_product_page_changed(tmp_path):
    ui = _make_ui(
        screenshot_dir=str(tmp_path / "shots"),
        page_signature={"home": "#home-anchor", "add_product": "#add-anchor"},
    )
    page = MockPageOps()
    page.set_missing("#add-anchor")
    result = ShopAdsExecutor(page, ui).add_product([1, 2])
    assert result["ok"] is False
    assert result["error_code"] == "page_changed"
    assert result["selected_count"] == 0
    pce = result["page_changed"]
    assert pce["page_key"] == "add_product"
    assert pce["missing"] == ["#add-anchor"]
    assert (tmp_path / "shots").is_dir()
    assert pce["screenshot_path"].startswith(str(tmp_path / "shots"))
    # 未点击任何商品、未点下一步
    assert page.click_count("input[data-pid='1']") == 0
    assert page.click_count("#next-btn") == 0


def test_add_product_auth_required():
    ui = _make_ui(page_signature={"home": "#home-anchor"})
    page = MockPageOps()
    page.set_missing("#home-anchor")  # 特征缺失 → check_login=expired
    result = ShopAdsExecutor(page, ui).add_product([1, 2])
    assert result["ok"] is False
    assert result["error_code"] == "AUTH_REQUIRED"
    assert result["selected_count"] == 0


def test_add_product_empty_no_match():
    result = ShopAdsExecutor(MockPageOps(), _make_ui()).add_product([])
    assert result["ok"] is False
    assert result["error_code"] == "NO_MATCH"
    assert result["selected_count"] == 0


def test_add_product_error_mapping_timeout():
    ui = _make_ui()
    page = MockPageOps()
    page.set_script("input[data-pid='1']", action="error")  # 元素不可用 → RuntimeError
    result = ShopAdsExecutor(page, ui).add_product([1, 2])
    assert result["ok"] is False
    assert result["error_code"] == "TIMEOUT"  # 页面操作失败按超时处理
    assert result["selected_count"] == 0
    # 未配置选择器 → 同样映射 TIMEOUT
    ui2 = _make_ui(add_product_checkbox="")
    result2 = ShopAdsExecutor(MockPageOps(), ui2).add_product([1])
    assert result2["ok"] is False
    assert result2["error_code"] == "TIMEOUT"


# ---------------------------------------------------------------- ShopAdsExecutor.run_batch
def test_run_batch_happy_chain_with_fake_form(monkeypatch):
    from ads import executor as ex

    monkeypatch.setattr("ads.settings.SettingsForm", _FakeSettingsForm)
    ui = _make_ui()
    page = MockPageOps()
    result = ex.ShopAdsExecutor(page, ui).run_batch(
        [101, 102],
        {
            "target_type": "net_roi",
            "roi": 2.5,
            "material_ids": ["m1", "m2"],
            "target_roi_override": 3.0,
        },
    )
    assert result["ok"] is True
    assert result["error_code"] == ""
    assert result["batch_id"].startswith("batch-")
    assert result["selected"] == 2
    assert result["truncated"] is False
    assert result["submit_result"] == {"passed": True, "blocked_reason": "", "error_code": ""}
    assert result["evidence"]  # 含 add_product 留痕
    # 调用链：choose_target → fill_roi → bind_materials → submit（含顺序）
    form = _FakeSettingsForm.last_form
    assert form.calls == [
        ("choose_target", "net_roi"),
        ("fill_roi", 2.5),
        ("bind_materials", ["m1", "m2"]),
        ("submit",),
    ]
    assert form.ctor_kwargs == {"target_roi_override": 3.0}  # 透传 SettingsForm 构造


def test_run_batch_settings_unavailable_cases(monkeypatch):
    from ads import executor as ex

    ui = _make_ui()
    # (a) settings 模块缺失（_load_settings_form 返回 None → 模拟 import 失败）→ settings_unavailable，不崩
    with monkeypatch.context() as mp:
        mp.setattr(ex, "_load_settings_form", lambda: None)
        result = ex.ShopAdsExecutor(MockPageOps(), ui).run_batch([1, 2])
        assert result["ok"] is False
        assert result["error"] == "settings_unavailable"
        assert result["error_code"] == "UNEXPECTED"
        assert result["batch_id"].startswith("batch-")
        assert result["submit_result"] is None
    # (b) SettingsForm 不存在（getattr 兜底返回 None）→ settings_unavailable
    with monkeypatch.context() as mp:
        mp.setattr("ads.settings.SettingsForm", None)
        result = ex.ShopAdsExecutor(MockPageOps(), ui).run_batch([1, 2])
        assert result["error"] == "settings_unavailable"
    # (c) 必需方法缺失（bind_materials 不存在）→ settings_unavailable
    with monkeypatch.context() as mp:
        mp.setattr("ads.settings.SettingsForm", _IncompleteSettingsForm)
        result = ex.ShopAdsExecutor(MockPageOps(), ui).run_batch([1, 2], {"roi": 2.0, "material_ids": ["m1"]})
        assert result["error"] == "settings_unavailable"
    # (d) 真实 settings 模块可被延迟加载（函数直接可用，返回真实类）
    assert ex._load_settings_form() is not None
    assert ex._load_settings_form().__name__ == "SettingsForm"


def test_run_batch_propagates_add_product_error(tmp_path):
    ui = _make_ui(
        screenshot_dir=str(tmp_path / "shots"),
        page_signature={"home": "#home-anchor", "add_product": "#add-anchor"},
    )
    page = MockPageOps()
    page.set_missing("#add-anchor")
    result = ShopAdsExecutor(page, ui).run_batch([1, 2])
    assert result["ok"] is False
    assert result["error_code"] == "page_changed"
    assert result["batch_id"] is None  # add_product 失败 → 无有效批 ID
    assert result["submit_result"] is None
    assert result["selected"] == 0


def test_run_batch_settings_exception_mapping(monkeypatch):
    from ads import executor as ex

    class _RaiseSettingsForm(_FakeSettingsForm):
        def submit(self):
            raise RuntimeError("提交按钮点击失败（模拟显式等待超时）")

    monkeypatch.setattr("ads.settings.SettingsForm", _RaiseSettingsForm)
    result = ex.ShopAdsExecutor(MockPageOps(), _make_ui()).run_batch(
        [1], {"roi": 2.0, "material_ids": ["m1"]}
    )
    assert result["ok"] is False
    assert result["error_code"] == "TIMEOUT"  # settings 链 RuntimeError → TIMEOUT
    assert result["submit_result"] is None

    class _RaiseChangedForm(_FakeSettingsForm):
        def choose_target(self, target_type):
            raise PageChangedError("页面跳转", evidence={"page_key": "settings", "missing": ["#x"]})

    monkeypatch.setattr("ads.settings.SettingsForm", _RaiseChangedForm)
    result = ex.ShopAdsExecutor(MockPageOps(), _make_ui()).run_batch(
        [1], {"roi": 2.0, "material_ids": ["m1"]}
    )
    assert result["ok"] is False
    assert result["error_code"] == "page_changed"
    assert result["page_changed"]["page_key"] == "settings"


def test_run_batch_submit_blocked(monkeypatch):
    from ads import executor as ex

    monkeypatch.setattr("ads.settings.SettingsForm", _BlockedSettingsForm)
    result = ex.ShopAdsExecutor(MockPageOps(), _make_ui()).run_batch(
        [1, 2], {"roi": 2.0, "material_ids": ["m1"]}
    )
    assert result["ok"] is False
    assert result["error_code"] == "PLATFORM_REJECT"
    assert result["error"] == "余额不足"
    assert result["submit_result"] == {
        "passed": False, "blocked_reason": "余额不足", "error_code": "PLATFORM_REJECT",
    }
    assert result["selected"] == 2
    assert result["batch_id"].startswith("batch-")


def test_run_batch_integration_with_real_settings():
    """run_batch ↔ 真实 settings.py 协同（Mock 驱动）：目标三选一 + 系统推荐 ROI + 素材绑定 + 提交。"""
    ui = _make_ui(
        page_signature={"home": "#home-anchor", "add_product": "#add-anchor"},
        item_interval_s=0.0,
    )
    page = MockPageOps({"#roi-recommended": {"action": "text", "value": "2.40"}})
    result = ShopAdsExecutor(page, ui).run_batch(
        [201, 202],
        {"target_type": "roi", "use_recommended_roi": True, "material_ids": ["m1", "m2"]},
    )
    assert result["ok"] is True
    assert result["selected"] == 2
    assert result["submit_result"] == {"passed": True, "blocked_reason": "", "error_code": ""}
    # settings 表单动作真实落盘到同一 Mock 页面
    assert page.click_count("#target-roi") == 1
    assert page.fill_value("#roi-input") == "2.40"  # 系统推荐 2.40 → 两位小数
    assert page.click_count(".material-checkbox[data-mid='m1']") == 1
    assert page.click_count(".material-checkbox[data-mid='m2']") == 1
    assert page.click_count("#submit-btn") == 1
    # 合并 evidence：含 add_product（goto/click）与 settings（submit 点击）留痕
    assert any(e["op"] == "goto" for e in result["evidence"])
    assert any(e["op"] == "click" and e["selector"] == "#submit-btn" for e in result["evidence"])
