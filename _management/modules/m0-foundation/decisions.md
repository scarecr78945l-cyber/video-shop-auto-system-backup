# M0 基座与数据治理 · 决策记录（decisions）

> 记录本模块关键技术决策：决策内容、理由、备选方案、日期、决策人。文档与代码不一致时必须记入此处（宪法第 8 节）。

| 日期 | 决策 | 理由 | 备选方案 | 决策人 |
|---|---|---|---|---|
| 2026-08-28 | 共享基座表（workflow_jobs/tasks/logs/app_config/error_codes）无前缀、归属 M0，其他模块表带各自前缀（m1_/asset_/image_/ad_…），共享表全员只读 | 宪法第 4 节「表名前缀 + 共享表只读」；避免业务模块表与基座表冲突 | 全表统一前缀 base_ | M0 总工 |
| 2026-08-28 | `workflow_jobs` 幂等键采用 `(product_id, stage, generation_version)` 唯一约束 | 09 文档明确；防并发重复入队/重复上架 | 仅 (product_id, stage) | M0 总工 |
| 2026-08-28 | 错误码表独立建表 `error_codes`（code/retryable/backoff_seconds/action），不并入 `app_config` JSON | 重试策略需结构化查询与种子数据，独立表可被调度器/队列直接 JOIN 引用；错误码是全系统唯一权威（宪法第 8 节） | 全部放 app_config 键值 | M0 总工 |
| 2026-08-28 | 金额单位统一为「元」Float，平台 API 以「分」计处由适配层换算（字段名注明 `*_fen`） | 与现有 pricing.py/sourcing 口径一致，最小改动；跨模块报表口径统一 | 全系统改用「分」整数 | M0 总工 |
| 2026-08-28 | `tasks`/`workflow_jobs` 以迁移包实际 DDL 为准：首轮只规划骨架，迁移包（`app.sanitized.db`→`backend/app.db`）落地后立即核对修订 | 当前 backend 树无 workflow 表（迁移包有 40 条 workflow_jobs/939 tasks），避免凭空设计造成迁移冲突 | 完全重设计表结构 | M0 总工 |
| 2026-08-28 | pytest 一律 `--basetemp=".pytest-tmp"`，已更新 `backend/README.md` 测试命令 | P-001 本地临时目录 WinError 5；防复发措施需在文档落实 | 修改系统 TEMP 权限 | M0 总工 |
| 2026-08-28 | 采纳总控裁决 REC-005（DA-001）：金额一律「分」int 存储（含 JSON 内金额），展示层转元；时间一律 UTC（ISO8601 带时区）存储、时间戳字段后缀 `_at`、展示层转 UTC+8 | 与微信 channels API/投放后台口径一致，消除 M0 初稿（元/Float）与 M4/M5（分/int）冲突；M0 修订 context 与 database 文档，logs.ts→logs.created_at | 维持「元」并要求 M4/M5 改 | M0 总工（裁决：总控） |
| 2026-08-28 | 时间列用 `AwareUTCDateTime`（TypeDecorator：SQLite 存 naive UTC、读回补 tzinfo 强制 aware UTC；PostgreSQL TIMESTAMPTZ 原生带时区） | SQLite 无时区类型导致 naive/aware 混用（TypeError: can't subtract offset-naive and offset-aware）；治本方案保证 Python 层永远 aware UTC（REC-005） | 测试层统一转 aware（掩盖问题） | M0 总工 |
| 2026-08-28 | `retry_after` 为总控第 1 步指定字段名（语义=下次可重试时间），**命名例外**：不满足 REC-005「时间戳 _at 后缀」规则（以 `ter` 结尾非 `_at`），保留总控命名，测试单独验证其存在性（test_retry_after_retry_time_field） | 总控指示优先；语义清晰（"在此之后可重试"）；改名违背已批准的 DDL | 改名 retry_at / retry_after_at | M0 总工（字段名裁决：总控） |
| 2026-08-28 | 测试用 SQLite 内存库（`sqlite:///:memory:`）时 `db.py` 用 `StaticPool` 固定单连接 | 默认 QueuePool 下内存库每连接独立、跨 session 数据不可见；StaticPool 保证建表/写入/读取跨 session 一致 | 测试改 tmp_path 文件库 | M0 总工 |
