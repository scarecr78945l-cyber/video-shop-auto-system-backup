# M5 自动小店投放（商品托管） · 模块数据库（database）

> 本模块独立数据库：开发库文件 `backend/data/db/m5-ads.db`（SQLite，不入 git）。
> 铁律：只操作本模块库；表名前缀 `ad_*`（宪法第 4 节）；生产切 PostgreSQL 时迁移脚本放本目录。
> 版本：v0.1 ｜ 撰写人：M5 总工 ｜ 日期：2025 体系建立日
> 口径（遵循总控 data-audit DA-001 裁决）：**金额一律「分」（int）**；**时间存储一律 UTC（ISO8601 带时区），展示层转 UTC+8**，时间戳字段名后缀 `_at`；主键自增 INTEGER。字段定义与 context/README.md 数据字典一致。

## 一、Schema 规划（SQLite DDL）

```sql
-- ============================================================
-- M5 自动小店投放（商品托管）· m5-ads.db  Schema v0.1
-- 表前缀 ad_*，与 08 文档第三节数据模型对齐
-- ============================================================

-- 1. 托管投放计划（一个托管计划 = 1 商品 + 1 组投放设置）
CREATE TABLE IF NOT EXISTS ad_campaigns (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL,            -- 与 M1 products.id 对齐（仅销售中商品）
    ad_mode             TEXT    NOT NULL DEFAULT 'goods_trust',  -- 商品托管（本项目唯一模式）
    target_type         TEXT    NOT NULL DEFAULT '成交ROI',      -- 成交ROI/净成交ROI/商品成交
    target_roi          REAL    NOT NULL DEFAULT 2.00,           -- 默认取系统推荐，可配置覆盖
    material_ids_json   TEXT    NOT NULL DEFAULT '[]',           -- 素材库ID列表（含视频号形象）
    status              TEXT    NOT NULL DEFAULT '待托管',        -- 待托管/托管中/已暂停/不可投放/已结束
    diagnosis           TEXT,                                    -- 优秀/良好/1项待优化/N项待优化
    batch_id            INTEGER,                                 -- 批量托管批次
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_product   ON ad_campaigns(product_id);
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_status    ON ad_campaigns(status);

-- 2. 托管执行记录（复用 WorkflowJob 机制：租约/错误分类/断点）
CREATE TABLE IF NOT EXISTS ad_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id       INTEGER NOT NULL REFERENCES ad_campaigns(id),
    attempt           INTEGER NOT NULL DEFAULT 1,
    status            TEXT    NOT NULL DEFAULT 'running',   -- running/success/failed/blocked
    error_code        TEXT,                                 -- 09 码表：VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/TIMEOUT/NO_MATCH/PLATFORM_REJECT/UNEXPECTED/page_changed
    evidence_json     TEXT    NOT NULL DEFAULT '{}',        -- 操作留痕（截图路径/选择器/耗时/URL，脱敏）
    lease_owner       TEXT,                                 -- 执行进程标识
    lease_expires_at  TEXT,                                 -- 租约 45min 过期回收
    batch_id          INTEGER,                              -- 批次号（≤50/批）
    created_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ad_runs_campaign ON ad_runs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_ad_runs_status   ON ad_runs(status);

-- 3. 投放报表快照（定时回读投放列表，幂等）
CREATE TABLE IF NOT EXISTS ad_report_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id       INTEGER NOT NULL REFERENCES ad_campaigns(id),
    recorded_at       TEXT    NOT NULL,                     -- 回读时间
    impressions       INTEGER NOT NULL DEFAULT 0,           -- 曝光（次）
    spend             INTEGER NOT NULL DEFAULT 0,           -- 花费（分）
    gmv               INTEGER NOT NULL DEFAULT 0,           -- 成交金额（分）
    platform_subsidy  INTEGER NOT NULL DEFAULT 0,           -- 平台补贴（分），补贴后ROI单独统计
    diagnosis         TEXT,                                 -- 智能诊断
    status            TEXT,                                 -- 投放中/暂停/不可投放
    UNIQUE(campaign_id, recorded_at)                        -- 幂等：同周期仅保留最新快照
);
CREATE INDEX IF NOT EXISTS idx_ad_snapshots_campaign_time ON ad_report_snapshots(campaign_id, recorded_at);

-- 4. 投放账户状态（仿 SourcePlatformState）
CREATE TABLE IF NOT EXISTS ad_account_states (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    balance           INTEGER NOT NULL DEFAULT 0,           -- 可用余额（分）
    status            TEXT    NOT NULL DEFAULT 'normal',    -- normal/risk_control/waiting_login/waiting_verification/paused
    throttle_level    INTEGER NOT NULL DEFAULT 0,           -- 0~4 节流级（间隔×1/2/4/8/16）
    paused_until      TEXT,                                 -- 暂停截止（人工接管断点续跑）
    pause_reason      TEXT,
    updated_at        TEXT    NOT NULL
);

-- 5. 素材库视频（与 M2/M3 assets 打通，评估标签回流）
CREATE TABLE IF NOT EXISTS ad_materials (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id           TEXT    NOT NULL,                 -- 小店素材库ID
    asset_id              INTEGER,                          -- 关联 M2/M3 assets.id（data-audit 核对）
    file_path             TEXT,                             -- 本地路径（环境变量根目录下）
    duration              REAL,                             -- 秒（5~300s）
    resolution            TEXT,                             -- 如 1080x1920（9:16，≥720×1280）
    evaluation            TEXT    NOT NULL DEFAULT '探索期', -- 探索期/高效/潜力（投放效果回流更新）
    upload_status         TEXT    NOT NULL DEFAULT '审核中', -- 上传中/已上传/审核中/审核通过/审核不通过/源文件损坏
    platform_material_id  TEXT,                             -- 平台侧素材ID
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL,
    UNIQUE(material_id)
);
CREATE INDEX IF NOT EXISTS idx_ad_materials_eval ON ad_materials(evaluation);
```

## 二、配置项（app_config 扩展，M0 基座表，写入经总控协调）

| key | 默认 | 说明 |
|---|---|---|
| ads.batch_size | 50 | 单批托管上限（平台硬限 ≤50） |
| ads.batch_interval_s | 300 | 批间隔（防风控，可配） |
| ads.report_interval_s | 1800 | 报表回读周期（10~30min 可配） |
| ads.stoploss_impression | 500 | 止损曝光阈值 |
| ads.min_balance_fen | 10000 | 余额阈值（¥100 → 10000 分） |
| ads.roi_floor_ratio | 0.8 | ROI 止损线（目标×80%，持续 2 周期） |
| ads.max_active_campaigns | 40 | 投放中商品上限（停止新增等自然淘汰） |
| ads.budget_single_fen / ads.budget_daily_fen / ads.budget_plan_fen | 0（不限） | 预算三重硬约束 |
| ads.kill_switch | false | 一键全停总开关 |

## 三、迁移记录

| 版本 | 说明 | 日期 |
|---|---|---|
| v0.1 | 初始 Schema：ad_campaigns / ad_runs / ad_report_snapshots / ad_account_states / ad_materials | 2025 体系建立日 |

> 后续：生产环境切 PostgreSQL 时，将本 DDL 移植为 PG 语法（BIGSERIAL/JSONB/TIMESTAMPTZ），迁移脚本放本目录 `migrations/`。
