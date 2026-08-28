"""M2 自动收集素材模块 · 领域模型与时间工具。

时间戳约定：DDL（database/README.md 第二节）规定 asset_* 表时间戳一律
TEXT ISO8601 UTC；iso_now() 固定 microseconds 宽度，保证同格式字符串
可字典序比较（租约回收 / 退避续跑判断）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    """当前时间 ISO8601 UTC 字符串（固定 microseconds 宽度，可字典序比较）。"""
    return utcnow().isoformat(timespec="microseconds")


def add_minutes_iso(minutes: int) -> str:
    """当前时间 + N 分钟 的 ISO8601 UTC 字符串（下载任务租约过期时间用）。"""
    return (utcnow() + timedelta(minutes=minutes)).isoformat(timespec="microseconds")
