"""共享 Chrome（CDP）浏览器会话封装。

对应对应方案文档：Playwright 复用共享 Chrome（CDP 端口），
平台登录态在浏览器侧维护，本模块只负责连接与页面复用。
"""

from __future__ import annotations

import os
import threading
from typing import Optional

from .base import CollectorError

try:
    from playwright.sync_api import Browser, Page, sync_playwright
except Exception:  # pragma: no cover - playwright 未安装
    Browser = None  # type: ignore
    Page = None  # type: ignore
    sync_playwright = None  # type: ignore

# 全局唯一 playwright 实例：多个 SharedBrowser 实例在同一进程共享，
# 避免 sync API 多次 start() 冲突（Sync API inside asyncio loop）
_pw_lock = threading.Lock()
_pw_instance = None


def _playwright():
    global _pw_instance
    if _pw_instance is None:
        with _pw_lock:
            if _pw_instance is None:
                if sync_playwright is None:
                    raise CollectorError("playwright 未安装", "ENV_MISSING")
                _pw_instance = sync_playwright().start()
    return _pw_instance


class SharedBrowser:
    """连接浏览器（CDP）。cdp_port 与 chrome_path 来自配置/环境变量。"""

    def __init__(self, cdp_port: int = 9222, chrome_path: str = ""):
        self.cdp_port = int(os.environ.get("SOURCING_CDP_PORT", cdp_port))
        self.chrome_path = chrome_path or os.environ.get("SOURCING_CHROME_PATH", "")
        self._browser: Optional[Browser] = None

    def connect(self) -> Browser:
        if self._browser is not None:
            return self._browser
        pw = _playwright()
        try:
            self._browser = pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{self.cdp_port}"
            )
        except Exception as e:
            raise CollectorError(
                f"浏览器连接失败（CDP :{self.cdp_port}）：{e}，"
                "请确认浏览器已以 --remote-debugging-port 启动并保持登录态",
                "AUTH_REQUIRED",
            ) from e
        return self._browser

    def page(self) -> Page:
        """新建标签页，但复用已有 context（共享 cookies，登录态不丢）。

        登录态保护：优先使用有页面的 context（用户登录所在的），绝不新建
        无登录态的 context，也不关闭/清理浏览器。
        """
        browser = self.connect()
        ctx = None
        for c in browser.contexts:
            if c.pages:
                ctx = c
                break
        if ctx is None and browser.contexts:
            ctx = browser.contexts[0]
        if ctx is None:
            raise CollectorError(
                "浏览器无上下文，请先在浏览器打开页面并保持登录",
                "AUTH_REQUIRED",
            )
        return ctx.new_page()

    def current_page(self, match_url: str = "") -> Page:
        """返回浏览器中匹配域名的页面（多标签页时按 URL 定位），不新建、不导航。"""
        browser = self.connect()
        pages: list = []
        for c in browser.contexts:
            pages.extend(c.pages)
        if not pages:
            raise CollectorError("浏览器无打开的页面", "NO_MATCH")
        if match_url:
            for pg in reversed(pages):
                try:
                    if match_url in pg.url:
                        return pg
                except Exception:
                    continue
            raise CollectorError(
                f"浏览器未找到含 {match_url} 的页面，请先在该平台打开榜单页",
                "NO_MATCH",
            )
        return pages[-1]

    def close(self) -> None:
        """仅断开 CDP 连接，不影响真实浏览器进程与登录态。"""
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
        self._browser = None


def detect_page_changed(page, expected_selectors: list[str]) -> bool:
    """页面改版检测：预期选择器一个都找不到 → 大概率改版。"""
    if not expected_selectors:
        return False
    try:
        for sel in expected_selectors:
            if page.locator(sel).first.is_visible(timeout=2000):
                return False
    except Exception:
        pass
    return True


def _redact_text(text: str) -> str:
    """敏感信息脱敏（证据留痕时使用）。"""
    import re

    text = re.sub(r"\b\d{11}\b", "138****0000", text)
    text = re.sub(r"(?i)(password|token|secret)[=:]\S+", r"\1=***", text)
    return text
