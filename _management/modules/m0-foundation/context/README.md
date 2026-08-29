# M0 基座与数据治理 · 上下文库（context）

> 模块的持久记忆，跨会话不丢失。任何代理重启后先读本目录。
> 铁律：本目录只写字段名与约定，**绝不写明文密钥/Token/Cookie 值**（宪法第 4 节）。

## 数据字典（骨架 v0.1，口径已按总控裁决 REC-005 / DA-001 修订）

### 全局字段口径（全系统强制一致，M4/M5 已按此实现）

| 约定项 | 口径 | 说明 |
|---|---|---|
| 主键 ID | 自增整数（Integer PK） | 业务键（如 fingerprint）另建唯一索引 |
| 金额 | **分（人民币），int**（整数存储） | 与微信小店 channels API、投放后台口径一致；展示层由前端/报表转「元」；JSON 内金额同样按分 int（总控裁决 REC-005，见 logs/data-audit.md DA-001） |
| 时间 | **UTC（ISO8601 带时区）存储** | 时间戳字段名一律后缀 `_at`；展示层转 UTC+8（东八区）；SQLite 开发库存 aware UTC（近似 ISO8601），PostgreSQL 用 TIMESTAMPTZ（真带时区）（总控裁决 REC-005 / DA-001） |
| 指纹 | SHA-256 hex（64 位小写） | `product_fingerprint` / 素材指纹共用此规格 |
| 枚举值 | 小写下划线（snake_case） | 见 `error_code` / `status` 枚举 |
| 布尔 | 0/1（Boolean） | — |
| JSON 字段 | JSON 列存证据/明细 | 只存可序列化数据，不存活对象（宪法 5 节） |

### M0 核心实体（字段骨架，DDL 见 `../database/README.md`）

- `workflow_jobs`：任务队列主表（stage/status/error_code/租约/幂等键）
- `tasks`：任务明细/子任务（与迁移包核对后定稿）
- `logs`：操作留痕（脱敏）
- `app_config`：键值+JSON 配置（类目白名单/权重/预算上限等）
- `error_codes`：错误码 → 重试策略映射（唯一权威）

## 共享表清单与归属（09 文档表清单 + 归属核对）

| 表 | 归属 | 读写 | 备注 |
|---|---|---|---|
| `workflow_jobs` | M0 | M0 写，全员只读 | 任务队列（stage/status/error_code/租约） |
| `tasks` | M0 | M0 写，全员只读 | 与迁移包 DDL 核对后定稿 |
| `logs` | M0 | 全员经 M0 工具函数写，M0 管理 | 敏感字段写入前必须 `_redact_text` |
| `app_config` | M0 | M0 写，全员只读 | 键值+JSON；类目白名单/权重/预算上限等 |
| `error_codes` | M0 | M0 写，全员只读 | 错误码→重试策略映射 |
| `products`/`product_library`/`product_fingerprint_claims`/`source_*`/`suppliers`/`sku` | M1 | M1 | 选品域（现 sourcing 库已建） |
| `asset_*` | M2 | M2 | 素材库（视频/图片，双去重） |
| `image_batches`/`image_assets`/`category_listing_memory` | M3 | M3 | 图片/视频优化域 |
| 上架域（`upload_history`/`wechat_upload_logs` 等） | M4 | M4 | 待迁移包核对后归属 |
| `ad_campaigns`/`ad_runs`/`ad_report_snapshots`/`ad_account_states` | M5 | M5 | 投放域 |
| `ai_generation_logs` | M3（AI 调用方） | M3 | AI 留痕 |

## 外部契约（摘要）

| 对象 | 契约要点 | 来源文档 |
|---|---|---|
| 微信小店 OpenAPI（channels） | 自写薄封装：SHA256 签名 + 时间戳窗口 + 限额队列；上架主链路 | 01/03 |
| DeepSeek / Kimi / Wan | AI 决策层（文案/规划/生图）；密钥仅环境变量 | 03/11 |
| TikTokDownloader / 下载 API 中台 | 素材采集；视频号支持弱，需自研补层 | 01 |
| 浏览器自动化 | Playwright + 共享 Chrome（CDP）；有米云独立端口 | 03/09 |

## 跨模块数据契约（M0 视角）

| 方向 | 数据 | 载体 |
|---|---|---|
| M0 → M1~M5 | 队列状态/错误码/重试策略/全局配置 | `workflow_jobs`/`error_codes`/`app_config`（只读） |
| M0 → 总控 | 全局风控状态/预算消耗/一键全停信号 | 风控快照 JSON（`_management/data-exchange/`） |
| M1~M5 → M0 | 任务入队请求/业务事件/错误上报 | 入队 API / data-exchange JSON（宪法 5 节流程） |
| M0 ↔ 各模块 | 字段口径核对（金额/时间/枚举/ID） | `data-audit.md` 登记 + 会签 |

## 调度与运行（A2 调度器进程化，v0.3）

- **设计对齐**：继承 `backend/sourcing/scheduler.py` 基线模式（02 文档「最值得抄」），M0 通用化——职责 = 通用队列驱动（轮询领取 → 分派 Worker → 回写 complete/fail + 节流/熔断），业务执行由注入的 `Worker` 实现（各模块提供；CLI 默认 `LoggingWorker` 仅留痕演示）。选品源级账本/降频（实时榜空转降日轮询）属业务调度（sourcing），M0 不实现。
- **独立进程方案**：`python -m foundation scheduler --loop [--interval N]`（独立进程，生产建议 systemd/后台托管拉起，09 文档第三节）；`--once` 单轮调试；`--db-url` 覆盖 DSN（默认 `M0_DB_URL`）。
- **断点自愈**：`resume_on_startup()` 启动即恢复租约过期的 running job 为 pending（`recover_expired_leases`，45min 过期回收），进程重启自愈（09 文档 recover_after_process_restart）。
- **节流/熔断**（09 文档第三节）：stage 级内存态——连续失败 ≥2 → 熔断暂停该 stage 至 `throttle_base_seconds × 2^level`（0~4 级，×1/2/4/8/16），冷却后自动恢复；成功后失败计数清零。全 stage 暂停 → 本轮跳过。
- **失败隔离**：单 job 失败/等待人工（waiting_verification/waiting_login）不阻塞其他 stage/job 排队（复用 `WorkflowQueue.claim`）。
- **配置**（`M0_SCHEDULER_*` 前缀，`SchedulerConfig`）：`M0_SCHEDULER_POLL_INTERVAL_SECONDS`（30）/`M0_SCHEDULER_MAX_CLAIM_PER_ROUND`（10）/`M0_SCHEDULER_THROTTLE_BASE_SECONDS`（30）/`M0_SCHEDULER_THROTTLE_LEVELS`（5）/`M0_SCHEDULER_CIRCUIT_BREAKER_FAILURES`（2）。
- **代码位置**：`backend/foundation/scheduler.py`（Worker/LoggingWorker/WorkflowScheduler/default_worker_id）、`backend/foundation/__main__.py`（init-db/scheduler CLI）、`backend/tests/test_foundation_scheduler.py`（12 例）。

## 风控与合规（A3 风控规则引擎，v0.4）

- **口径**：与 M5 `backend/ads/stop_loss.py` 同口径（总控裁决：共享规则以基座为准，M5 引用由总控协调）——金额一律「分」int、ROI 浮点倍数、枚举英文、纯函数/数据驱动（dict/ORM 兼容 `_get`）、结构化 `RuleVerdict`/`BudgetVerdict`/`EngineResult`。
- **四层防线**（10 文档第一节）：S7 预算三重硬约束 `check_budget_triple`（单笔/日总/计划总同时生效，任一超限即停，0=不限，多超限取首个）；自动止损 S1 `rule_s1_stop_loss`（花费>0 且 0 成交且曝光≥500 → 暂停+标签）与 S3 `rule_s3_roi_floor`（连续 2 周期 ROI<目标×80% → 降档）；S5 `rule_s5_balance`（余额<¥100 → halt_new）；S8 `kill_switch_enabled`（最高优先级，未识别字符串视为关防误触发）。
- **引擎**：`RiskEngine.evaluate(campaign, snapshots, *, account_balance_fen, ...)`——S8 短路（只返回 S8/halt_all）→ S7（有预算上下文）→ S5（halt_all）→ S1 → S3；halt_all = S8|S5（对齐 M5 语义，预算超限不触发 halt_all 仅停花钱动作）。
- **边界**：S2/S4/S6（诊断优化记录/补贴统计/活跃上限）为投放业务专属规则，留在 M5 不清除。
- **代码位置**：`backend/foundation/risk.py`（RiskEngine/rule_s1~s5/check_budget_triple/kill_switch_enabled/normalize_diagnosis）、`backend/tests/test_foundation_risk.py`（26 例）；M0 环境变量 `M0_KILL_SWITCH` + `app_config` 键（`risk.kill_switch`）为全停入口（A4 工程基座统一 .env.example）。

## 环境事实

- **运行时**：Python 3.12、FastAPI、SQLAlchemy 2.0、Playwright、ffmpeg（11 文档前置清单）
- **CDP 端口**：商机中心/1688/淘宝 → 共享浏览器 9223（历史 9222，以配置为准）；有米云 → 独立 9555；抖店罗盘 → 共享 9223（见 `backend/sourcing/config.py`）
- **pytest 约定（P-001/P-011，宪法第 12 节）**：M0 专属命令 `python -m pytest tests -q --basetemp=".pytest-tmp-m0"`——**禁止共用 `.pytest-tmp`**（多代理并行共享 basetemp 会互相清理，导致间歇性 PermissionError/WinError 5，串行复跑会掩盖真实失败）；全量回归由总控统一执行（总控用 `.pytest-tmp-verify`）；P-001 本机默认临时目录 WinError 5 无权限
- **数据库**：开发 SQLite（`backend/data/db/<模块>.db`，不入 git）；生产 PostgreSQL（`POSTGRES_DSN`）
- **迁移包**：`app.sanitized.db` → `backend/app.db`（498 products / 521 product_library / 939 tasks / 657 image_assets / 40 workflow_jobs），由总控执行，落地后 M0 核对 `tasks`/`workflow_jobs` DDL

### 环境变量注册表（只列名字，不列值；明文值禁止写入任何文件）

| 变量 | 用途 | 归属 |
|---|---|---|
| `SOURCING_DB_URL` / `SOURCING_CHROME_PATH` / `SOURCING_LOG_LEVEL` | M1 选品模块 | M1 |
| `M0_DB_URL` / `M0_LOG_LEVEL` | M0 基座库连接/日志 | M0 |
| `M0_LEASE_MINUTES` | 队列租约时长（默认 45） | M0 |
| `M0_SCHEDULER_POLL_INTERVAL_SECONDS` / `M0_SCHEDULER_MAX_CLAIM_PER_ROUND` / `M0_SCHEDULER_THROTTLE_BASE_SECONDS` / `M0_SCHEDULER_THROTTLE_LEVELS` / `M0_SCHEDULER_CIRCUIT_BREAKER_FAILURES` | 调度器配置（A2） | M0 |
| `M0_KILL_SWITCH` | 一键全停总开关 | M0 |
| `BUDGET_SINGLE_MAX` / `BUDGET_DAILY_MAX` / `BUDGET_PLAN_MAX` | 预算三重硬约束 | M0 |
| `AD_BALANCE_MIN` | 投放余额阈值（默认 100） | M0 |
| `DEEPSEEK_API_KEY` / `KIMI_API_KEY` / `WAN_API_KEY` | AI 密钥 | M3 使用，M0 管脱敏 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 小店 OpenAPI | M4 使用，M0 管脱敏 |
| `REDIS_URL` / `POSTGRES_DSN` / `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | 生产存储 | M0 |
| `CHROME_PATH` / `CDP_PORT_SHARED` / `CDP_PORT_YOUMI` | 浏览器路径/CDP 端口 | M0 注册，各模块读取 |
