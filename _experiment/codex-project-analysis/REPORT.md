# 视频号小店全自动系统：静态系统分析报告

## 概述

**结论一句话：**这是一个业务规则、数据模型、离线/fixtures 验证和 M1 真实采集已较扎实的多模块原型；但上架、投放和素材库三个关键写入链路仍以 mock/骨架为主，ROI 回流也主要是可导入/导出的契约，尚不是可持续运行的生产闭环。

本次为只读静态审查：未启动服务、未执行测试、未访问外部平台。因此文档中出现的 `1179 passed / 2 skipped`、`M4 136 passed`、`ads 158 passed` 等均记为**历史验收声明**，不作为本次重新验证的结果。重要静态证据包括：`backend/requirements.txt`（SHA-256 `586884...DD60`）、`frontend/package.json`（`C20A5A...29DF`）和 `frontend/next.config.ts`（`1B6FD2...D31D`）。

## 1. 架构与分层

`03-系统总体架构设计.md:8-26` 规定采集、AI 决策、执行、调度监控四层。实际落地呈现“中间两层强、真实执行弱”的特征。

| 设计层 | 已落地证据 | 判断与缺口 |
|---|---|---|
| 采集层 | M1 的 `sourcing/collectors/browser.py:SharedBrowser` 真正调用 Playwright `connect_over_cdp`；`doudian.py`、`youmi.py`、`alibaba.py`、`taobao.py` 都有页面解析、登录/验证码探测。M2 有 `materials/downloader.py`、`normalizer.py`、`storage.py`、`TikTokDownloaderCLI`。 | M1 的罗盘、有米云、1688询价实现具备真实浏览器路径，且 v0.71~v0.83 git 记录有实采证据。M2 的淘宝/1688 引用采集默认 `fixtures_mode=True`，auto 分支在 `taobao_refs.py:_collect_auto` 抛 `NotImplementedError`；素材采集层并未整体实机化。设计中的 MinIO/OSS、PostgreSQL 热度特征表尚未见生产实现，当前默认均为 SQLite/本地存储。 |
| AI 决策层 | M1 `sourcing/scoring.py`、`pricing.py`、`compliance.py`；M3 `optimization/images/`、`copywriting/`、`review/`、`ab/`；上架门禁 `services/listing_gate.py:ListingGate`。 | 规则打分、白名单、硬拦词、图像质量/相关性闸门有代码。`WanImageProvider` 在无 `WAN_API_KEY` 时走 Pillow 占位图（`images/provider.py:196`）；DeepSeek 无 Key/失败返回规则降级（`copywriting/llm.py:10`）。P-044 的 `OpenAIImg2ImgProvider` 是真实 HTTP 实现，但静态调用点仅见若干 `backend/_gen_*.py` 临时脚本，未见其接入主 M3 流水线。 |
| 执行层 | M4 有 `listing/pipeline.py`、`state_machine.py`、`candidate_pool.py`、`platform_rejection.py`、`listing_*` 表；M5 有 `ads/settings.py`、`executor.py`、`report.py`、`stop_loss.py`、`ad_*` 表。 | M4 的 `WechatOpenApiAdapter` 默认 `mode="mock"`，其 `LIVE_API_PATHS` 九个业务路径均为空、标为待核对（`adapters/wechat_openapi.py:256-269`）。M4 UI fallback 明确禁止导入 Playwright，默认 `MockPageOps`。M5 的 `PlaywrightBrowserConnector.connect()` 直接抛 `NotImplementedError`，执行器是“全 Mock 驱动”（`ads/executor.py:110-123,323`）。故执行层的数据状态机成熟，真实写平台能力尚未交付。 |
| 调度与监控层 | M0 `foundation/repo.py:WorkflowQueue` 有幂等入队、45 分钟租约、错误分流、过期回收；`foundation/scheduler.py:WorkflowScheduler` 有 loop/熔断。M1/M2 也有独立 scheduler/downloader loop；前端/API 有 overview、jobs、workbench、kill switch。 | M0 是可运行的通用队列骨架，但生产进程托管、M4/M5 执行器注册和统一调度编排未看到。尤其 `ads/report.py:22` 明说“不做真实定时器”，只提供 `run_once/collect_missing`；设计中的“独立进程重启自愈”在各业务执行链尚未形成一个部署单元。 |

### 数据闭环核验

投放回写**已形成数据契约和单元可测部件，未形成自动运行闭环**：

- M5 `ads/feedback.py` 能构造 M5→M1 类目级交换文件、M5→M2 评估、M5→M1 拒因；M1 `sourcing/ad_backfill.py:load_exchange/apply_exchange` 能校验并落 `m1_ad_conversion_cache` / `m1_ad_conversion_ingests`；M3 `optimization/ab/ingest.py`、`retrain.py` 可摄取/重训练。
- 但 `feedback.py` 的唯一写出入口是 `write_exchange_file()`，静态搜索未见其被 M5 report scheduler 自动调用；`ad_backfill.py` 也是 CLI/显式调用入口。并且 M5 真实报表来源尚未接通，`ads/report.py` 只接受已解析的 rows。当前闭环是“文件契约 + fixtures 集成”，不是“投放报表自动回读→自动回写→下一批决策”。

## 2. M0~M6 模块评估

宪法要求的 `brief/progress/decisions/BLOCKERS/risks/context/database` 在 M0~M6 均可见；所有 `BLOCKERS.md` 当前显示“暂无”。但数据库迁移交付不均衡：M0 有 PostgreSQL 正向/回滚脚本；M1 只有 `v0.1_m1_ad_tables.sql`；M2~M6 的 `database/migrations/` 目录缺失。这与“每模块迁移脚本可演练”的治理标准不一致。

| 模块 | 声称进度（当前文件） | 代码实现位置/主要表 | 成熟度判断 | 主要风险 |
|---|---:|---|---|---|
| M0 foundation | 100% | `backend/foundation/{tables,repo,scheduler,risk,security}.py`；`workflow_jobs`、`tasks`、`logs`、`app_config`、`error_codes`、`admin_users`、`auth_sessions` | **高（基础能力）**。队列/租约/错误策略/风险引擎完整。 | 只有 M0 有 PG 迁移；调度框架尚未证明已托管、也未证明驱动 M4/M5 真执行器。 |
| M1 sourcing | `progress.md` 95%，`dashboard.md` 97% | `backend/sourcing/`；`products`、`product_library`、`source_*`、`suppliers`、`sku`、`m1_ad_conversion_*` | **中高（真实采集和业务规则）**。CDP 实采、询价、风控/断点、白名单和回写导入均存在。 | 阿里、罗盘登录态与限流是现实阻塞（P-039/P-040/P-046）；多供应商仍不稳定；进度口径冲突；核心 M1 schema 没有完整迁移。 |
| M2 materials | 100% | `backend/materials/`；`asset_items`、`asset_download_jobs`、`asset_sources`、`asset_*` | **中（仓储/去重/下载骨架）**。下载租约、MD5+phash、相关性状态、ffmpeg 规格校验较完整。 | 淘宝/1688 collector 默认 fixtures 且 auto 未实现；小店上传默认 mock、`ShopMaterialUploadProvider` 抛异常；无迁移；运行库曾有 schema 过期记录（M6 decisions 第17项）。 |
| M3 optimization | `progress.md` 96%，`dashboard.md` 95% | `backend/optimization/`；`opt_templates`、`opt_video_variants`、`opt_image_batches`、`opt_images`、`opt_evaluation_feedback` 等 | **中（离线内容流水线）**。图像质量、审核、A/B、反馈/重训练均有可测结构。 | 默认无 key 时 Pillow 占位、文案规则降级；OpenAI img2img 未见进入正式编排；素材上传 API/UI 均未实机；无迁移。 |
| M4 listing | 100% | `backend/listing/`、`backend/adapters/wechat_openapi.py`、`backend/services/listing_gate.py`；`listing_tasks`、`listing_spus`、`listing_skus`、`listing_*` | **中（状态机/门禁），低（真实上架）**。九态、幂等键、拒审修复、候选池已实现。 | OpenAPI 主链路默认 mock且路径待核；UI fallback 无真实浏览器；真实素材仅部分、资质/运费模板/官方契约尚待；无迁移。 |
| M5 ads | 75% | `backend/ads/`；`ad_campaigns`、`ad_runs`、`ad_report_snapshots`、`ad_account_states`、`ad_materials` | **中（规则/报告/反馈），低（实投）**。预算三约束、止损、报表幂等、回写契约和 M0 风控复用良好。 | CDP connector 是骨架；无真实报表定时器；账户/余额/登录/素材/实机探针未确认；无迁移。75% 比“已完成 fixtures 集成”更符合实际。 |
| M6 frontend/API | 100% | `backend/api/` + `frontend/app/(dashboard)/`、`frontend/lib/`；43 个 API 路径、9 个前端路由 | **中高（管理控制台）**。路由、取数、闸门操作、媒体预览、分页和前后端契约基本对齐。 | 默认鉴权是进程内 fixtures；cookie 未设置 Secure；部分详情 join、生产存储根和部署 CORS 仍未确认；无迁移属合理（该模块不拥有业务库），但应在 README 明确“无库”。 |

进度看板本身已有漂移：`_management/dashboard.md` 仍写 M3 95%、M1 97%、M6 “媒体端点/商品名 join 待办”和“41路径”，而当前模块进度为 M3 96%、M1 95%，`m6-frontend/decisions.md:28-30` 已记录 43 路径、M2/M3 媒体端点和 campaigns `product_name` 已交付。这削弱了 dashboard 作为实时事实源的可靠性。

## 3. 后端设计质量

### 数据库隔离、模型与迁移

- 默认 DSN 体现“一模块一库”：M0~M5 分别是 `m0-foundation.db`、`m1-sourcing.db`、`m2-materials.db`、`m3-optimization.db`、`m4-listing.db`、`m5-ads.db`（各自 `config.py`）。业务表前缀也总体落实：`asset_*`、`opt_*`、`listing_*`、`ad_*`；M0 共享表无前缀符合宪法归属。
- 两个例外需要治理说明：M1 自己拥有名为 `app_config` 的表（`sourcing/tables.py:39`），而 M0 也拥有共享 `app_config`；代码 `sourcing/pipeline.py:_load_category_whitelist` 从 M1 库读取该表。名称相同但物理库不同，易造成“共享配置到底以哪个库为准”的部署歧义。第二，`services/listing_gate.py`、`optimization/compliance.py`、`materials/tagger.py` 直接 import M1 的合规逻辑，虽未直接跨库写数据，但模块边界已是代码复用而非纯契约。
- M6 的 `Services` 六库容器会分别查询 M1/M5，例如 `m5_ads.py:132-148` 将 M5 `product_id` 批量映射到 M1 `products.title`。这是 API 聚合的合理用途，但这类跨库读取应补入 `data-audit.md` 的正式条目，并把失败降级/字段责任写成版本化契约。
- 迁移策略是最大结构性短板：多数模块靠 SQLAlchemy `create_all` 建库，无法把已有 SQLite 运行库平滑演进；M6 决策记录已经出现真实 `m2-materials.db` 缺列导致 `/api/assets` 500 的实例。M0 的 PG 脚本并未覆盖 M1~M5 表，也未见迁移演练证据。

### 幂等、断点和错误码

M0 `WorkflowQueue` 的 `enqueue/claim/complete/fail/recover_expired_leases` 和 M4 `ListingRepo.claim_task` 均有租约与重试；M2 下载任务同样有 `lease_expires_at`、`risk_control`；M1 scheduler 也实现 source/board 状态、节流与熔断。这部分设计和测试命名显示出较强的一致性。

错误码的**基础集合**已落实：M0 种子表有 `VERIFICATION_REQUIRED`、`AUTH_REQUIRED`、`RATE_LIMIT`、`TIMEOUT`、`NO_MATCH`、`PLATFORM_REJECT`、`UNEXPECTED`，并扩展 `INSUFFICIENT_REFERENCES/PAGE_CHANGED`。但各模块仍有差异：M2 把页面变化映射为 `PLATFORM_REJECT`；M5 注释/表还保留 `page_changed` 小写；API 又增加 `VALIDATION_ERROR`、`INVALID_STATE` 等局部码。差异有数据审计说明，却缺少一个可导入的、跨模块共享的枚举包和契约校验测试。

### 配置与测试

- 类目白名单、硬拦策略、评分、预算、上传模式、并发、限流等大部分在 Pydantic settings / `app_config` 中；`sourcing/pipeline.py` 已按 `category.whitelist` 读取运行时配置，`ads/config.py` 将金额统一为分。
- 仍有关键硬编码：`sourcing/cli.py:62` 有 Windows Chrome 绝对路径兜底；`ads/executor.py:54-55` 固化 CDP URL/9222；`wechat_openapi.py` 的 backoff/熔断常量未进配置。它们并非所有都是缺陷，但与“路径/阈值都配置化”的宪法不完全相符。
- 测试按模块划分细，名称覆盖模型、repo、异常、API、闸门、fixtures E2E；测试数量的历史声明较多。薄弱处集中在真实 OpenAPI、真实 Playwright、真实外部下载器、数据库迁移、生产部署、跨进程调度和真实素材/投放回流，因为代码本身明确用 mock、fixtures 或骨架替代。

### `_*.py` 卫生

名称匹配的 `backend/**/_*.py` 实有 49 个，其中 25 个是正常的 `__init__.py/__main__.py` 或 API 测试辅助；另外 24 个位于 `backend/` 根目录，是 `_probe_*`、`_gen_*`、`_draft_*`、`_verify_*`、`_collage_*` 等探测/生成脚本，且全部被 git 追踪。它们含浏览器、网络、图像写入和数据库操作痕迹，已超出一次性实验脚本的合理范围。建议迁到有 README、输入输出约定、日志与命名边界的 `tools/` 或 `_experiment/`，并把已成为生产流程的部分吸收进模块 CLI。

## 4. 前端控制台

- 路由/API 对齐度高：前端的总览、商品、素材、审核、上架、投放、工作台、异常、设置页面均使用 `frontend/lib/api.ts` 的 `apiGet/apiPost`，与 `backend/api/routers/*.py` 路径相符。当前静态可数 API 装饰器为 43 个；M2 `GET /api/assets/{id}/preview` 与 M3 `GET /api/optimization/media/{image_id}` 都存在，故旧看板的“媒体端点待办”已过时。
- 后端媒体端点采用 `FileResponse`，M2 复用 `LocalStorage._resolve`，M3 对 `resolve()` 后路径作相等比较（`m2_materials.py:224-253`、`m3_optimization.py:352-374`），对路径穿越有明确防护；生产环境的 `MATERIALS_STORAGE_DIR` 与实际落盘目录一致性仍未确认。
- 鉴权具备正向基础：全局守卫、httpOnly/SameSite=Lax session、前端 `credentials:"include"`、CORS 显式白名单。默认 `M6_CORS_ORIGINS=""` 表示仅同源，不会意外放开跨域。
- 生产缺口：默认 `M6_API_AUTH_MODE=fixtures` 使用进程内会话，重启即失效；`M0AuthStore` 可消费 `admin_users/auth_sessions`，但生产数据初始化和迁移未确认。cookie 调用没有 `secure=True`，密码校验使用快速 SHA-256 而不是含盐、慢哈希；前端默认 API 地址是 `http://127.0.0.1:8000`。这些组合适合本机联调，不宜视作生产后台认证完成。
- 详情页仍有轻微契约缺口：`GET /api/ads/campaigns` 有 `product_name`，`GET /api/ads/campaigns/{id}` 没有；列表分页已统一，但 `copywrites/logs/op-logs` 的响应信封仍不统一（M6 decisions V-L4）。

## 5. 外部集成与自动化风险

| 链路 | 静态事实 | 风险判断 |
|---|---|---|
| 微信小店 OpenAPI 上架主链 | `WechatOpenApiAdapter` 有 token、令牌桶、错误映射和 mock dispatch；默认 mock，全部业务 `LIVE_API_PATHS` 为空。 | 不是可用主链。T2/T4/T7 等官方契约、真实签名、资质/审核/链接查询均需逐接口实测。 |
| M4 Playwright 兜底 | `listing/ui_fallback.py` 明确零真实浏览器，只有 `PageOps/MockPageOps`。 | 当前不构成兜底；真实 API 接不通时也没有可执行的第二轨。 |
| M5 商品托管 | M5 settings、止损、快照解析已做；CDP 真实 connector 未实现。 | 写入投放和读回报表均未实机化，资金约束只能在模拟数据里证明。 |
| M1 浏览器采集/询价 | 真正的 CDP/Playwright collectors，P-035~P-046 记录了登录失效、URL 时效、风控熔断、低频批跑、断点续跑。 | 是最接近真实自动化的域，同时也是最脆弱的域：选择器、账号、平台联合风控、共享 profile 和 signed URL 都会使长时间无人值守不可预测。 |
| M2 外部素材 | TikTokDownloader wrapper 依赖本机 binary；淘宝/1688 collectors 默认 fixtures；M2 素材库上传 mock。 | 真实下载器安装、ffmpeg、CDP 登录态、平台选择器、上传 API/后台均是前置项。 |
| AI 图/文案 | Wan、DeepSeek、OpenAI-compatible img2img 均有 provider；无 key 时分别 Pillow/规则降级。 | 可演示“有输出”，但要区分真实生成、Pillow 占位和人工脚本批生成；主流水线需要记录 provider、model、prompt、成本、来源图、审核结论。 |

应明确登记并在启动检查中验证的外部前置项：微信小店企业主体/类目资质/运费模板/API 凭据；小店投放余额、素材库账号和真实页面选择器；淘宝、1688、罗盘、有米云的独立登录态与 CDP profile；ffmpeg/ffprobe/TikTokDownloader；M3 的 WAN/DeepSeek/IMG/Qwen-VL Key；以及生产存储目录、CORS 源和 PostgreSQL/对象存储。上述项在本次静态审查中均为**未确认**。

## 6. 数据与合规

- `data-audit.md` 的 DA-003~DA-008 与 `_management/data-exchange/m2-m3-m4-relevance-gate.json` 表明跨模块字段、评估枚举、金额/时间已做过会签。`REC-005` 的金额分 int、UTC 存储在 M4/M5/opt 表上可见；M6 API 再转换为元显示。M1 原始采集价格是 float/元语义，靠边界层处理，需继续用契约测试防止重复换算。
- 合规三态和人工闸门有实际代码：`sourcing/compliance.py` 产出 `hard_reject/candidate/manual_review`，`sourcing/gate.py` 以阈值放松，`services/listing_gate.py` 检查 `attrs_complete`、相关性、图和资质，前端 `workbench.py` 汇总六类待办。`10-风险合规与风控清单.md` 的白名单、功效/供应链词、人工复核方向基本对齐。
- 仍有两项边界：M2 的关联状态在 `ListingCandidate.material_relevance is None` 时为向后兼容而放行（`listing_gate.py:120-121`），在生产接线遗漏时会使相关性门失效；M3 `ReviewSpec.high_risk_categories` 默认空，人工抽检率默认 10%，高风险类目强制复核需要实际配置/审计验证。
- M0/M5 预算、止损、余额、全停的纯函数和 API 已实现，但 M5 没有真实执行器/余额回读，故“硬约束已上线”的表述目前仅适用于进入该规则引擎的模拟/调用路径。

## 7. 工程卫生与治理

**可借鉴的治理：**宪法、模块六件套、`pitfall-log.md`、`data-audit.md`、REC 决策和丰富 git 提交说明形成了较好的过程证据。P-039/P-040/P-046 记录了限流、登录失效、熔断和恢复节奏，且不少规则已回写到配置/脚本；这比只保留“成功”更有工程价值。

**需要修正的卫生问题：**

1. 版本纪律在最近三次提交失效：`v0.81`、`v0.82`、`v0.83` 是 commit message，但 `git tag` 最新只有 `v0.80`；HEAD `75f8b0e` 比 `origin/master` ahead 1。重大真实素材/风控改动未对应可回退 tag 与远端备份。
2. 运行资产隔离不完整。`backend/data/` 被忽略且约 4,891 文件/1.17 GB，符合运行缓存预期；但 `backend/.pytest-tmp-m2e/` 有 67 个文件约 5.4 MB 被追踪，和 `.gitignore` 的 pytest 临时目录规则冲突。根目录 `data/` 未被忽略，当前有未追踪的 listing 图片；`_management/_review_sheets/` 未追踪；`_experiment/pdd-scrape/` 有 139 文件约 69.6 MB 的脚本、截图、JS bundle 和日志，缺少保留/清理政策。
3. `backend/requirements.txt` 只覆盖当前直接 imports 的主要依赖，未锁定版本、未区分 runtime/dev、PostgreSQL 驱动被注释、真实 TikTokDownloader/ffmpeg 属外部依赖。前端把 `postcss` 强制 override 到 `8.5.10`，`next.config.ts` 又设 `eslint.ignoreDuringBuilds=true`；这些是环境规避措施，需要 CI 里独立 lint/SCA/构建门禁补位。
4. 管理文档事实漂移已影响判断（进度、路径数、媒体/商品名待办）；应把 dashboard 从人工摘要改为每次版本交付时由模块 progress/验收清单交叉核对。

## 8. 综合结论与建议

### 成熟度较高、可借鉴的部分

1. M0 队列、错误分流、租约回收、风控规则与脱敏的可测试基础能力。
2. M1 对真实 CDP 采集的运行经验：登录态检测、低频、熔断、断点、证据记录和踩坑闭环。
3. M4/M5 的状态机、幂等键、金额/时间口径和上架/投放业务门禁建模。
4. M6 的 API 聚合、前端人工闸门、分页/枚举/金额展示层，以及媒体路径保护。
5. `data-audit.md` 和契约交换文件将跨模块口径显性化的做法。

### 成熟度较低、风险较大的部分

1. M4 OpenAPI、M4 UI fallback、M5 CDP 执行和真实报表回读均未完成实机路径。
2. M2/M3 多条“自动”链路默认 fixtures/mock/Pillow/规则降级，真实产物来源不够可观测。
3. ROI 回写是交换文件能力而非自动调度的闭环，且没有真实投放数据源。
4. 除 M0 外缺数据库迁移，已出现运行库 schema 漂移实例。
5. 认证、部署、构建和运行资产治理仍偏开发态；看板与模块事实存在滞后。

### 建议（按价值排序）

| 优先级 | 建议 | 理由与涉及位置 |
|---|---|---|
| P0 | 建一个“小额真实闭环验收”而非继续扩大 mock：一个合规商品、真实素材、真实 M4 创建/审核/链接、一个 M5 托管与两次报表回读。每一步设置可暂停和人工确认。 | 这是验证五链路目标的最短证据链。先完成 `adapters/wechat_openapi.py` 的 T1~T7 和 `ads/executor.py:PlaywrightBrowserConnector`，再接 `ads/report.py`。 |
| P0 | 为 M1~M5 建立版本化迁移与实际库升级检查，先修 M2 schema 漂移。 | `database/migrations/` 只有 M0完整、M1局部；`m6-frontend/decisions.md:17` 已记录真实 M2 库缺列。每模块应有 upgrade/downgrade、空库/旧库演练及启动前 schema version 检查。 |
| P0 | 把反馈闭环接进调度：M5 快照→原子写交换物→M1/M2/M3 幂等摄取→重训练→审计事件；失败可重试。 | 当前 `ads/feedback.py` 与 `sourcing/ad_backfill.py` 只是可调用工具，`ads/report.py` 没有定时器。应让 M0 `WorkflowQueue` 编排或明确业务 scheduler。 |
| P1 | 将真实/模拟模式做成强制可观测状态：所有产物记录 `provider/mode/model/source/evidence`，UI 明示 mock、Pillow、规则降级。 | 防止把 `MockPageOps`、Pillow 占位或临时 img2img 脚本结果误看成已上线能力；涉及 M2 upload、M3 providers、M4 adapter、M5 executor/API。 |
| P1 | 固化浏览器运行策略：每平台独立 profile、登录探活、全局速率预算、连续失败熔断、批次恢复记录和人工接管通知。 | P-039/P-040/P-046 已证明共享阿里登录态与高频采集的脆弱性；涉及 `sourcing/config.py`、`collectors/browser.py`、未来 M4/M5 CDP 适配器。 |
| P1 | 生产化 M6 鉴权与部署配置。 | 迁移到 M0 持久会话，使用慢哈希密码、HTTPS `Secure` cookie、显式生产 CORS、账号初始化/轮换和审计；涉及 `api/auth.py`、`api/config.py`、M0 auth 表迁移。 |
| P2 | 清理实验/临时/测试产物并补 CI。 | 将 24 个根级探索脚本、69.6 MB experiment、被追踪 pytest 临时文件分层；CI 独立执行锁定依赖安装、pytest、vitest、tsc、eslint 与迁移检查。涉及 `.gitignore`、`backend/requirements.txt`、`frontend/package.json`、管理目录。 |
| P2 | 以一次版本化交付同步 dashboard、progress、tags 和远端。 | 先为 v0.81~v0.83 补可追溯标签/发布说明并推送，之后以验收清单更新 `_management/dashboard.md`；避免目前 95/96/97%、41/43 路径、待办状态相互矛盾。 |

