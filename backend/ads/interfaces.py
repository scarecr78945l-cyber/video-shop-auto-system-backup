"""M5 自动小店投放 · 页面操作抽象接口（v0.3 执行层公共骨架）。

Playwright 真实实现（connect_over_cdp 共享浏览器）在实机/登录态就绪后落地；
fixtures 阶段由各子代理提供 MockPageOps 实现，离线跑通全流程。
两个并行子代理（托管执行器 / 投放设置）共用本契约，避免相互 import 冲突。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PageOps(Protocol):
    """浏览器页面最小操作集（Playwright 语义的子集）。

    子代理实现 Mock 时逐方法返回可控值；真实实现后续用 Playwright
    Page 包装（goto/click/fill/select_option/…一一对应）。
    """

    def goto(self, url: str) -> None: ...
    def wait_for(self, selector: str, timeout_ms: int = 15000) -> None: ...
    def click(self, selector: str) -> None: ...
    def fill(self, selector: str, value: str) -> None: ...
    def select_option(self, selector: str, value: str) -> None: ...
    def read_text(self, selector: str) -> str: ...
    def read_attr(self, selector: str, attr: str) -> str | None: ...
    def exists(self, selector: str) -> bool: ...
    def count(self, selector: str) -> int: ...
    def screenshot(self, path: str) -> str: ...
    def close(self) -> None: ...


class PageChangedError(RuntimeError):
    """页面结构与配置锚点不一致（P-003/R3）：选择器/特征元素缺失即触发。

    携带 evidence（截图路径/缺失特征/当前 URL）供留痕与人工接管。
    """

    def __init__(self, message: str, evidence: dict | None = None):
        super().__init__(message)
        self.evidence: dict = evidence or {}
