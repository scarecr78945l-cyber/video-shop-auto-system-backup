-- =============================================================================
-- 0001_create_base_tables.pg.sql
-- M0 基座五表 · PostgreSQL 方言 DDL（对齐 database/README.md 最终 DDL v0.2）
-- 幂等：CREATE TABLE IF NOT EXISTS + 种子 ON CONFLICT DO NOTHING，可重复执行。
-- 数据口径（REC-005）：金额一律「分」int（JSONB 内同）；时间戳 timestamptz UTC；
--   时间戳字段后缀 _at（retry_after 为总控指定命名例外）。
-- 方言差异：JSON→JSONB / DATETIME→TIMESTAMPTZ / AUTOINCREMENT→BIGSERIAL /
--   INTEGER(0/1)→BOOLEAN（error_codes.retryable）。
-- 执行：psql "$POSTGRES_DSN" -f 0001_create_base_tables.pg.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------- workflow_jobs
CREATE TABLE IF NOT EXISTS workflow_jobs (
    id                  BIGSERIAL PRIMARY KEY,
    product_id          INTEGER NOT NULL,                    -- 跨库业务引用，不建 FK
    stage               VARCHAR(40) NOT NULL,                -- source_collect|alibaba_quote|taobao_reference|image_generation|listing_upload|shop_ads_run|shop_ads_report
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_code          VARCHAR(40),
    error_message       TEXT DEFAULT '',
    retry_count         INTEGER NOT NULL DEFAULT 0,
    retry_after         TIMESTAMPTZ,                         -- 下次可重试时间（UTC）
    lease_owner         VARCHAR(120),
    lease_expires_at    TIMESTAMPTZ,                         -- 45min 过期回收
    generation_version  VARCHAR(40) NOT NULL DEFAULT 'v1',
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 金额按分 int（REC-005）
    evidence_json       JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 结果证据
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wj_idempotency UNIQUE (product_id, stage, generation_version)
);
CREATE INDEX IF NOT EXISTS idx_wj_status ON workflow_jobs(status);
CREATE INDEX IF NOT EXISTS idx_wj_stage  ON workflow_jobs(stage);
CREATE INDEX IF NOT EXISTS idx_wj_retry  ON workflow_jobs(retry_after);
CREATE INDEX IF NOT EXISTS idx_wj_lease  ON workflow_jobs(lease_expires_at);

-- ---------------------------------------------------------------- tasks
CREATE TABLE IF NOT EXISTS tasks (
    id                 BIGSERIAL PRIMARY KEY,
    job_id             INTEGER NOT NULL,                     -- 归属 workflow_jobs.id（不建 FK 防跨库）
    stage              VARCHAR(40) NOT NULL,
    task_type          VARCHAR(60) NOT NULL DEFAULT '',
    status             VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_code         VARCHAR(40),
    error_message      TEXT DEFAULT '',
    retry_count        INTEGER NOT NULL DEFAULT 0,
    retry_after        TIMESTAMPTZ,
    lease_owner        VARCHAR(120),
    lease_expires_at   TIMESTAMPTZ,
    payload            JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tk_idempotency UNIQUE (job_id, task_type)
);
CREATE INDEX IF NOT EXISTS idx_tk_job    ON tasks(job_id);
CREATE INDEX IF NOT EXISTS idx_tk_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tk_retry  ON tasks(retry_after);

-- ---------------------------------------------------------------- logs
CREATE TABLE IF NOT EXISTS logs (
    id         BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    module     VARCHAR(20) NOT NULL,                         -- m0/m1/.../m5
    level      VARCHAR(10) NOT NULL,
    event      VARCHAR(120) DEFAULT '',
    message    TEXT DEFAULT '',
    evidence   JSONB NOT NULL DEFAULT '{}'::jsonb            -- 写入前必须 redact（P-004）
);
CREATE INDEX IF NOT EXISTS idx_logs_module_ts ON logs(module, created_at);

-- ---------------------------------------------------------------- app_config
CREATE TABLE IF NOT EXISTS app_config (
    key         VARCHAR(120) PRIMARY KEY,
    value       JSONB NOT NULL DEFAULT '{}'::jsonb,          -- 金额类配置按分 int
    description VARCHAR(500) DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- error_codes
CREATE TABLE IF NOT EXISTS error_codes (
    code            VARCHAR(40) PRIMARY KEY,
    retryable       BOOLEAN NOT NULL DEFAULT FALSE,
    backoff_seconds INTEGER NOT NULL DEFAULT 0,
    action          VARCHAR(60) NOT NULL,                    -- retry|manual_takeover|block_forever
    description     VARCHAR(300) DEFAULT ''
);

-- 错误码种子（幂等；对齐 09 文档码表 + PAGE_CHANGED）
INSERT INTO error_codes (code, retryable, backoff_seconds, action, description) VALUES
    ('VERIFICATION_REQUIRED',   FALSE, 0,   'manual_takeover', '验证码/安全验证：单任务暂停 60min 等人工'),
    ('AUTH_REQUIRED',           FALSE, 0,   'manual_takeover', '登录失效：人工登录后断点续跑'),
    ('RATE_LIMIT',              TRUE,  180, 'retry',           '限流/频繁：180s 退避'),
    ('TIMEOUT',                 TRUE,  60,  'retry',           '超时：60s 退避'),
    ('NO_MATCH',                TRUE,  120, 'retry',           '无同款：120s 退避'),
    ('INSUFFICIENT_REFERENCES', TRUE,  120, 'retry',           '素材/参考不足：120s 退避'),
    ('PLATFORM_REJECT',         FALSE, 0,   'block_forever',   '平台驳回（资质/内容）：记录原因转人工/修复候选'),
    ('UNEXPECTED',              TRUE,  60,  'retry',           '未知错误：60s 退避，留证据'),
    ('PAGE_CHANGED',            TRUE,  120, 'retry',           '页面改版：选择器失效，留证据（P-003）')
ON CONFLICT (code) DO NOTHING;

COMMIT;
