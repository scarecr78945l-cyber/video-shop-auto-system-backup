"""M3 自动素材优化模块配置（pydantic-settings，环境变量前缀 M3_）。

对齐方案文档 06/09/10：硬性输出规格、模板参数默认值、审核抽检率、
上传双轨模式（REC-002）、门禁阈值、LLM 调用参数。
密钥一律只写环境变量名，值经 os.environ 读取（禁止落库/落日志）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VideoSpec(BaseModel):
    """投放素材硬性输出规格（不可协商，对齐 05/06/09 文档）。"""

    min_width: int = 720
    min_height: int = 1280
    aspect: str = "9:16"
    formats: tuple[str, ...] = ("mov", "mp4")
    max_size_mb: int = 500
    min_duration: int = 5
    max_duration: int = 300
    # ffmpeg 出片参数（子代理-C 使用；此处仅默认值，可经 app_config 覆盖）
    crf: int = 23
    audio_codec: str = "aac"


class ImageSpec(BaseModel):
    """主图/详情图规格（对齐 06 第二节）。"""

    main_image_count: int = 5          # 主图 5 张
    main_image_aspect: str = "1:1"     # 1:1
    detail_image_min: int = 3          # 详情图 ≥3（最低门槛 1+1 可放行，标准 3+3）
    phash_hamming_threshold: int = 8   # 汉明距离 ≤8 视为同图（主图不全相同校验）
    max_regenerate: int = 2            # 质量门禁打回重生成次数上限
    min_edge_px: int = 800             # 门禁最小边


class CopywritingSpec(BaseModel):
    """文案规格（对齐 06 第三节）。"""

    title_min_chars: int = 15
    title_max_chars: int = 35
    ad_variants_min: int = 2           # 投放文案 ≥2 套候选
    badge_variants_min: int = 2        # 角标 ≥2 套候选


class LlmSpec(BaseModel):
    """LLM 调用参数（密钥只走环境变量，此处仅开关/超时/重试）。"""

    deepseek_env: str = "DEEPSEEK_API_KEY"
    kimi_env: str = "KIMI_API_KEY"
    wan_env: str = "WAN_API_KEY"
    fallback_enabled: bool = True      # LLM 不可用时降级规则模板/默认策略
    max_retries: int = 2
    timeout_seconds: int = 60
    daily_cost_budget_cny: float = 50.0  # 日成本预算熔断（记录 ai_generation_logs 统计）


class ReviewSpec(BaseModel):
    """审核闸门（对齐 06 第四节）。"""

    sample_rate: float = 0.1           # 人工复核抽检比例（配置化）
    high_risk_categories: tuple[str, ...] = ()  # 高风险类目强制人工（默认空，配置化）


class UploadSpec(BaseModel):
    """小店素材库上传（REC-002：双轨 UploadService，api|ui|semi）。"""

    mode: str = "api"                  # api 优先 | ui Playwright 兜底 | semi 半自动降级
    batch_size: int = 50               # ≤50/批串行（P-006）
    cdp_port: int = 9223               # 共享 Chrome（小店后台登录态，归 M0 管理）


class M3Config(BaseSettings):
    """总配置。环境变量：M3_DB_URL / M3_UPLOAD_MODE 等。"""

    model_config = SettingsConfigDict(
        env_prefix="M3_", env_file=".env", extra="ignore"
    )

    db_url: str = Field(
        default="sqlite:///data/db/m3-optimization.db",
        description="本模块独立库；生产切 postgresql+psycopg2://...",
    )
    log_level: str = "INFO"
    data_dir: Path = Field(default_factory=lambda: Path("data"))
    fixtures_dir: Path = Field(default_factory=lambda: Path("fixtures"))
    gen_concurrency: int = 2           # 出片/生图并发数

    video: VideoSpec = Field(default_factory=VideoSpec)
    image: ImageSpec = Field(default_factory=ImageSpec)
    copywriting: CopywritingSpec = Field(default_factory=CopywritingSpec)
    llm: LlmSpec = Field(default_factory=LlmSpec)
    review: ReviewSpec = Field(default_factory=ReviewSpec)
    upload: UploadSpec = Field(default_factory=UploadSpec)


def load_config(**overrides: Any) -> M3Config:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return M3Config(**overrides)
