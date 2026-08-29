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

# 相关性门状态枚举（REC-迁移-03 C3 唯一口径；M3 relevance 判定结果消费落此字段，
# 契约见 _management/data-exchange/m2-m3-m4-relevance-gate.json 与 data-audit DA-010）
RELEVANCE_STATUS_VALUES: tuple[str, ...] = (
    "pending",          # 未判定（默认；入库时 pending）
    "passed",           # 相关 → 放行（可进入询价/上架链）
    "failed",           # 不相关 → 淘汰（不进入询价/上架链，状态可查询）
    "manual_review",    # 多款式 → 人工确认目标款（禁止自动创建衍生商品）
)

# M3 relevance 判定结果（gate.result: pass/reject/manual_review）→ relevance_status 映射
RELEVANCE_RESULT_TO_STATUS: dict[str, str] = {
    "pass": "passed",
    "reject": "failed",
    "manual_review": "manual_review",
}


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


class BoardCacheConfig(BaseModel):
    """榜单图缓存参数（子代理 B3；R-M2-09 + context 2.4：缓存键=榜单 id+商品 id、
    缓存目录配置化、失败不影响选品主流程）。

    多源接口化：sources 白名单默认 ["youmi"]（有米云，sourcing 链路已实测打通）；
    "kaogujia"（考古加）为预留源——考古加采集器尚未开发（M1 REC-006 降级为可选第四源），
    落地后由上层通过 BoardImageCache.register_source("kaogujia") 注册，本配置不硬编码依赖。
    """

    cache_dir: Path = Field(
        default_factory=lambda: Path("data/board_cache"),
        description="榜单图缓存目录（默认 data/board_cache；可用 load_config(board_cache=...) 覆盖，或 CLI --cache-dir）",
    )
    enabled: bool = Field(
        default=True,
        description="总开关（False=禁用缓存，cache_image 直接返回失败不发起下载；对齐 tiktok.enabled 风控开关模式）",
    )
    sources: list[str] = Field(
        default_factory=lambda: ["youmi"],
        description="来源白名单（默认 youmi=有米云；kaogujia=考古加预留，待考古加采集器落地后注册）",
    )
    timeout_seconds: float = Field(
        default=30.0, description="图片下载超时（秒）；超时→TIMEOUT（对齐 downloader.py 码表，R-M2-06）"
    )
    max_bytes: int = Field(
        default=10 * 1024 * 1024, description="单张图片大小上限（字节），超限即失败不落盘（防缓存垃圾大文件）"
    )


class WechatVideoConfig(BaseSettings):
    """视频号采集器参数（自研，R-M2-03/R-M2-05；对齐 context/README.md 2.2 外部契约）。

    与 TikTokConfig 同模式（env_prefix=MATERIALS_ + validation_alias 显式完整环境变量名 +
    populate_by_name=True），`load_config(wechat_video={...})` 按字段名覆盖可用（测试/CLI 常用）。
    cdp_port 默认 9223（共享浏览器，以 sourcing config 为准）；profile_dir="shared" 复用
    共享登录态（P-002 不重复开页）；fixtures_mode 默认 True：零浏览器零登录态可跑通全链路
    （R-M2-17），auto 模式待登录态 + 选择器抓包校准后开启。
    密钥纪律（P-004）：本配置只存路径/端口/开关/选择器，不存任何凭证。
    """

    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore", populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="MATERIALS_WECHAT_VIDEO_ENABLED",
        description="视频号采集器总开关（False=禁用该来源，R-M2-21 风控开关）",
    )
    cdp_port: int = Field(
        default=9223,
        validation_alias="MATERIALS_WECHAT_VIDEO_CDP_PORT",
        description="共享浏览器 CDP 端口（默认 9223，以 sourcing config 为准；登录态在共享 profile）",
    )
    profile_dir: str = Field(
        default="shared",
        validation_alias="MATERIALS_WECHAT_VIDEO_PROFILE_DIR",
        description="共享浏览器 user-data-dir 标识（复用登录态，P-002）",
    )
    fixtures_mode: bool = Field(
        default=True,
        validation_alias="MATERIALS_WECHAT_VIDEO_FIXTURES_MODE",
        description="True=离线样本模式（默认，零浏览器零登录态）；False=auto 连共享浏览器解析",
    )
    boards: list[str] = Field(
        default_factory=lambda: ["热门视频"],
        validation_alias="MATERIALS_WECHAT_VIDEO_BOARDS",
        description="板块名（如 热门视频/达人）；fixtures 样本与 board_url_<board> 选择器按名匹配",
    )
    selectors: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="MATERIALS_WECHAT_VIDEO_SELECTORS",
        description="覆盖默认选择器/URL 模板（P-003 平台改版只改配置不崩代码）",
    )


class TaobaoRefsConfig(BaseSettings):
    """淘宝商品视频与同款图采集器参数（子代理 B2'；对齐 context/README.md 2.3 外部契约 + R-M2-08）。

    与 WechatVideoConfig/TikTokConfig 同模式（env_prefix=MATERIALS_ + validation_alias 显式
    完整环境变量名 + populate_by_name=True），`load_config(taobao_refs={...})` 按字段名覆盖可用。
    环境事实：共享 Chrome 登录态待确认 → 本阶段只交付 fixtures 离线模式（fixtures_mode=True）；
    auto 真实浏览器（Playwright 共享 Chrome CDP）仅留配置与接口骨架，未验证不实现细节。
    选择器/URL 全配置化（P-003 平台改版只改配置不崩代码）；page_changed 检测留证据。
    密钥纪律（P-004）：本配置只存开关/端口/选择器，不存任何凭证/Cookie。
    """

    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore", populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="MATERIALS_TAOBAO_REFS_ENABLED",
        description="淘宝采集总开关（False=禁用采集，R-M2-21 风控开关）",
    )
    fixtures_mode: bool = Field(
        default=True,
        validation_alias="MATERIALS_TAOBAO_REFS_FIXTURES_MODE",
        description="True=离线样本模式（默认，读 backend/fixtures/materials/taobao_refs.json）；False=auto 连共享浏览器解析（骨架）",
    )
    cdp_port: int = Field(
        default=9223,
        validation_alias="MATERIALS_TAOBAO_REFS_CDP_PORT",
        description="共享 Chrome CDP 端口（auto 模式用；默认 9223，以 sourcing config 为准）",
    )
    selectors: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="MATERIALS_TAOBAO_REFS_SELECTORS",
        description="页面必需选择器（键=语义名，值=正则）；auto 模式 page_changed 检测用，未命中→PLATFORM_REJECT+P-003 证据",
    )


class AlibabaConfig(BaseSettings):
    """1688 商品视频与同款图采集器参数（子代理 B2'；同构于 TaobaoRefsConfig，source_platform="1688"）。

    `MATERIALS_ALIBABA_ENABLED` / `MATERIALS_ALIBABA_FIXTURES_MODE` /
    `MATERIALS_ALIBABA_CDP_PORT` / `MATERIALS_ALIBABA_SELECTORS` 直接映射；
    populate_by_name=True 保证 `load_config(alibaba={...})` 字典覆盖可用。
    密钥纪律（P-004）：本配置只存开关/端口/选择器，不存任何凭证/Cookie。
    """

    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore", populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="MATERIALS_ALIBABA_ENABLED",
        description="1688 采集总开关（False=禁用采集，R-M2-21 风控开关）",
    )
    fixtures_mode: bool = Field(
        default=True,
        validation_alias="MATERIALS_ALIBABA_FIXTURES_MODE",
        description="True=离线样本模式（默认，读 backend/fixtures/materials/alibaba_1688.json）；False=auto 连共享浏览器解析（骨架）",
    )
    cdp_port: int = Field(
        default=9223,
        validation_alias="MATERIALS_ALIBABA_CDP_PORT",
        description="共享 Chrome CDP 端口（auto 模式用；默认 9223，以 sourcing config 为准）",
    )
    selectors: dict[str, str] = Field(
        default_factory=dict,
        validation_alias="MATERIALS_ALIBABA_SELECTORS",
        description="页面必需选择器（键=语义名，值=正则）；auto 模式 page_changed 检测用",
    )


class TaggerConfig(BaseModel):
    """素材标签化参数（子代理 B4-1；对齐 context 1.1 tags_json 口径 + R-M2-18/R-M2-19）。

    max_tags：单素材标签总数上限（去重保序后截断，默认 8）；
    tag_keyword_stopwords：标题关键词提取停用词（小表默认，命中即剔除）。
    只追加本子配置，不改既有项；测试/CLI 用 `load_config(tagger={...})` 覆盖。
    """

    max_tags: int = Field(
        default=8,
        description="标签总数上限（平台/达人/类目/标题关键词去重保序后截断）",
    )
    tag_keyword_stopwords: list[str] = Field(
        default_factory=lambda: [
            "视频", "短视频", "热门", "推荐", "分享", "好物", "种草", "开箱", "测评", "素材",
        ],
        description="标题关键词提取停用词（命中即剔除，小表默认）",
    )


class UploadConfig(BaseSettings):
    """小店素材库上传配置（子代理 B4-2；对齐 context 1.4/3.3 与 database asset_uploads DDL）。

    上传链路以「接口抽象 + fixtures mock」交付（backend/materials/integration.py）：
    真实小店素材库 API/登录态未确认前 mode 恒为 mock（默认，零外网零登录态可测），
    shop 模式为真实 provider 骨架（ShopMaterialUploadProvider 方法抛 NotImplementedError）。
    与 TikTokConfig 同模式（env_prefix=MATERIALS_ + validation_alias 显式完整环境变量名 +
    populate_by_name=True），`load_config(upload={"mode": "shop"})` 按字段名覆盖可用。
    密钥纪律（P-004）：本配置只存模式/参数占位，不存任何 API Key/Cookie/Token；
    provider_params 只允许放**环境变量名/非敏感参数**，绝不写明文凭据。
    """

    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore", populate_by_name=True)

    mode: str = Field(
        default="mock",
        validation_alias="MATERIALS_UPLOAD_MODE",
        description=(
            "上传 provider 模式：mock（默认，fixtures 离线）/ shop（真实小店素材库，"
            "待 API/登录态确认后实现，见 integration.py ShopMaterialUploadProvider）"
        ),
    )
    provider_params: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="MATERIALS_UPLOAD_PROVIDER_PARAMS",
        description=(
            "真实 provider 参数占位（JSON，环境变量覆盖），如 "
            '{"api_base_url_env": "MATERIALS_UPLOAD_API_BASE_URL", '
            '"credential_env": "MATERIALS_UPLOAD_CREDENTIAL", "timeout_seconds": 60}；'
            "只存环境变量名/非敏感参数，不存明文凭据（P-004）"
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
    board_cache: BoardCacheConfig = Field(default_factory=BoardCacheConfig)
    wechat_video: WechatVideoConfig = Field(default_factory=WechatVideoConfig)
    taobao_refs: TaobaoRefsConfig = Field(default_factory=TaobaoRefsConfig)
    alibaba: AlibabaConfig = Field(default_factory=AlibabaConfig)
    tagger: TaggerConfig = Field(default_factory=TaggerConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)


def load_config(**overrides: Any) -> MaterialsConfig:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return MaterialsConfig(**overrides)
