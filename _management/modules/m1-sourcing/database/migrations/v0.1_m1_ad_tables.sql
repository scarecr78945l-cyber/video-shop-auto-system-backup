-- ============================================================================
-- M1 自动选品 · 迁移 v0.1：m1 投放转化两张表
--   m1_ad_conversion_cache     类目级投放转化缓存（打分输入）
--   m1_ad_conversion_ingests   回写导入审计（幂等/追溯）
-- ============================================================================
-- SQLite 幂等 DDL：CREATE TABLE IF NOT EXISTS + 唯一约束，重复执行不报错、不产生重复数据。
-- ORM 定义源：backend/sourcing/tables.py（M1AdConversionCache / M1AdConversionIngest）。
-- 字段口径：_management/modules/m1-sourcing/database/README.md 第二节；
--           _management/modules/m1-sourcing/context/README.md C-2（M5 回写契约）。
-- 生产 PostgreSQL 迁移起点（见同目录 README.md 方式三）。
-- ============================================================================

-- 1) 类目级投放转化缓存（打分输入）
CREATE TABLE IF NOT EXISTS m1_ad_conversion_cache (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category      VARCHAR(80)  NOT NULL,            -- 类目锚点（与 products.category 一致，C-1）
    roi           REAL         NOT NULL DEFAULT 0,   -- 期间托管 ROI（成交额/花费，比值无量纲）
    sales_amount  INTEGER      NOT NULL DEFAULT 0,   -- 期间托管成交额（分，int；与 M5 口径对齐，禁元/分混用）
    sample_count  INTEGER      NOT NULL DEFAULT 0,   -- 计入商品数（<5 弱样本，打分视为无数据）
    period_start  VARCHAR(20)  NOT NULL,             -- 快照期起 YYYY-MM-DD
    period_end    VARCHAR(20)  NOT NULL,             -- 快照期止 YYYY-MM-DD
    generated_at  DATETIME     NOT NULL,             -- M5 生成时间（新鲜度判定基准，R-14；ISO-8601 带时区）
    source_file   VARCHAR(300) NOT NULL DEFAULT '',  -- 来源交换文件（审计）
    ingested_at   DATETIME     NOT NULL,             -- 本模块导入时间（UTC）
    UNIQUE (category, period_start, period_end)      -- 幂等键：同周期重复导入覆盖
);
CREATE INDEX IF NOT EXISTS idx_m1_ad_cache_category ON m1_ad_conversion_cache (category);
CREATE INDEX IF NOT EXISTS idx_m1_ad_cache_period   ON m1_ad_conversion_cache (period_start, period_end);

-- 2) 回写导入审计（幂等/追溯）
CREATE TABLE IF NOT EXISTS m1_ad_conversion_ingests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file  VARCHAR(300) NOT NULL,
    schema_ver   INTEGER      NOT NULL DEFAULT 1,
    period_start VARCHAR(20)  NOT NULL,
    period_end   VARCHAR(20)  NOT NULL,
    generated_at DATETIME     NOT NULL,
    rows_loaded  INTEGER      NOT NULL DEFAULT 0,
    skipped      INTEGER      NOT NULL DEFAULT 0,    -- 弱样本/无类目命中跳过数
    status       VARCHAR(20)  NOT NULL DEFAULT 'ok', -- ok | partial | failed
    message      TEXT         NOT NULL DEFAULT '',
    ingested_at  DATETIME     NOT NULL,
    UNIQUE (source_file, period_start, period_end, generated_at)
);
