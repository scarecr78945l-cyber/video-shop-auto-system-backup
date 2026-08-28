# M2 自动收集素材 · 模块数据库（database）

> 本模块独立数据库：开发库文件 `backend/data/db/m2-materials.db`（SQLite，不入 git，备份由总控统一执行）。
> 铁律：只操作本模块库；本模块全部表前缀 `asset_*`（宪法第 4 节）；基座共享表（`workflow_jobs`/`app_config`/`logs`）只读。
> 生产切换 PostgreSQL 时，迁移脚本放本目录（对齐 11 文档 M4 里程碑：SQLite→PostgreSQL + MinIO + Redis）。
> 本文件仅做 Schema 规划（v0.1 筹备阶段暂不建库，DDL 已按 SQLite 语法可直接执行）。

---

## 一、表清单总览

| 表 | 作用 | 对应 09 文档 |
|---|---|---|
| `asset_items` | 素材库主表（视频/图片，双去重，评估标签，平台素材 ID） | 新增表 `assets`（本模块实现名，见 decisions.md） |
| `asset_download_jobs` | 下载任务账本（状态/重试/节流/租约/证据） | 对齐 `source_collection_events`/`source_runs` 模式 |
| `asset_sources` | 采集源/达人账本（游标/next_run_at/节流级/熔断） | 对齐 `source_cursors`/`source_platform_states` 模式 |
| `asset_dedup_fingerprints` | 去重指纹注册表（防并发重复入库） | 对齐 `product_fingerprint_claims` 认领机制 |
| `asset_evaluations` | 评估标签回流审计（M5 回写留痕） | 新增（05 文档评估标签回流） |
| `asset_compliance_checks` | 内容预审记录（供应链词/品牌词命中） | 复用 `compliance.py` 逻辑的落库 |
| `asset_uploads` | 上传小店素材库记录 | 新增（05 文档 upload_status/platform_material_id） |

---

## 二、Schema（DDL，SQLite 语法）

```sql
-- ============================================================
-- M2 素材模块 Schema v0.1（规划版）
-- 约定：时间戳统一 TEXT ISO8601 UTC；布尔用 INTEGER 0/1；
--       枚举用 TEXT + CHECK 约束；JSON 用 TEXT。
-- ============================================================

-- 1. 素材主表（Asset 实体，字段对齐 05 文档第四节 + 09 新增表 assets）
CREATE TABLE IF NOT EXISTS asset_items (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_type            TEXT    NOT NULL CHECK (asset_type IN ('video', 'image')),
    source_platform       TEXT    NOT NULL,                -- 视频号/抖音/快手/小红书/淘宝/1688/考古加/有米云
    source_url            TEXT    NOT NULL,                -- 追溯与版权标记依据
    source_author         TEXT,                            -- 达人/作者
    md5                   TEXT    NOT NULL,                -- 32 位小写 hex
    phash                 TEXT    NOT NULL,                -- 图片整图 phash / 视频关键帧 phash(JSON)
    file_path             TEXT    NOT NULL,                -- 存储键：本地相对键；M4 迁 MinIO 后为 MinIO 键
    duration              INTEGER,                         -- 秒（video 必填，5~300）
    resolution            TEXT,                            -- 宽x高，如 720x1280（video 必填）
    size                  INTEGER NOT NULL,                -- 字节，≤524288000
    tags_json             TEXT,                            -- 标签数组 JSON
    heat_score            REAL,                            -- 来源热度归一化 0~100
    evaluation            TEXT CHECK (evaluation IN ('exploring','efficient','potential') OR evaluation IS NULL),
    upload_status         TEXT    NOT NULL DEFAULT 'local'
                          CHECK (upload_status IN ('local','uploading','uploaded','failed','disabled')),
    platform_material_id  TEXT UNIQUE,                     -- 小店素材库 ID（投放绑定用）
    compliance_status     TEXT    NOT NULL DEFAULT 'pending'
                          CHECK (compliance_status IN ('pending','passed','rejected')),
    derivation_note       TEXT,                            -- 二创义务标记（去水印/混剪/换文案）
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_asset_items_platform ON asset_items (source_platform);
CREATE INDEX IF NOT EXISTS idx_asset_items_type_status ON asset_items (asset_type, upload_status);
CREATE INDEX IF NOT EXISTS idx_asset_items_evaluation ON asset_items (evaluation);
CREATE INDEX IF NOT EXISTS idx_asset_items_compliance ON asset_items (compliance_status);
CREATE INDEX IF NOT EXISTS idx_asset_items_md5 ON asset_items (md5);

-- 2. 下载任务账本（对齐 WorkflowJob 错误码体系：VERIFICATION_REQUIRED/AUTH_REQUIRED/
--    RATE_LIMIT/TIMEOUT/NO_MATCH/PLATFORM_REJECT/UNEXPECTED）
CREATE TABLE IF NOT EXISTS asset_download_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER REFERENCES asset_items (id),   -- 下载成功后回填
    source_platform TEXT    NOT NULL,
    source_url      TEXT    NOT NULL,
    job_type        TEXT    NOT NULL,                      -- video / image / video_page(取直链)
    status          TEXT    NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','success','failed','paused','blocked')),
    error_code      TEXT,                                  -- 错误码表
    error_message   TEXT,                                  -- 脱敏后信息
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 3,
    throttle_level  INTEGER NOT NULL DEFAULT 0,            -- 0~4 退避级
    next_run_at     TEXT,                                  -- 退避/人工接管后的续跑时间
    lease_owner     TEXT,                                  -- 租约持有者（实例 id）
    lease_expires_at TEXT,                                 -- 45min 过期回收
    evidence_json   TEXT,                                  -- 请求/响应摘要（不含 Cookie/密钥）
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_asset_dl_status ON asset_download_jobs (status, next_run_at);
CREATE INDEX IF NOT EXISTS idx_asset_dl_platform ON asset_download_jobs (source_platform, status);

-- 3. 采集源/达人账本（对齐 source_cursors + source_platform_states：游标/节流/熔断/断点）
CREATE TABLE IF NOT EXISTS asset_sources (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_platform      TEXT    NOT NULL,
    source_key           TEXT    NOT NULL,                 -- 达人 id / 关键词 / 榜单 id
    source_name          TEXT,                             -- 展示名
    cursor_value         TEXT,                             -- 分页游标
    next_run_at          TEXT,
    completed_for_date   TEXT,                             -- 当日已完成标记（YYYY-MM-DD）
    throttle_level       INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    risk_control         INTEGER NOT NULL DEFAULT 0,       -- 熔断：1=暂停该平台
    idle_runs            INTEGER NOT NULL DEFAULT 0,       -- 空转计数（实时榜降频用）
    config_json          TEXT,                             -- 该源专属配置（不含密钥）
    created_at           TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL,
    UNIQUE (source_platform, source_key)
);

-- 4. 去重指纹注册表（防并发重复入库；对齐 product_fingerprint_claims 认领机制）
CREATE TABLE IF NOT EXISTS asset_dedup_fingerprints (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint_type TEXT    NOT NULL,                     -- md5 / video_phash / image_phash
    fingerprint_value TEXT   NOT NULL,                     -- 指纹值（phash 含帧标识）
    asset_id         INTEGER NOT NULL REFERENCES asset_items (id),
    hits            INTEGER NOT NULL DEFAULT 1,            -- 命中次数（重复素材计数）
    claimed_at       TEXT    NOT NULL,                     -- 认领时间（并发认领用）
    UNIQUE (fingerprint_type, fingerprint_value)
);

CREATE INDEX IF NOT EXISTS idx_asset_fp_type ON asset_dedup_fingerprints (fingerprint_type);

-- 5. 评估标签回流审计（M5 回写留痕；asset_items.evaluation 只存当前值）
CREATE TABLE IF NOT EXISTS asset_evaluations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES asset_items (id),
    evaluation      TEXT    NOT NULL CHECK (evaluation IN ('exploring','efficient','potential')),
    evidence_json   TEXT,                                  -- 回流批次/报表快照摘要
    source_agent    TEXT,                                  -- 回写方（M5）
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_asset_eval_asset ON asset_evaluations (asset_id, created_at);

-- 6. 内容预审记录（供应链词/品牌词过滤；复用 compliance.py 逻辑）
CREATE TABLE IF NOT EXISTS asset_compliance_checks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES asset_items (id),
    check_type      TEXT    NOT NULL,                      -- supply_chain_word / brand_word / efficacy_word
    result          TEXT    NOT NULL,                      -- pass / reject / review
    hit_words_json  TEXT,                                  -- 命中词列表（脱敏后无密钥问题）
    note            TEXT,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_asset_cc_asset ON asset_compliance_checks (asset_id, result);

-- 7. 上传小店素材库记录（M3 上传链路；幂等防重复上传）
CREATE TABLE IF NOT EXISTS asset_uploads (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id             INTEGER NOT NULL REFERENCES asset_items (id),
    attempt              INTEGER NOT NULL DEFAULT 1,
    status               TEXT    NOT NULL
                         CHECK (status IN ('pending','success','failed','disabled')),
    platform_material_id TEXT UNIQUE,                      -- 成功回填；与 asset_items 对齐
    error_code           TEXT,
    evidence_json        TEXT,
    created_at           TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_asset_up_asset ON asset_uploads (asset_id, status);
```

### 关键约束说明

1. **硬规格约束**在代码层强制（DDL 不跨表校验）：`duration 5~300`、`resolution ≥720×1280`、`size ≤524288000`、`asset_type=video` 时 duration/resolution 必填——由 `materials/config.py` 常量 + 标准化器双重校验（R-M2-12）。
2. **幂等**：`asset_dedup_fingerprints.UNIQUE(fingerprint_type, fingerprint_value)` 防并发重复入库；`asset_items.platform_material_id UNIQUE` 防重复上传回填。
3. **错误码**：`asset_download_jobs.error_code` 复用全局码表（`VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/TIMEOUT/NO_MATCH/PLATFORM_REJECT/UNEXPECTED`），重试/退避策略对齐 09 文档第二节。
4. **断点续跑**：`asset_sources`（游标/账本）+ `asset_download_jobs`（next_run_at/租约）支撑进程重启自愈（`recover_after_process_restart`）。
5. **合规门禁**：入库前 `asset_compliance_checks` 必须存在 `pass` 记录且 `asset_items.compliance_status='passed'`；否则不允许对外提供（M3/M4/M5 契约）。

---

## 三、迁移记录

| 版本 | 说明 | 日期 |
|---|---|---|
| v0 | 初始 Schema 规划（7 表，SQLite 语法，暂未建库） | 2025 体系建立日 |

> 迁移纪律：v0.1 筹备阶段只规划不建库；开发阶段由总工执行 `init-db`（对齐 sourcing `python -m sourcing init-db` 模式）；任何表结构变更必须：①更新本文件 DDL；②写迁移脚本放本目录；③记入 `decisions.md` 与 `progress.md`。
