"""M4 自动上架模块配置（pydantic-settings，环境变量前缀 LISTING_）。

开发默认库 backend/data/db/m4-listing.db（一模块一库铁律：只操作本模块库），
生产通过 LISTING_DB_URL 切 PostgreSQL；LISTING_LEASE_MINUTES 控制任务租约
（断点续跑 45min 过期回收，09 文档口径）。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ListingConfig(BaseSettings):
    """总配置。环境变量：LISTING_DB_URL / LISTING_LEASE_MINUTES 等。"""

    model_config = SettingsConfigDict(
        env_prefix="LISTING_", env_file=".env", extra="ignore"
    )

    db_url: str = Field(
        default="sqlite:///data/db/m4-listing.db",
        description=(
            "SQLAlchemy DSN；开发默认 SQLite（backend/data/db/m4-listing.db，"
            "不入 git），生产切 postgresql+psycopg2://..."
        ),
    )
    lease_minutes: int = 45  # 任务租约分钟数：到期可被其他 worker 回收（断点续跑）
    audit_poll_interval_seconds: float = 60.0  # query_audit_status 轮询间隔
    audit_poll_max_attempts: int = 30  # 轮询最大次数（超限转人工/失败）
    link_verify_timeout_seconds: float = 10.0  # 真实链接 HTTP 可达性校验超时（R22）


def load_config(**overrides: Any) -> ListingConfig:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return ListingConfig(**overrides)
