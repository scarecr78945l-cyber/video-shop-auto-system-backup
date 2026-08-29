"""选品模块配置（pydantic-settings，环境变量前缀 SOURCING_）。

所有偏好均可配置化，对应方案文档 04 第四节：类目白名单、打分权重、
价格带权重、来源榜单权重、历史类目成本等。运行时优先读 app_config 表
（`AppConfigRepo`），未配置时回落到此处默认值。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CATEGORY_WHITELIST: list[str] = [
    "家居日用",
    "厨房用品",
    "宠物用品",
    "收纳整理",
    "个护清洁",
    "服饰配件",
    "数码配件",
    "办公文具",
    "户外运动",
]


class BoardSpec(BaseModel):
    """一个榜单/页面的账本与调度规格。"""

    name: str
    kind: str = "static"  # static=日扫一次 | realtime=小时轮询（空转 24 次降日）
    url_template: str = ""
    selectors: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class CollectorConfig(BaseModel):
    """各来源采集器配置：登录态、选择器、开关、独立浏览器端口。"""

    enabled: bool = True
    boards: list[BoardSpec] = Field(default_factory=list)
    # 选择器配置化（R-23/A1）：值与采集器 DEFAULT_SELECTORS 一致（columns 除外，
    # youmi/doudian 的 columns 刻意不迁入 config → 走 _locate_columns 动态表头定位，见 A4）。
    # 值类型为 Any：字符串选择器之外，columns 等结构化映射（dict[str, int]）也允许。
    selectors: dict[str, Any] = Field(default_factory=dict)
    # 榜单 URL 日期回看天数（有米云 {start_date}/{end_date} 占位符，A2）：
    # end=当天，start=当天-lookback_days；无占位符模板不受影响。
    lookback_days: int = 7
    pagination: dict[str, Any] = Field(default_factory=dict)
    cdp_port: int = 9222  # 浏览器 CDP 端口（Playwright connect_over_cdp）；各来源可独立端口隔离登录态
    chrome_path: str = ""  # 便携 Chrome 路径，空则用系统默认
    profile_dir: str = ""  # 独立 user-data-dir（登录态隔离）；空=共享浏览器

    @property
    def board_map(self) -> dict[str, BoardSpec]:
        return {b.name: b for b in self.boards}


class ScoringConfig(BaseModel):
    """五维打分权重。

    基础四维满分和 = 100；投放转化维度满分 = ad_conversion_weight（默认 10），
    无数据时不生效，权重从其他四维折算（和仍为 100），
    对应里程碑 M2「数据结构先行，无数据时权重=0 不生效」。
    """

    dimension_max: dict[str, float] = Field(
        default_factory=lambda: {
            "trend": 35.0,        # 热度趋势
            "profit": 30.0,       # 利润率
            "after_sale": 20.0,   # 售后风险
            "supply": 15.0,       # 供给稳定
        }
    )
    ad_conversion_weight: float = 10.0  # 投放转化（新增，从其他维折算）
    # 各维度明细档位（详见 scoring.py，这里只放可调阈值）
    trend_rank_bands: list[tuple[int, int, float]] = Field(
        default_factory=lambda: [(3, 25.0), (10, 20.0), (30, 15.0), (100, 8.0)]
    )  # (排名上限, 得分)
    trend_sales_bands: list[tuple[int, float]] = Field(
        default_factory=lambda: [(10000, 8.0), (3000, 6.0), (1000, 4.0), (300, 2.0)]
    )
    trend_cross_bonus: float = 2.0
    profit_margin_bands: list[tuple[float, float]] = Field(
        default_factory=lambda: [
            (0.60, 30.0),
            (0.45, 25.0),
            (0.35, 18.0),
            (0.25, 12.0),
            (0.15, 6.0),
        ]
    )
    after_sale_bands: list[tuple[float, float]] = Field(
        default_factory=lambda: [(0.03, 20.0), (0.08, 16.0), (0.15, 8.0)]
    )
    after_sale_unknown: float = 10.0
    supply_bands: list[tuple[int, float]] = Field(
        default_factory=lambda: [(10, 15.0), (5, 12.0), (3, 8.0), (2, 5.0)]
    )
    ad_roi_bands: list[tuple[float, float]] = Field(
        default_factory=lambda: [(3.0, 10.0), (2.0, 8.0), (1.5, 6.0), (1.0, 4.0)]
    )
    ad_roi_below: float = 2.0
    ad_data_max_age_days: float = 7.0  # 投放转化数据新鲜度阈值：generated_at 超过 N 天视为无数据（R-14 / C-2）
    top_n: int = 50  # 每日入池数量


class PricingConfig(BaseModel):
    """定价阶梯：成本 → 建议售价（复用半成品 pricing.py 口径）。"""

    ladder: list[tuple[float, float]] = Field(
        default_factory=lambda: [(3.0, 9.0), (5.0, 19.9), (10.0, 29.9), (15.0, 49.9)]
    )
    default_markup: float = 2.5  # 超出阶梯上限时的兜底倍率


class DedupConfig(BaseModel):
    """去重阈值。"""

    phash_hamming_threshold: int = 8  # 汉明距离 ≤8 视为同图
    attribute_hash_salt: str = "sourcing.v1"


class SchedulerConfig(BaseModel):
    """调度器：账本/节流/熔断。"""

    throttle_levels: int = 5  # 0~4 级
    throttle_base_seconds: float = 30.0  # 间隔 ×1/2/4/8/16
    circuit_breaker_failures: int = 2  # 连续失败 N 次 → risk_control
    empty_runs_before_downgrade: int = 24  # 实时榜连续空转 N 次 → 降日轮询
    realtime_interval_seconds: float = 3600.0
    static_interval_seconds: float = 86400.0
    claim_lease_minutes: int = 45
    max_items_per_run: int = 200
    max_daily_candidates: int = 2000


class SourcingConfig(BaseSettings):
    """总配置。环境变量：SOURCING_DB_URL / SOURCING_LOG_LEVEL 等。"""

    model_config = SettingsConfigDict(
        env_prefix="SOURCING_", env_file=".env", extra="ignore"
    )

    # REC-007：默认开发库从 sqlite:///sourcing.db（backend 相对路径）切到
    # sqlite:///data/db/m1-sourcing.db（即 backend/data/db/m1-sourcing.db，一模块一库）。
    # 旧 sourcing.db 无数据不迁移，新库为唯一正式开发库；SOURCING_DB_URL 仍可覆盖。
    db_url: str = Field(
        default="sqlite:///data/db/m1-sourcing.db",
        description=(
            "SQLAlchemy DSN；开发默认 SQLite（backend/data/db/m1-sourcing.db，不入 git），"
            "生产切 postgresql+psycopg2://..."
        ),
    )
    log_level: str = "INFO"
    data_dir: Path = Field(default_factory=lambda: Path("data"))
    fixtures_dir: Path = Field(default_factory=lambda: Path("fixtures"))
    # 系统/便携 Chrome 可执行文件路径（launch-browsers 启动独立浏览器用）
    chrome_path: str = ""

    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)

    category_whitelist: list[str] = Field(default_factory=lambda: list(DEFAULT_CATEGORY_WHITELIST))
    category_whitelist_enabled: bool = True  # 关掉=放开全类目（人工闸门把关）

    # REC-迁移-01（C1 鞋服/包类硬拦）：旧系统 SOURCING_HARD_BLOCK_POLICY 词表
    # （apparel_terms 245 + safe_apparel_context_terms 豁免 / bag_terms 80 + safe_bag_context_terms 豁免）
    # 以 JSON 配置挂载（sourcing/data/hard_block_policy.json），compliance.py 读取；
    # 命中鞋服/包词且不在安全上下文 → hard_reject（旧系统「鞋服/包类必淘汰」语义）。
    hard_block_policy_path: Path = Field(
        default_factory=lambda: Path(__file__).parent / "data" / "hard_block_policy.json"
    )
    hard_block_policy_enabled: bool = True  # 总开关（可配置化放松）

    # 选品采集三源：
    #   除有米云外，全部走「新的共享浏览器」（launch-browsers 启动，CDP 9223），
    #   商机中心/抖店罗盘/1688/淘宝 均登录在同一个共享浏览器。
    #   有米云走独立特制浏览器（便携 Chrome，CDP 9555，登录态隔离）。
    opportunities: CollectorConfig = Field(
        default_factory=lambda: CollectorConfig(
            cdp_port=9223,
            profile_dir="shared",
            boards=[
                BoardSpec(
                    name="机会品",
                    url_template="https://store.weixin.qq.com/shop/goods/opprotunity",
                )
            ],
            # A1：与 opportunities.py DEFAULT_SELECTORS 逐键一致（含 columns 结构化映射）
            selectors={
                "home_url": "https://store.weixin.qq.com/shop/goods/opprotunity",
                "row": "table tbody tr",
                "columns": {"title": 0, "source": 1, "status": 2},
                "login_gate": "[class*='login']",
                "verify_gate": "[class*='captcha'], [class*='verify']",
            },
        )
    )  # 视频号商机中心（微信小店后台，共享浏览器）
    youmi: CollectorConfig = Field(
        default_factory=lambda: CollectorConfig(
            cdp_port=9555,
            profile_dir="youmi-portable",
            boards=[
                BoardSpec(
                    name="商品榜",
                    # 不带 tableSelect → 默认视图（含「商品」列），避免用户隐藏列导致取不到标题
                    # A2：日期参数占位符化，导航时按 lookback_days 动态生成（end=当天，start=当天-7）
                    url_template=(
                        "https://console.youshu.youcloud.com/goods/sale"
                        "?site_id=10502&startDate={start_date}&endDate={end_date}"
                    ),
                )
            ],
            # A1：与 youmi.py DEFAULT_SELECTORS 一致，但刻意不含 columns（A4：留空走动态表头定位）
            selectors={
                "home_url": "https://console.youshu.youcloud.com/",
                "row": ".el-table__body-wrapper tr",
                "next_page": ".el-pagination .btn-next, .el-pagination__next",
                "login_gate": ".login-modal, [class*='login']",
                "verify_gate": ".captcha, [class*='verify']",
            },
        )
    )  # 有米云（独立特制浏览器 console.youshu.youcloud.com）
    doudian: CollectorConfig = Field(
        default_factory=lambda: CollectorConfig(
            cdp_port=9223,
            profile_dir="shared",
            boards=[
                BoardSpec(
                    name="商品榜",
                    url_template="https://compass.jinritemai.com/shop/chance/rank-product",
                ),
                # 飙升榜：URL 待登录态就绪后从页面地址栏回填（A3，见 selector-log 第 6 节）
                BoardSpec(name="飙升榜", url_template=""),
                # P2-6 旧系统罗盘榜单目录补全（douyin_compass_board_catalog.py，2026-08 旧系统现场）：
                # 旧系统为「3 类目(运动户外/个护家清/智能家居) × 3 时间窗(近1天/近7天/近30天) × 3 静态榜
                # + 1 实时榜」共 30 个组合，且均为 rank-product 同页内 tab 切换（URL 不区分榜单）。
                # 本处仅登记 4 个榜单名（不展开类目×时间窗矩阵），全部 disabled：
                # ① 不参与采集/调度（base.boards 过滤 enabled，见 scheduler/pipeline）；
                # ② url_template 留空 → 采集器 URL 映射按非空过滤，不干扰商品榜/飙升榜；
                # ③ 启用前置：罗盘页 tab 实测 + 选择器校准（R-23）+ 类目/时间窗切换参数化。
                BoardSpec(name="商品卡榜", url_template="", kind="static", enabled=False),
                BoardSpec(name="短视频榜", url_template="", kind="static", enabled=False),
                BoardSpec(name="同行低退榜", url_template="", kind="static", enabled=False),
                BoardSpec(
                    name="实时爆品挖掘榜",
                    url_template="",
                    kind="realtime",
                    enabled=False,
                ),
            ],
            # A1：与 doudian.py DEFAULT_SELECTORS 一致，但刻意不含 columns（A4：留空走动态表头定位）
            selectors={
                "home_url": "https://compass.jinritemai.com/shop/chance/rank-product",
                "row": ".aurora-table-tbody tr",
                "next_page": ".aurora-pagination-next, [class*='pagination'] [class*='next']",
                "login_gate": ".login, [class*='login']",
                "verify_gate": ".captcha, [class*='verify'], [class*='captcha']",
            },
        )
    )  # 抖店电商罗盘（共享浏览器）

    # P2-6 考古加（kaogujia）—— 第四源备胎（REC-006：D-1 裁决，考古加降级可选第四源）。
    # 榜单目录来自旧系统 kaogujia_board_catalog.py（2026-08 现场，配套 playwright_kaogujia.py 32KB 分页逻辑）。
    # 状态：**仅配置登记，未启用**（enabled=False → 不参与采集/调度）：
    #   ① 采集器尚未实现（新系统无 kaogujia collector）；
    #   ② 启用前置：实现采集器 + 登录态（独立 profile）+ 选择器校准（R-23，selectors 留空=待校准）；
    #   ③ 旧系统采集节奏 interval_minutes=120（约 2h 级），本处按风控纪律保守登记 static（日扫，R-50），
    #      启用时由总控按实测重新裁决 kind。
    kaogujia: CollectorConfig = Field(
        default_factory=lambda: CollectorConfig(
            cdp_port=9223,
            profile_dir="shared",  # 待实测后按登录态隔离需求校准（备胎未启用，端口/profile 均待裁决）
            enabled=False,
            boards=[
                BoardSpec(
                    name="实时销量榜",
                    url_template="https://www.kaogujia.com/liveTopList/douyinProductList/realSales",
                    kind="static",
                    enabled=False,
                ),
                BoardSpec(
                    name="视频热推荐榜",
                    url_template="https://www.kaogujia.com/liveTopList/douyinProductList/videoRecommendList",
                    kind="static",
                    enabled=False,
                ),
                BoardSpec(
                    name="商品热销榜",
                    url_template="https://www.kaogujia.com/liveTopList/douyinProductList/hotSales",
                    kind="static",
                    enabled=False,
                ),
                BoardSpec(
                    name="商品数据大盘",
                    url_template="https://www.kaogujia.com/productMarket",
                    kind="static",
                    enabled=False,
                ),
                BoardSpec(
                    name="往年爆款",
                    url_template="https://www.kaogujia.com/historyBestseller",
                    kind="static",
                    enabled=False,
                ),
            ],
            # selectors 留空：采集器未实现，启用时按 DEFAULT_SELECTORS 约定 + inspect-page 校准（R-23）
            selectors={},
        )
    )  # 考古加（第四源备胎，未启用）

    # 询价/素材源（共享浏览器）
    alibaba: CollectorConfig = Field(
        default_factory=lambda: CollectorConfig(
            cdp_port=9223,
            profile_dir="shared",
            # A1：与 alibaba.py DEFAULT_SELECTORS 逐键一致
            selectors={
                "search_input": "input[placeholder*='搜索'], input[class*='search']",
                "search_btn": "button[class*='search'], .search-btn",
                "image_upload": "input[type='file'], .upload-btn",
                "result_row": ".card-item, [class*='offer'] li",
                "result_title": ".title, [class*='title']",
                "order_price": ".order-price, .price-box, [class*='price']",
                "supplier_name": ".company-name, [class*='company']",
                "confirm_btn": ".confirm-btn, button:has-text('确认')",
                "login_gate": ".login-modal, [class*='login']",
                "verify_gate": ".captcha, [class*='verify']",
            },
        )
    )
    taobao: CollectorConfig = Field(
        default_factory=lambda: CollectorConfig(
            cdp_port=9223,
            profile_dir="shared",
            # A1：与 taobao.py DEFAULT_SELECTORS 逐键一致
            selectors={
                "search_input": "input[placeholder*='搜索'], input[class*='search']",
                "search_btn": "button[class*='search'], .search-btn",
                "result_row": ".items .item, [class*='item']",
                "result_title": ".title, [class*='title']",
                "image": "img",
                "next_page": ".next, [class*='next']",
                "login_gate": ".login-modal, [class*='login']",
                "verify_gate": ".captcha, [class*='verify']",
            },
        )
    )

    # 广告转化数据（回流）：按类目聚合的 ROI/成交额（AdReportSnapshot 汇总来源）
    ad_conversion_by_category: dict[str, dict[str, float]] = Field(default_factory=dict)

    # M5 → M1 投放转化回写交换文件路径（契约 C-2：_management/data-exchange/m5-ad-conversion.json）。
    # 默认 "" = 未配置：此时 ad-sync 必须 --file 显式指定；配置后 ad-sync 可缺省读此路径。
    ad_exchange_file: str = ""


def load_config(**overrides: Any) -> SourcingConfig:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return SourcingConfig(**overrides)
