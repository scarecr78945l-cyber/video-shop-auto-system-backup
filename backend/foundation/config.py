"""M0 基座配置（pydantic-settings，环境变量前缀 M0_）。

环境变量（只列名不列值，见 _management/modules/m0-foundation/context/README.md）：
M0_DB_URL / M0_LOG_LEVEL / M0_LEASE_MINUTES / M0_DATA_DIR
M0_SCHEDULER_POLL_INTERVAL_SECONDS / M0_SCHEDULER_MAX_CLAIM_PER_ROUND /
M0_SCHEDULER_THROTTLE_BASE_SECONDS / M0_SCHEDULER_THROTTLE_LEVELS /
M0_SCHEDULER_CIRCUIT_BREAKER_FAILURES
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerConfig(BaseSettings):
    """调度器配置（环境变量前缀 M0_SCHEDULER_）。

    对齐 09 文档第三节：节流 0~4 级（间隔 ×1/2/4/8/16）、连续失败 ≥2 熔断暂停 stage。
    """

    model_config = SettingsConfigDict(env_prefix="M0_SCHEDULER_", extra="ignore")

    poll_interval_seconds: float = 30.0  # 轮询间隔（CLI --loop 用）
    max_claim_per_round: int = 10        # 每轮最大领取数
    throttle_base_seconds: float = 30.0  # 节流基准间隔（×2^level）
    throttle_levels: int = 5             # 0~4 级
    circuit_breaker_failures: int = 2    # 连续失败 N 次 → 熔断暂停 stage（09 文档）


class FoundationConfig(BaseSettings):
    """M0 基座配置。生产切 PostgreSQL：M0_DB_URL=postgresql+psycopg2://..."""

    model_config = SettingsConfigDict(env_prefix="M0_", env_file=".env", extra="ignore")

    db_url: str = "sqlite:///data/db/m0-foundation.db"  # 宪法第 4 节：backend/data/db/<模块>.db
    log_level: str = "INFO"
    lease_minutes: int = 45  # 队列租约时长（09 文档：45min 过期回收）
    data_dir: Path = Path("data")

    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)


def load_config(**overrides) -> FoundationConfig:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return FoundationConfig(**overrides)
