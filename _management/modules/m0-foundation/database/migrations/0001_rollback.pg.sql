-- =============================================================================
-- 0001_rollback.pg.sql
-- M0 基座五表 · PostgreSQL 回滚（逆序 DROP，幂等）
-- 注意：回滚 = 删除 PG 侧表（数据丢失）；切换期回滚方案见 README.md：
--   未切流量前回滚 = 直接切回 SQLite 保留快照（POSTGRES_DSN 改回 M0_DB_URL），
--   PG 侧 DROP 仅用于彻底放弃迁移。
-- =============================================================================

BEGIN;

DROP TABLE IF EXISTS logs;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS workflow_jobs;
DROP TABLE IF EXISTS app_config;
DROP TABLE IF EXISTS error_codes;

COMMIT;
