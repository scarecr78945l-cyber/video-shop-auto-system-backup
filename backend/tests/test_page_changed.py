"""detect_page_changed 单元测试（mock page，不依赖真实浏览器）。

对应 `sourcing/collectors/browser.py` 的 `detect_page_changed(page, expected_selectors)`：
- 任一预期选择器可见 → 未改版（False）
- 全部不可见 → 疑似改版（True）
- 空 expected_selectors → 未改版（False，不调用 locator）
- locator 抛异常（页面错误）→ 按改版处理（True，except Exception 兜底）
- is_visible 超时抛 TimeoutError → 按改版处理（True）
"""

from sourcing.collectors.browser import detect_page_changed


class FakeLocator:
    """模拟 Playwright Locator：first 返回自身，is_visible 可配置结果或抛异常。"""

    def __init__(self, visible: bool = False, visible_error: Exception | None = None):
        self._visible = visible
        self._visible_error = visible_error

    @property
    def first(self):
        return self

    def is_visible(self, timeout: float = 2000):
        if self._visible_error is not None:
            raise self._visible_error
        return self._visible


class FakePage:
    """模拟 Playwright Page：locator(sel) 按选择器返回配置好的 FakeLocator。

    - visibility: {sel: bool}  —— locator(sel).is_visible() 的返回值
    - visible_errors: {sel: Exception} —— locator(sel).is_visible() 抛出的异常
    - locator_error: Exception —— 任何 locator(sel) 调用直接抛异常（页面错误）
    """

    def __init__(self, visibility=None, visible_errors=None, locator_error=None):
        self._visibility = dict(visibility or {})
        self._visible_errors = dict(visible_errors or {})
        self._locator_error = locator_error

    def locator(self, sel: str):
        if self._locator_error is not None:
            raise self._locator_error
        return FakeLocator(
            visible=self._visibility.get(sel, False),
            visible_error=self._visible_errors.get(sel),
        )


def test_any_expected_selector_visible_means_not_changed():
    """① 任一预期选择器可见 → 返回 False（未改版）。"""
    page = FakePage(visibility={"row": False, "title": True})
    assert detect_page_changed(page, ["row", "title"]) is False


def test_all_selectors_invisible_means_changed():
    """② 全部预期选择器不可见 → 返回 True（疑似改版）。"""
    page = FakePage(visibility={"row": False, "title": False})
    assert detect_page_changed(page, ["row", "title"]) is True


def test_empty_expected_selectors_not_changed():
    """③ 空 expected_selectors → 返回 False（不调用 locator）。"""
    page = FakePage(visibility={"row": True})
    assert detect_page_changed(page, []) is False


def test_locator_exception_treated_as_changed():
    """④ locator 抛异常（页面错误/已关闭）→ except Exception 兜底 → True。"""
    page = FakePage(locator_error=RuntimeError("page closed"))
    assert detect_page_changed(page, ["row"]) is True


def test_is_visible_timeout_treated_as_changed():
    """⑤ is_visible 超时抛 TimeoutError → except Exception 兜底 → True。"""
    page = FakePage(visible_errors={"row": TimeoutError("timeout 2000ms exceeded")})
    assert detect_page_changed(page, ["row"]) is True


def test_first_visible_short_circuits_before_later_error():
    """选择器按序判断：前面的可见即返回 False，不触碰后续会抛错的 locator。"""
    page = FakePage(
        visibility={"row": True},
        visible_errors={"title": TimeoutError("boom")},
    )
    assert detect_page_changed(page, ["row", "title"]) is False
