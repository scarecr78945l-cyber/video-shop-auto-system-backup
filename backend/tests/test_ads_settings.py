"""M5 自动小店投放（商品托管）· 投放设置执行层测试（Mock 驱动，无真实浏览器）。

覆盖：pick_materials 素材优选（优先级/排除/limit/稳定排序/空输入）、
validate_submit 提交校验（余额不足/素材不可用/预算超限/全过/优先级）、
SettingsForm（目标三选一/ROI 填值/素材绑定/提交与页面校验/证据留痕）、
MockSettingsPage 冒烟、config 追加字段。

fixtures 全部在测试文件内自建（不依赖/不改写 conftest 既有内容）。

运行（P-001：必须带 --basetemp）：
  python -m pytest tests/test_ads_settings.py -q --basetemp=".pytest-tmp"
"""

import pytest

from ads.config import load_config
from ads.settings import (
    MockSettingsPage,
    SettingsForm,
    SubmitResult,
    pick_materials,
    validate_submit,
)
from ads.ui_config import ShopAdsSelectors, ShopAdsUiConfig

# ---------------------------------------------------------------- 测试工具


def _make_ui(**overrides):
    """构造投放设置页 UI 配置（选择器注入 fixtures 值；可按 key 覆盖/清空）。"""
    selectors = {
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
    selectors.update(overrides)
    return ShopAdsUiConfig(selectors=ShopAdsSelectors(**selectors))


def _mat(mid, evaluation="exploring", status="approved", impressions=None, gmv=None):
    """构造素材 dict（可选 impressions/gmv 字段）。"""
    m = {"material_id": mid, "evaluation": evaluation, "upload_status": status}
    if impressions is not None:
        m["impressions"] = impressions
    if gmv is not None:
        m["gmv"] = gmv
    return m


# ---------------------------------------------------------------- pick_materials
def test_pick_materials_priority_order():
    mats = [
        _mat("m1", evaluation="exploring"),
        _mat("m2", evaluation="efficient"),
        _mat("m3", evaluation="potential"),
    ]
    got = pick_materials(mats)
    assert [m["material_id"] for m in got] == ["m2", "m3", "m1"]  # 高效>潜力>探索期
    # 返回保持输入字段结构（同引用，不裁剪）
    assert got[0] is mats[1]
    assert got[0]["evaluation"] == "efficient"
    assert set(got[0].keys()) == {"material_id", "evaluation", "upload_status"}


def test_pick_materials_excludes_unapproved():
    mats = [
        _mat("r", evaluation="efficient", status="rejected"),   # 审核不通过 → 排除
        _mat("c", evaluation="efficient", status="corrupt"),    # 源文件损坏 → 排除
        _mat("v", evaluation="efficient", status="reviewing"),  # 审核中 → 排除
        _mat("u", evaluation="efficient", status="uploading"),  # 上传中 → 排除
        _mat("p", evaluation="potential", status="approved"),
        _mat("e", evaluation="exploring", status="approved"),
    ]
    got = pick_materials(mats)
    assert [m["material_id"] for m in got] == ["p", "e"]


def test_pick_materials_limit_truncates():
    mats = [
        _mat("e1", "efficient"),
        _mat("e2", "efficient"),
        _mat("e3", "efficient"),
        _mat("p1", "potential"),
        _mat("p2", "potential"),
    ]
    assert [m["material_id"] for m in pick_materials(mats, limit=2)] == ["e1", "e2"]
    assert len(pick_materials(mats)) == 3  # 默认 limit=3
    assert pick_materials(mats, limit=0) == []
    assert pick_materials(mats, limit=-1) == []


def test_pick_materials_same_evaluation_stable_sort():
    mats = [
        _mat("a", "efficient", impressions=100, gmv=5000),
        _mat("b", "efficient", impressions=100, gmv=9000),
        _mat("c", "efficient", impressions=300, gmv=100),
        _mat("d", "efficient"),  # 无曝光/成交 → 视为 0，排同级别末尾
    ]
    got = pick_materials(mats, limit=4)  # 4 个素材，limit 放大以观察完整排序
    assert [m["material_id"] for m in got] == ["c", "b", "a", "d"]
    # 稳定排序：完全相同键值保持输入顺序
    stable = [_mat("x1", "efficient", impressions=1, gmv=1), _mat("x2", "efficient", impressions=1, gmv=1)]
    assert [m["material_id"] for m in pick_materials(stable)] == ["x1", "x2"]


def test_pick_materials_empty_input():
    assert pick_materials([]) == []


def test_pick_materials_no_approved():
    mats = [_mat("a", "efficient", "rejected"), _mat("b", "potential", "reviewing")]
    assert pick_materials(mats) == []


# ---------------------------------------------------------------- validate_submit
def test_validate_submit_balance_insufficient():
    res = validate_submit(balance_fen=9999, min_balance_fen=10000, materials_ok=True)
    assert res.passed is False
    assert res.blocked_reason == "余额不足"
    assert res.error_code == "PLATFORM_REJECT"
    assert isinstance(res, SubmitResult)


def test_validate_submit_materials_unavailable():
    res = validate_submit(balance_fen=50000, min_balance_fen=10000, materials_ok=False)
    assert res.passed is False
    assert res.blocked_reason == "素材未过审/不可投放"
    assert res.error_code == "PLATFORM_REJECT"


def test_validate_submit_budget_over_limit():
    res = validate_submit(
        50000, 10000, True, budget_state={"over_limit": True, "rule": "budget_daily_fen"}
    )
    assert res.passed is False
    assert res.blocked_reason == "预算超限"
    assert res.error_code == "PLATFORM_REJECT"
    # 未超限 / 未传 budget_state → 预算检查通过
    assert validate_submit(50000, 10000, True, budget_state={"over_limit": False}).passed is True
    assert validate_submit(50000, 10000, True, budget_state=None).passed is True


def test_validate_submit_all_pass():
    res = validate_submit(balance_fen=10000, min_balance_fen=10000, materials_ok=True)
    assert res.passed is True
    assert res.blocked_reason == ""
    assert res.error_code == ""


def test_validate_submit_precedence_balance_first():
    res = validate_submit(
        balance_fen=500, min_balance_fen=10000, materials_ok=False,
        budget_state={"over_limit": True},
    )
    assert res.blocked_reason == "余额不足"  # 余额检查优先级最高
    assert res.error_code == "PLATFORM_REJECT"


# ---------------------------------------------------------------- SettingsForm
def test_choose_target_all_three():
    ui = _make_ui()
    mock = MockSettingsPage()
    form = SettingsForm(mock, ui)
    form.choose_target("roi")
    form.choose_target("net_roi")
    form.choose_target("goods")
    assert mock.click_count("#target-roi") == 1
    assert mock.click_count("#target-net-roi") == 1
    assert mock.click_count("#target-goods") == 1
    clicks = [e for e in form.evidence if e["op"] == "click"]
    assert [e["target"] for e in clicks] == ["roi", "net_roi", "goods"]
    assert [e["label"] for e in clicks] == ["成交ROI", "净成交ROI", "商品成交"]


def test_choose_target_invalid_raises():
    form = SettingsForm(MockSettingsPage(), _make_ui())
    with pytest.raises(ValueError):
        form.choose_target("cps")
    with pytest.raises(ValueError):
        form.choose_target("")


def test_fill_roi_normal():
    ui = _make_ui()
    mock = MockSettingsPage()
    form = SettingsForm(mock, ui)
    form.fill_roi(2.5)
    assert mock.fill_value("#roi-input") == "2.50"  # 两位小数格式化
    form.fill_roi(2)
    assert mock.fill_value("#roi-input") == "2.00"
    ev = [e for e in form.evidence if e["op"] == "fill"]
    assert ev[-1]["value"] == "2.00"
    assert ev[-1]["selector"] == "#roi-input"


def test_fill_roi_non_positive_raises():
    form = SettingsForm(MockSettingsPage(), _make_ui())
    for bad in (0, -1, -0.01):
        with pytest.raises(ValueError):
            form.fill_roi(bad)


def test_bind_materials_clicks_checkboxes():
    ui = _make_ui()
    mock = MockSettingsPage()
    form = SettingsForm(mock, ui)
    form.bind_materials(["m1", "m2", "m3"])
    assert mock.click_count(".material-checkbox[data-mid='m1']") == 1
    assert mock.click_count(".material-checkbox[data-mid='m2']") == 1
    assert mock.click_count(".material-checkbox[data-mid='m3']") == 1
    assert [e["mid"] for e in form.evidence if e["op"] == "click"] == ["m1", "m2", "m3"]
    bind_ev = [e for e in form.evidence if e["op"] == "bind"]
    assert bind_ev and bind_ev[0]["material_ids"] == ["m1", "m2", "m3"]


def test_bind_materials_empty_raises():
    with pytest.raises(ValueError):
        SettingsForm(MockSettingsPage(), _make_ui()).bind_materials([])


def test_submit_happy_path_full_flow():
    """happy path：目标+ROI+素材+提交全流程 → passed，素材勾选次数/evidence 正确。"""
    ui = _make_ui()
    mock = MockSettingsPage()
    form = SettingsForm(mock, ui)
    form.choose_target("roi")
    form.fill_roi(2.5)
    form.bind_materials(["m1", "m2"])
    res = form.submit()
    assert res.passed is True
    assert res.blocked_reason == ""
    assert mock.click_count("#submit-btn") == 1
    assert mock.click_count(".material-checkbox[data-mid='m1']") == 1
    assert mock.click_count(".material-checkbox[data-mid='m2']") == 1
    # evidence：操作/选择器/耗时/时间戳字段齐全
    assert len(form.evidence) >= 6
    assert all(e["op"] and e["selector"] and e["ms"] >= 0 and e["ts"] for e in form.evidence)


def test_submit_banner_blocks_balance_and_material():
    ui = _make_ui()
    # 余额不足 banner → blocked + 人工接管
    mock = MockSettingsPage(banner_text="账户余额不足，请充值后继续")
    res = SettingsForm(mock, ui).submit()
    assert res.passed is False
    assert res.blocked_reason == "余额不足"
    assert res.error_code == "PLATFORM_REJECT"
    # 素材未过审 banner（两种文案变体）→ blocked
    for text in ("素材未过审，暂不可投放", "素材未通过审核，请更换素材"):
        res = SettingsForm(MockSettingsPage(banner_text=text), ui).submit()
        assert res.passed is False
        assert res.blocked_reason == "素材未过审/不可投放"
        assert res.error_code == "PLATFORM_REJECT"


def test_submit_unconfigured_banner_raises_timeout():
    ui = _make_ui(settings_error_banner="")
    with pytest.raises(RuntimeError, match="TIMEOUT"):
        SettingsForm(MockSettingsPage(), ui).submit()
    # 选择器已配置但页面无 banner 元素 → 视为无校验失败，通过
    ui_ok = _make_ui()
    mock = MockSettingsPage(missing=[ui_ok.selectors.settings_error_banner])
    res = SettingsForm(mock, ui_ok).submit()
    assert res.passed is True


def test_submit_generic_banner_blocks():
    mock = MockSettingsPage(banner_text="系统繁忙，请稍后再试")
    res = SettingsForm(mock, _make_ui()).submit()
    assert res.passed is False
    assert res.error_code == "PLATFORM_REJECT"
    assert res.blocked_reason == "系统繁忙，请稍后再试"


def test_recommended_roi_and_resolve_policy():
    ui = _make_ui()
    mock = MockSettingsPage()
    form = SettingsForm(mock, ui, target_roi_override=None)
    mock.set_text("#roi-recommended", "2.40")
    assert form.read_recommended_roi() == 2.4
    assert form.resolve_roi(2.4) == 2.4  # 系统推荐优先（无覆盖时）
    override_form = SettingsForm(mock, ui, target_roi_override=3.0)
    assert override_form.resolve_roi(2.4) == 3.0  # 可配置覆盖优先
    with pytest.raises(ValueError):
        form.resolve_roi(None)  # 两者皆无
    # 推荐来源缺失/无元素/非数字 → None
    ui2 = _make_ui(settings_roi_recommended="")
    assert SettingsForm(mock, ui2).read_recommended_roi() is None
    mock2 = MockSettingsPage(missing=["#roi-recommended"])
    assert SettingsForm(mock2, ui).read_recommended_roi() is None
    mock.set_text("#roi-recommended", "abc")
    assert form.read_recommended_roi() is None


# ---------------------------------------------------------------- MockSettingsPage
def test_mock_happy_flow_smoke_and_protocol():
    from ads.interfaces import PageOps

    mock = MockSettingsPage()
    assert isinstance(mock, PageOps)  # runtime_checkable Protocol 合规
    mock.goto("https://channels.weixin.qq.com/shop")
    mock.wait_for("#submit-btn", timeout_ms=5000)
    mock.click("#target-roi")
    mock.fill("#roi-input", "2.00")
    mock.select_option("#xx", "y")
    assert mock.exists("#roi-input") is True
    assert mock.read_text(".error-banner") == ""  # happy：banner 空文本
    mock.set_count(".material-row", 3)
    assert mock.count(".material-row") == 3
    shot = mock.screenshot("evidence/1.png")
    assert shot == "evidence/1.png"
    mock.close()
    assert mock.closed is True
    ops = [o["op"] for o in mock.operations]
    assert ops == ["goto", "wait_for", "click", "fill", "select_option", "screenshot", "close"]
    assert mock.click_count("#target-roi") == 1
    assert mock.fill_value("#roi-input") == "2.00"


def test_mock_missing_element_raises():
    # 精确缺失
    mock = MockSettingsPage(missing=["#roi-input"])
    with pytest.raises(RuntimeError):
        mock.fill("#roi-input", "2.00")
    with pytest.raises(RuntimeError):
        mock.wait_for("#roi-input")
    assert mock.exists("#roi-input") is False
    assert mock.count("#roi-input") == 0
    # 全缺失场景（模拟页面未加载/page_changed）
    mock_all = MockSettingsPage(scenario="missing_element")
    with pytest.raises(RuntimeError):
        mock_all.click("#submit-btn")
    with pytest.raises(RuntimeError):
        mock_all.wait_for("#submit-btn")
    assert mock_all.exists("#submit-btn") is False


# ---------------------------------------------------------------- config 追加字段
def test_config_ads_settings_fields():
    cfg = load_config()
    assert cfg.target_roi_override is None  # 默认不覆盖（系统推荐优先）
    assert cfg.roi_recommended_source == "system"
    cfg2 = load_config(target_roi_override=2.5)
    assert cfg2.target_roi_override == 2.5
