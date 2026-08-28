"""M5 自动小店投放（商品托管）模块 · 时间工具。

时间口径（总控 data-audit DA-001）：时间一律 UTC（ISO8601 带时区）存储，
展示层转 UTC+8；时间戳字段名后缀 `_at`。SQLite 存储会丢失 tzinfo，
读取时用 ensure_aware 统一补 UTC，避免 naive/aware 比较报错。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    """当前 UTC 带时区时间（列默认值/显式写入统一用）。"""
    return datetime.now(timezone.utc)


def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite 存储会丢失 tzinfo；读取时统一补 UTC（避免 naive/aware 比较报错）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
