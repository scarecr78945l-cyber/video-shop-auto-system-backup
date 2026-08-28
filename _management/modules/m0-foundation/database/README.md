# M0 基座与数据治理 · 模块数据库（database）

> 本模块独立数据库：开发库文件 `backend/data/db/m0-foundation.db`（SQLite，不入 git；可暂不建库，本轮为 Schema 规划）。
> 铁律：只操作本模块库；共享表其他模块只读（宪法第 4 节）；生产切 PostgreSQL 时迁移脚本放本目录。
> **数据口径（总控裁决 REC-005 / DA-001，M4/M5 已按此实现）**：金额一律「分」int 存储（含 JSON 内金额），展示层转元；时间一律 UTC（ISO8601 带时区），时间戳字段名后缀 `_at`，展示层转 UTC+8。

## 一、表清单与前缀约定

| 前缀 | 归属 | 说明 |
|---|---|---|
| （无前缀） | **M0 共享基座** | `workflow_jobs` / `tasks` / `logs` / `app_config` / `error_codes` |
| `m1_*` | M1 | 选品域（现 `backend/sourcing/` 已建表，物理库归 M1） |
| `asset_*` | M2 | 素材域 |
| `image_*` | M3 | 图片/视频优化域 |
| `listing_*` / `wechat_*` | M4 | 上架域 |
| `ad_*` | M5 | 投放域 |

> 注意：`app_config` 表当前实现位于 `backend/sourcing/tables.py`（`AppConfigRow`，键值+JSON），归属 M0 共享。首轮以「键约定统一、物理库随迁移包整合」处理；迁移包落地后经 `data-audit.md` 核对跨库归属。

## 二、Schema（DDL，SQLite 方言；PostgreSQL 方言差异见迁移计划）

### `workflow_jobs` — 任务队列主表（09 文档第二节）

```sql
CREATE TABLE workflow_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL,      -- 业务商品 ID（跨库引用，不建 FK 防跨库）
    stage               VARCHAR(40) NOT NULL,  -- source_collect|alibaba_quote|taobao_reference|image_generation|listing_upload|shop_ads_run|shop_ads_report
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
                      -- pending|running|waiting_login|waiting_verification|blocked|success|failed|cancelled
    error_code          VARCHAR(40),           -- 见 error_codes 表
    error_message       TEXT DEFAULT '',
    retry_count         INTEGER DEFAULT 0,
    next_retry_at       DATETIME,
    lease_owner         VARCHAR(120),          -- 租约持有者（worker id）
    lease_expires_at    DATETIME,              -- 45min 过期回收
    generation_version  VARCHAR(40) DEFAULT 'v1',
    payload             JSON,                  -- 入队参数/断点数据
    result              JSON,                  -- 结果证据（evidence_json 沿用）
    created_at          DATETIME NOT NULL,
    updated_at          DATETIME NOT NULL,
    UNIQUE (product_id, stage, generation_version)  -- 幂等防重复入队（09 文档）
);
CREATE INDEX idx_wj_status     ON workflow_jobs(status);
CREATE INDEX idx_wj_stage      ON workflow_jobs(stage);
CREATE INDEX idx_wj_next_retry ON workflow_jobs(next_retry_at);
```

### `tasks` — 任务明细/子任务（骨架，待迁移包核对后定稿）

```sql
CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER,                       -- 关联 workflow_jobs.id（暂不建 FK）
    task_type   VARCHAR(60),
    status      VARCHAR(20) DEFAULT 'pending',
    payload     JSON,
    result      JSON,
    error_code  VARCHAR(40),
    created_at  DATETIME NOT NULL,
    updated_at  DATETIME NOT NULL
);
```

### `logs` — 操作留痕（脱敏）

```sql
CREATE TABLE logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at DATETIME NOT NULL,              -- 时间戳字段统一 _at 后缀（REC-005）
    module     VARCHAR(20) NOT NULL,           -- m0/m1/.../m5
    level      VARCHAR(10) NOT NULL,
    event      VARCHAR(120),
    message    TEXT,
    evidence   JSON                            -- 敏感字段写入前必须 _redact_text
);
CREATE INDEX idx_logs_module_ts ON logs(module, created_at);
```

### `app_config` — 全局配置（键值+JSON，M0 拥有，全员只读）

```sql
-- 已存在于 backend/sourcing/tables.py（AppConfigRow: key PK / value JSON / description / updated_at）
-- 键命名约定：<域>.<名>，例如：
--   budget.single_max | budget.daily_max | budget.plan_max   （预算三重硬约束）
--   risk.throttle_levels | risk.circuit_breaker_failures | risk.lease_minutes
--   category.whitelist | scoring.weights | ads.roi_target
```

### `error_codes` — 错误码 → 重试策略映射（M0 唯一权威，宪法第 8 节）

```sql
CREATE TABLE error_codes (
    code             VARCHAR(40) PRIMARY KEY,
    retryable        INTEGER NOT NULL DEFAULT 0,
    backoff_seconds  INTEGER NOT NULL DEFAULT 0,
    action           VARCHAR(60) NOT NULL,     -- retry|manual_takeover|block_forever
    description      VARCHAR(300)
);

-- 种子数据（对齐 09 文档错误码表）：
INSERT INTO error_codes VALUES
 ('VERIFICATION_REQUIRED',   0,    0, 'manual_takeover', '验证码/安全验证：单任务暂停 60min 等人工'),
 ('AUTH_REQUIRED',           0,    0, 'manual_takeover', '登录失效：人工登录后断点续跑'),
 ('RATE_LIMIT',              1,  180, 'retry',          '限流/频繁：180s 退避'),
 ('TIMEOUT',                 1,   60, 'retry',          '超时：60s 退避'),
 ('NO_MATCH',                1,  120, 'retry',          '无同款：120s 退避'),
 ('INSUFFICIENT_REFERENCES', 1,  120, 'retry',          '素材/参考不足：120s 退避'),
 ('PLATFORM_REJECT',         0,    0, 'block_forever',  '平台驳回（资质/内容）：记录原因转人工/修复候选'),
 ('UNEXPECTED',              1,   60, 'retry',          '未知错误：60s 退避，留证据'),
 ('PAGE_CHANGED',            1,  120, 'retry',          '页面改版：选择器失效，留证据（P-003）');
```

## 三、迁移计划（SQLite → PostgreSQL）

| 阶段 | 内容 | 输出 |
|---|---|---|
| 1 兼容期 | SQLAlchemy 方言无关 DDL；SQLite 开发 | 现有 sourcing 库 + `m0-foundation.db` |
| 2 迁移脚本 | alembic 或纯 SQL：`CREATE TABLE IF NOT EXISTS` + 数据复制 + 序列重建 | `database/migrations/` |
| 3 切换 | `POSTGRES_DSN` 环境变量切换；启动自检；回滚 = 切回 SQLite 保留快照 | 切换清单 |
| 4 校验 | 行数/唯一约束/索引核对 + 回归测试 | `data-audit` 记录 |

> 方言差异备忘：JSON 类型 SQLite→PostgreSQL 用 `JSONB`；DATETIME→`TIMESTAMPTZ`；`AUTOINCREMENT`→`IDENTITY/SERIAL`；布尔 Integer→Boolean。

## 迁移记录

| 版本 | 说明 | 日期 |
|---|---|---|
| v0 | 初始规划（本文件：共享表清单/DDL/迁移计划） | 2026-08-28 |
