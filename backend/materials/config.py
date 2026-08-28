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


class NormalizeConfig(BaseSettings):
    """标准化器参数（子代理 C；对齐 05 文档第三节 ffmpeg 输出参数锁定示例，参数集中便于按素材源微调）。

    自身也是 settings 模型（env_prefix=MATERIALS_），因此 `MATERIALS_FFMPEG_PATH` /
    `MATERIALS_FFPROBE_PATH` 直接映射到本子配置的 ffmpeg_path / ffprobe_path
    （已实测：pydantic-settings 2.15 嵌套 BaseSettings 可读环境变量；普通嵌套 BaseModel 不读）。
    密钥纪律（P-004）：本配置只存路径，不存任何凭证。
    """

    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore")

    ffmpeg_path: str | None = Field(
        default=None,
        description="ffmpeg 可执行路径（环境变量 MATERIALS_FFMPEG_PATH 覆盖；None=走 PATH 自动探测）",
    )
    ffprobe_path: str | None = Field(
        default=None,
        description="ffprobe 可执行路径（环境变量 MATERIALS_FFPROBE_PATH 覆盖；None=走 PATH 或 ffmpeg 同目录自动探测）",
    )
    transcode_timeout_seconds: int = Field(
        default=300, description="ffmpeg 转码/ffprobe 探测超时（秒）；R-M2-16 转码资源占用双重保护之一"
    )
    output_format: str = Field(default="mp4", description="标准化输出容器格式（默认 mp4）")
    crf: int = Field(default=23, description="libx264 质量档位（05 示例 -crf 23）")
    ratio_tolerance: float = Field(
        default=0.01, description="宽高比与 9/16 的容差（默认 ±0.01；normalizer.validate_specs 模块常量同值）"
    )
    duration_limit: int = Field(default=300, description="转码 -t 截断上限（秒），对齐 MAX_DURATION")
    video_filter: str = Field(
        default=(
            "scale=720:1280:force_original_aspect_ratio=decrease,"
            "pad=720:1280:(ow-iw)/2:(oh-ih)/2"
        ),
        description="ffmpeg -vf 输出参数（05 文档第三节锁定示例；实际按素材源微调时改这里）",
    )


class TikTokConfig(BaseSettings):
    """TikTokDownloader 采集器参数（子代理 A；对齐 context/README.md 2.1 外部契约 + R-M2-04/R-M2-05）。

    自身也是 settings 模型（env_prefix=MATERIALS_），各字段用 validation_alias 显式指定
    **完整**环境变量名（实测 pydantic-settings 2.15：字段带别名时 env 名 = 别名原样，
    前缀不再叠加），因此 `MATERIALS_TIKTOK_BINARY` / `MATERIALS_TIKTOK_TIMEOUT_SECONDS` /
    `MATERIALS_TIKTOK_OUTPUT_DIR` / `MATERIALS_TIKTOK_VERSION_PIN` /
    `MATERIALS_TIKTOK_ENABLED` 直接映射到本子配置对应字段；
    populate_by_name=True 保证 `load_config(tiktok={...})` 按字段名覆盖可用（测试/CLI 常用）。
    密钥纪律（P-004）：本配置只存路径/开关/版本号，不存任何凭证。
    """

    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore", populate_by_name=True)

    binary_path: str | None = Field(
        default=None,
        validation_alias="MATERIALS_TIKTOK_BINARY",
        description="TikTokDownloader 可执行路径（环境变量 MATERIALS_TIKTOK_BINARY 覆盖；None=走 PATH 探测）",
    )
    timeout_seconds: int = Field(
        default=300,
        validation_alias="MATERIALS_TIKTOK_TIMEOUT_SECONDS",
        description="外部 CLI 子进程超时（秒）；超时→TIMEOUT（R-M2-06）",
    )
    default_output_dir: str = Field(
        default="data/tiktok_downloads",
        validation_alias="MATERIALS_TIKTOK_OUTPUT_DIR",
        description="采集默认输出目录（环境变量 MATERIALS_TIKTOK_OUTPUT_DIR 覆盖）",
    )
    version_pin: str = Field(
        default="4.1.x",
        validation_alias="MATERIALS_TIKTOK_VERSION_PIN",
        description=(
            "推荐锁定版本线（环境变量 MATERIALS_TIKTOK_VERSION_PIN 覆盖；requirements 固定精确版本，"
            "升级需回归，安装说明见 collectors/README.md）"
        ),
    )
    enabled: dict[str, bool] = Field(
        default_factory=lambda: {"douyin": True, "kuaishou": True, "xiaohongshu": True},
        validation_alias="MATERIALS_TIKTOK_ENABLED",
        description=(
            "平台开关（环境变量 MATERIALS_TIKTOK_ENABLED 为 JSON 对象，如 {\"kuaishou\": false}）；"
            "False=该平台禁用采集（R-M2-21 风控开关）"
        ),
    )


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
    normalize: NormalizeConfig = Field(default_factory=NormalizeConfig)
    tiktok: TikTokConfig = Field(default_factory=TikTokConfig)


def load_config(**overrides: Any) -> MaterialsConfig:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return MaterialsConfig(**overrides)
