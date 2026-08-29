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
| `M0_SCHEDULER_INTERVAL` | 调度器轮询间隔 | M0 |
| `M0_KILL_SWITCH` | 一键全停总开关 | M0 |
| `BUDGET_SINGLE_MAX` / `BUDGET_DAILY_MAX` / `BUDGET_PLAN_MAX` | 预算三重硬约束 | M0 |
| `AD_BALANCE_MIN` | 投放余额阈值（默认 100） | M0 |
| `DEEPSEEK_API_KEY` / `KIMI_API_KEY` / `WAN_API_KEY` | AI 密钥 | M3 使用，M0 管脱敏 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 小店 OpenAPI | M4 使用，M0 管脱敏 |
| `REDIS_URL` / `POSTGRES_DSN` / `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | 生产存储 | M0 |
| `CHROME_PATH` / `CDP_PORT_SHARED` / `CDP_PORT_YOUMI` | 浏览器路径/CDP 端口 | M0 注册，各模块读取 |
