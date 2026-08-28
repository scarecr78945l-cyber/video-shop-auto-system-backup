"""M2 自动收集素材模块配置（pydantic-settings，环境变量前缀 MATERIALS_）。

对齐 05/09/10 文档与 context/README.md 数据字典：
- ★素材硬规格常量集中在本文件（P-007 防复发），供标准化器/入库/投放绑定复用；
- 下载中台参数（并发/退避基数/熔断阈值/租约分钟）供子代理 F 复用；
- 去重阈值（phash 汉明距离）供双去重器（子代理 E）校准后引用。
密钥一律只走环境变量（仅写变量名，禁止落库/落日志/落文档）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# ★ 素材硬规格常量（写死，投放/投稿共用；05 文档第三节 + context 1.3 + P-007）
# ---------------------------------------------------------------------------
MIN_WIDTH: int = 720              # 分辨率下限宽 ≥720
MIN_HEIGHT: int = 1280            # 分辨率下限高 ≥1280
MIN_RATIO: float = 9 / 16         # 9:16 竖屏校验用（宽/高下限比）
MAX_SIZE_BYTES: int = 524288000   # 大小上限 ≤500M（524288000 字节）
MIN_DURATION: int = 5             # 时长下限 5 秒
MAX_DURATION: int = 300           # 时长上限 300 秒
ALLOWED_FORMATS: list[str] = ["mp4", "mov"]  # 允许的视频容器格式

# 评估标签枚举（M5 回写唯一口径；M2 入库时为 NULL，context 1.4）
EVALUATION_VALUES: tuple[str, ...] = ("exploring", "efficient", "potential")


class DownloadConfig(BaseModel):
    """下载中台参数（子代理 F 复用，对齐 09 文档第二节错误码/退避体系）。"""

    concurrency: int = 3                  # 并发下载数
    backoff_base_seconds: float = 30.0    # 失败退避基数：间隔 ×1/2/4/8/16
    circuit_breaker_failures: int = 2     # 连续失败 N 次 → risk_control 熔断（任务书/risks R-M2-04 口径 ≥2）
    lease_minutes: int = 45               # 下载任务租约时长（过期回收）


class DedupConfig(BaseModel):
    """去重阈值（双去重器校准后引用；对齐 sourcing/dedup.py 的 hamming 口径）。"""

    phash_hamming_threshold: int = 8      # 汉明距离 ≤8 视为疑似重复（fixtures 离线校准后定默认值）


class MaterialsConfig(BaseSettings):
    """总配置。环境变量：MATERIALS_DB_URL / MATERIALS_STORAGE_DIR 等。"""

    model_config = SettingsConfigDict(
        env_prefix="MATERIALS_", env_file=".env", extra="ignore"
    )

    db_url: str = Field(
        default="sqlite:///data/db/m2-materials.db",
        description="本模块独立库；生产切 postgresql+psycopg2://...",
    )
    log_level: str = "INFO"
    data_dir: Path = Field(default_factory=lambda: Path("data"))
    fixtures_dir: Path = Field(default_factory=lambda: Path("fixtures"))
    storage_dir: Path = Field(
        default_factory=lambda: Path("data/materials"),
        description="素材存储根目录（环境变量 MATERIALS_STORAGE_DIR 覆盖）；file_path 为其下相对键",
    )

    download: DownloadConfig = Field(default_factory=DownloadConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)


def load_config(**overrides: Any) -> MaterialsConfig:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return MaterialsConfig(**overrides)
