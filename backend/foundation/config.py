"""M0 基座配置（pydantic-settings，环境变量前缀 M0_）。

环境变量（只列名不列值，见 _management/modules/m0-foundation/context/README.md）：
M0_DB_URL / M0_LOG_LEVEL / M0_LEASE_MINUTES / M0_DATA_DIR
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class FoundationConfig(BaseSettings):
    """M0 基座配置。生产切 PostgreSQL：M0_DB_URL=postgresql+psycopg2://..."""

    model_config = SettingsConfigDict(env_prefix="M0_", env_file=".env", extra="ignore")

    db_url: str = "sqlite:///data/m0-foundation.db"
    log_level: str = "INFO"
    lease_minutes: int = 45  # 队列租约时长（09 文档：45min 过期回收）
    data_dir: Path = Path("data")


def load_config(**overrides) -> FoundationConfig:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return FoundationConfig(**overrides)
