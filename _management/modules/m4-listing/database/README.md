# M4 自动上架 · 模块数据库（database）

> 本模块独立数据库：开发库文件 `backend/data/db/m4-listing.db`（SQLite，不入 git）。
> 铁律：只操作本模块库；表名前缀见宪法第 4 节（本模块 `listing_*`）；生产切 PostgreSQL 时迁移脚本放本目录。

## 一、表归属决策（重要）

| 表 | 归属 | 本模块权限 | 说明 |
|---|---|---|---|
| `listing_tasks` / `listing_spus` / `listing_skus` / `listing_upload_assets` / `listing_op_logs` / `listing_audit_records` / `listing_quota_states` | **M4（本库）** | 读写 | 本模块全部私有状态，前缀 listing_*，防冲突（宪法第 4 节 / P-005） |
| `workflow_jobs` / `tasks` / `logs` / `app_config` / `products` / `sku` / `pricing` / `image_assets` / `category_listing_memory` | 基座 M0（共享） | **只读** | 09 文档列出现有表；读取须在 data-audit.md 登记，写入经总控协调 |
| `upload_history` / `wechat_upload_logs` | 基座 M0（半成品既有表，09 文档列为复用） | **默认只读参照** | 设计 07 要求「每次操作留痕：UploadHistory + WechatUploadLog」：M4 以 `listing_upload_assets` / `listing_op_logs` 为本模块证据留痕，两者字段语义对齐（见下）；若基座侧开通写通道（总控批准），再以 `upload_history`/`wechat_upload_logs` 为正式落点，写入时登记 data-audit.md。**此决策记录于 decisions.md** |

## 二、Schema（DDL 规划，SQLite 方言，生产迁移 PostgreSQL 时同构改造）

> 字段口径与单位见 context/README.md 数据字典。JSON 字段统一存 TEXT（SQLite 无原生 JSON 类型；PostgreSQL 迁移为 jsonb）。

```sql
-- ============================================================
-- M4 自动上架模块库：m4-listing.db
-- 版本：v0（规划稿，暂不建库；开发时由 P1/P3 子代理落地执行）
-- 通用约定：created_at/updated_at 存 UTC ISO-8601 文本；金额单位一律“分”
-- ============================================================

-- 1. 上架任务（状态机主表）
CREATE TABLE IF NOT EXISTS listing_tasks (
    task_id            TEXT PRIMARY KEY,          -- = workflow_jobs 关联 ID
    product_id         INTEGER NOT NULL,          -- 基座 products.id
    generation_version TEXT NOT NULL,             -- 幂等键组成（M1/M3 版本号）
    stage              TEXT NOT NULL DEFAULT 'listing_upload',
    status             TEXT NOT NULL DEFAULT 'pending',
    gate_result        TEXT,                      -- JSON: {item:{passed,reason,evidence}}
    platform_spu_id    TEXT,                      -- create_spu 返回
    product_link       TEXT,                      -- 真实链接，验证通过前为空
    link_verified_at   TEXT,
    reject_reason_code TEXT,
    attempts           INTEGER NOT NULL DEFAULT 0,
    lease_owner        TEXT,
    lease_expires_at   TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE (product_id, stage, generation_version)  -- 幂等防重复入队
);
CREATE INDEX IF NOT EXISTS idx_listing_tasks_status ON listing_tasks(status);
CREATE INDEX IF NOT EXISTS idx_listing_tasks_product ON listing_tasks(product_id);

-- 2. SPU 平台映射
CREATE TABLE IF NOT EXISTS listing_spus (
    spu_id             TEXT PRIMARY KEY,          -- 平台 SPU ID
    task_id            TEXT NOT NULL REFERENCES listing_tasks(task_id),
    title              TEXT NOT NULL,
    category_id        INTEGER NOT NULL,
    qualification      TEXT,                      -- JSON 摘要（不含凭证原文）
    freight_template_id TEXT,
    purchase_limit     TEXT,                      -- JSON {per_user,period}
    status             TEXT NOT NULL,
    audit_id           TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_listing_spus_task ON listing_spus(task_id);

-- 3. SKU 平台映射
CREATE TABLE IF NOT EXISTS listing_skus (
    sku_id             TEXT PRIMARY KEY,          -- 平台 SKU ID
    spu_id             TEXT NOT NULL REFERENCES listing_spus(spu_id),
    product_sku_code   TEXT NOT NULL,             -- 基座 sku 主键（M1 成本来源）
    price_cents        INTEGER NOT NULL,          -- 分；定价阶梯结果
    cost_cents         INTEGER NOT NULL,          -- 分；真实成本，仅入库不对外
    stock              INTEGER NOT NULL DEFAULT 10000,
    purchase_limit     TEXT,                      -- JSON（默认每月 2 件）
    status             TEXT NOT NULL,
    UNIQUE (spu_id, product_sku_code)
);

-- 4. 上传历史（主图/详情图；与基座 upload_history 语义对齐）
CREATE TABLE IF NOT EXISTS listing_upload_assets (
    asset_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id            TEXT NOT NULL REFERENCES listing_tasks(task_id),
    image_asset_id     INTEGER NOT NULL,          -- 基座 image_assets.id（M3）
    file_sha256        TEXT NOT NULL,             -- 上传幂等去重键
    media_id           TEXT,                      -- upload_image 返回
    usage              TEXT NOT NULL,             -- main_image / detail_image
    position           INTEGER NOT NULL DEFAULT 0,-- 主图 1–5，详情图 0
    status             TEXT NOT NULL DEFAULT 'uploaded',
    evidence           TEXT,                      -- JSON 脱敏摘要
    created_at         TEXT NOT NULL,
    UNIQUE (task_id, file_sha256)
);
CREATE INDEX IF NOT EXISTS idx_listing_assets_task ON listing_upload_assets(task_id);

-- 5. 微信操作日志（证据留痕；与基座 wechat_upload_logs 语义对齐）
CREATE TABLE IF NOT EXISTS listing_op_logs (
    log_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id            TEXT NOT NULL,
    request_id         TEXT NOT NULL,             -- 幂等键
    api                TEXT NOT NULL,             -- create_spu / create_skus / upload_image / submit_audit / query_audit_status / get_product_link / update_stock / update_price / update_spu
    direction          TEXT NOT NULL,             -- request / response
    payload_digest     TEXT,                      -- 请求体脱敏摘要（无密钥）
    status_code        INTEGER,
    error_code         TEXT,                      -- WorkflowJob 错误码
    platform_code      TEXT,                      -- 平台业务错误码原样
    evidence_json      TEXT,                      -- 响应证据（敏感字段脱敏）
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_listing_oplogs_task ON listing_op_logs(task_id, created_at);

-- 6. 审核记录（提交/轮询/驳回/拒审处理）
CREATE TABLE IF NOT EXISTS listing_audit_records (
    audit_record_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id            TEXT NOT NULL REFERENCES listing_tasks(task_id),
    audit_id           TEXT NOT NULL,
    submit_at          TEXT NOT NULL,
    last_query_at      TEXT,
    audit_status       TEXT,                      -- 平台原样状态
    reject_reason      TEXT,
    reject_category    TEXT,                      -- title/category/qualification/image/price/content_compliance/other
    fix_candidate      TEXT,                      -- JSON 修复候选
    resubmit_required  INTEGER NOT NULL DEFAULT 1,-- 二次门禁标志
    evidence           TEXT,
    UNIQUE (task_id, audit_id)
);
CREATE INDEX IF NOT EXISTS idx_listing_audits_task ON listing_audit_records(task_id);

-- 7. 接口配额状态（令牌桶 + 熔断探针）
CREATE TABLE IF NOT EXISTS listing_quota_states (
    api                  TEXT PRIMARY KEY,
    tokens               REAL NOT NULL,
    capacity             REAL NOT NULL,
    refill_rate          REAL NOT NULL,           -- 令牌/秒
    window_start         TEXT NOT NULL,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    circuit_open_until   TEXT
);
```

## 三、索引与查询要点

- 入队查询：`status='pending'` 且 `lease_expires_at` 过期/空（断点续跑）。
- 已上架判据查询：`status='listed' AND link_verified_at IS NOT NULL AND product_link != ''`（M5 候选池只读视图，**仅销售中商品**）。
- 幂等去重：`UNIQUE(product_id, stage, generation_version)`；图片 `UNIQUE(task_id, file_sha256)`；审核 `UNIQUE(task_id, audit_id)`。

## 四、迁移记录

| 版本 | 说明 | 日期 |
|---|---|---|
| v0 | 初始规划稿（本回合，仅文档不建库；DDL 由 P1/P3 子代理落地并登记） | 2025 体系建立日 |

## 五、生产迁移（M4 阶段，SQLite → PostgreSQL）

- 迁移脚本目录：本目录 `migrations/`（如 `0001_init.sql` / `0001_up.sql`），由总控统一排期执行。
- 注意点：JSON 字段 TEXT → jsonb；AUTOINCREMENT → SERIAL/IDENTITY；`REFERENCES` 保留；索引名保留。
- 迁移前必须备份 `m4-listing.db`（备份由总控执行，本模块不运行 git/备份命令）。
