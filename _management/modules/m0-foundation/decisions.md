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
