"""采集器工厂与来源遍历。

真实采集走 Playwright 共享 Chrome（CDP），选择器全部配置化（平台改版只改配置）；
离线开发/测试走 fixtures 采集器，零登录态、零网络。
"""

from __future__ import annotations

from typing import Iterable

from ..config import SourcingConfig
from .base import Collector, CollectorError, QuoteCollector  # noqa: F401

__all__ = ["Collector", "QuoteCollector", "CollectorError", "make_collector",
           "iter_sources", "resolve_mode"]


def make_collector(source: str, config: SourcingConfig, mode: str = "auto") -> Collector:
    """工厂：mode=fixtures 强制离线；auto/live 用真实采集器。"""
    if mode == "fixtures":
        from .fixtures import FixtureCollector, FixtureQuoteCollector

        if source in ("alibaba", "taobao"):
            return FixtureQuoteCollector(source, config)  # type: ignore[return-value]
        return FixtureCollector(source, config)

    spec = getattr(config, source)
    if source == "youmi":
        from .youmi import YoumiCollector

        return YoumiCollector(spec)
    if source == "opportunities":
        from .opportunities import OpportunitiesCollector

        return OpportunitiesCollector(spec)
    if source == "doudian":
        from .doudian import DoudianCollector

        return DoudianCollector(spec)
    if source == "alibaba":
        from .alibaba import AlibabaQuoteCollector

        return AlibabaQuoteCollector(spec)  # type: ignore[return-value]
    if source == "taobao":
        from .taobao import TaobaoReferenceCollector

        return TaobaoReferenceCollector(spec)  # type: ignore[return-value]
    raise ValueError(f"未知来源: {source}")


def iter_sources(config: SourcingConfig) -> Iterable[str]:
    for s in ("opportunities", "youmi", "doudian", "alibaba", "taobao"):
        if getattr(config, s).enabled:
            yield s


def resolve_mode(source: str, config: SourcingConfig, mode: str) -> str:
    """auto：来源未启用时回退 fixtures；否则用真实采集器。"""
    if mode != "auto":
        return mode
    if not getattr(config, source).enabled:
        return "fixtures"
    return "live"
