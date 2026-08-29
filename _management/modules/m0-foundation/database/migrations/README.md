# M0 基座 · SQLite → PostgreSQL 迁移（A5）

> 迁移脚本目录（对齐 database/README.md「三、迁移计划」与 M1 migrations 目录模式）。
> 幂等：`0001_create_base_tables.pg.sql` 可重复执行（IF NOT EXISTS + ON CONFLICT DO NOTHING）。

## 一、迁移计划（四阶段）

| 阶段 | 内容 | 载体 |
|---|---|---|
| 1 兼容期 | SQLAlchemy 方言无关 DDL + SQLite 开发（现状） | `backend/foundation/tables.py`（ORM 五表） |
| 2 迁移脚本 | PG 方言 DDL + 种子（本目录）；数据复制（SQLite→PG） | `0001_create_base_tables.pg.sql` + 数据复制（见下） |
| 3 切换 | `M0_DB_URL=postgresql+psycopg2://...`（或 `POSTGRES_DSN`）环境变量切换；启动自检 | 环境变量 + `python -m foundation init-db` 冒烟 |
| 4 校验 | 行数/唯一约束/索引核对 + 回归测试 | 校验 SQL（见下） |

## 二、方言差异清单（SQLite → PostgreSQL）

| SQLite | PostgreSQL | 涉及 |
|---|---|---|
| `JSON` | `JSONB` | workflow_jobs.payload/evidence_json、tasks.payload/evidence_json、logs.evidence、app_config.value |
| `DATETIME` | `TIMESTAMPTZ` | 全部时间列（`_at` 后缀 UTC；retry_after 为命名例外） |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL` | 五表 id |
| `INTEGER`（0/1） | `BOOLEAN` | error_codes.retryable |
| `VARCHAR`/`INTEGER`/`TEXT` | 同名 | 兼容 |
| `UNIQUE(...)` | `CONSTRAINT ... UNIQUE` | uq_wj_idempotency / uq_tk_idempotency / 主键 |
| `CREATE INDEX` | `CREATE INDEX IF NOT EXISTS` | idx_wj_* / idx_tk_* / idx_logs_module_ts |
| SQLite 无时区 | `now()` 默认值（TIMESTAMPTZ） | created_at/updated_at |

## 三、执行方式

```bash
# 1) 建表 + 种子（幂等）
psql "$POSTGRES_DSN" -f 0001_create_base_tables.pg.sql

# 2) 数据复制（SQLite → PG）：建议用 Python/SQLAlchemy 双引擎脚本
#    （SQLite 逐表 SELECT → PG INSERT；JSON 列走 JSONB；时间戳补 UTC tzinfo）。
#    迁移包（app.sanitized.db）落地后执行，先核对源库行数与 DDL 差异。

# 3) 切换与冒烟
#    M0_DB_URL=postgresql+psycopg2://... python -m foundation init-db   # 幂等自检
#    M0_DB_URL=postgresql+psycopg2://... python -m foundation scheduler --once
```

## 四、回滚方案

| 场景 | 回滚动作 |
|---|---|
| 未切流量前发现异常 | **切回 SQLite 保留快照**：`M0_DB_URL` 改回 `sqlite:///data/db/m0-foundation.db`，无数据损失（PG 表可保留或 DROP） |
| 已切流量后需回退 | 停服务 → 切回 SQLite（PG 侧数据不自动回写，SQLite 快照为基线）→ 修问题后重跑迁移 |
| 彻底放弃 PG 侧 | `psql "$POSTGRES_DSN" -f 0001_rollback.pg.sql`（逆序 DROP，数据丢失） |

## 五、校验 SQL（迁移后核对）

```sql
-- 行数核对（与 SQLite 源库逐表对比）
SELECT 'workflow_jobs' AS tbl, count(*) FROM workflow_jobs
UNION ALL SELECT 'tasks', count(*) FROM tasks
UNION ALL SELECT 'logs', count(*) FROM logs
UNION ALL SELECT 'app_config', count(*) FROM app_config
UNION ALL SELECT 'error_codes', count(*) FROM error_codes;
-- 错误码种子应 = 9 条
SELECT count(*) FROM error_codes;
-- 唯一约束存在性
SELECT conname FROM pg_constraint WHERE conname IN ('uq_wj_idempotency','uq_tk_idempotency');
```

## 迁移记录

| 版本 | 说明 | 日期 |
|---|---|---|
| v0.6 | A5：PG 方言五表 DDL + 种子 + 回滚 + 迁移计划文档 | 2026-08-29 |
