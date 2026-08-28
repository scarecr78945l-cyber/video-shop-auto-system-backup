"""M5 自动小店投放（商品托管）模块配置（pydantic-settings，环境变量前缀 ADS_）。

对齐 _management/modules/m5-ads/context/README.md 与 database/README.md：
批量/预算/止损/余额等可配置项集中在此（运行时优先读 app_config 表
read_app_config 只读，未配置时回落此处默认值）。
密钥纪律（P-004）：本配置只存路径/数值，不存任何凭证（无 Token/Cookie/密码字段）。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdsConfig(BaseSettings):
    """总配置。环境变量：ADS_DB_URL / ADS_BATCH_SIZE / ADS_KILL_SWITCH 等。"""

    model_config = SettingsConfigDict(env_prefix="ADS_", env_file=".env", extra="ignore")

    db_url: str = Field(
        default="sqlite:///data/db/m5-ads.db",
        description=(
            "本模块独立库 DSN；开发默认 SQLite（backend/data/db/m5-ads.db，不入 git），"
            "生产切 postgresql+psycopg2://..."
        ),
    )
    log_level: str = "INFO"

    # ---- 批量/调度（context 三/4.3 节） ----
    batch_size: int = Field(default=50, description="单批托管上限（平台硬限 ≤50/批）")
    batch_interval_s: int = Field(default=300, description="批间隔（秒，防风控，可配）")
    report_interval_s: int = Field(default=1800, description="报表回读周期（秒，10~30min 可配）")

    # ---- 止损/余额（止损规则表 S1/S3/S5/S6） ----
    stoploss_impression: int = Field(default=500, description="止损曝光阈值（次），S1：花费>0 成交=0 且曝光≥阈值")
    min_balance_fen: int = Field(default=10000, description="余额阈值（分，¥100），S5：低于阈值暂停新托管+告警")
    roi_floor_ratio: float = Field(default=0.8, description="ROI 止损线（目标×80%，持续 2 快照周期），S3")
    max_active_campaigns: int = Field(default=40, description="投放中商品数上限，S6：超限停止新增等自然淘汰")

    # ---- 预算三重硬约束（S7，单位分；0=不限） ----
    budget_single_fen: int = Field(default=0, description="单笔预算（分）；0=不限")
    budget_daily_fen: int = Field(default=0, description="日总预算（分）；0=不限")
    budget_plan_fen: int = Field(default=0, description="计划总预算（分）；0=不限")

    # ---- 总开关/浏览器 ----
    kill_switch: bool = Field(default=False, description="一键全停总开关，S8 最高优先级")
    cdp_port: int = Field(default=9222, description="共享 Chrome CDP 端口（Playwright connect_over_cdp）")

    # ---- 投放设置（v0.3 追加：目标 ROI 取值策略，08 文档四②） ----
    target_roi_override: float | None = Field(
        default=None,
        description=(
            "目标 ROI 配置覆盖值（浮点倍数，如 2.00，非金额不走分）。非 None 时优先于系统推荐值；"
            "环境变量 ADS_TARGET_ROI_OVERRIDE（context README 中 M5_ADS_TARGET_ROI_OVERRIDE "
            "为模块级命名，本文件 env_prefix=ADS_ 统一映射）"
        ),
    )
    roi_recommended_source: str = Field(
        default="system",
        description=(
            "系统推荐 ROI 来源标识：system=后台系统推荐（默认）；预留 class_avg 等扩展来源。"
            "环境变量 ADS_ROI_RECOMMENDED_SOURCE"
        ),
    )


def load_config(**overrides: Any) -> AdsConfig:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return AdsConfig(**overrides)
