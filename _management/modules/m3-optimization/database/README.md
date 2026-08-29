# M3 自动素材优化 · 模块数据库（database）

> 本模块独立数据库：`backend/data/db/m3-optimization.db`（SQLite 开发，不入 git）。
> 铁律：只操作本模块库；表前缀 `opt_*`；共享表（workflow_jobs / app_config / logs / ai_generation_logs）只读（归 M0）。
> 生产切 PostgreSQL 时迁移脚本放本目录（当前为 v0.1 规划稿，尚未建库）。

## 设计原则

- 表前缀 `opt_*`（optimization），避免与 M2 `asset_*` / M5 `ad_*` / 基座表冲突（宪法第 4 节）。
- 主键统一 `TEXT`（UUID 或雪花）；时间统一 UTC ISO-8601。
- 所有产出物保留「参数快照」（template_params_snapshot / plan_json），模板更新不污染历史数据。
- 跨模块引用只存 ID，不复制大字段；file_path 存相对路径，存储层归 M0/M2 管理。

## Schema（DDL 规划 v0.1）

### opt_templates —— 二创模板参数（按类目，可配置 + 重训练）

```sql
CREATE TABLE IF NOT EXISTS opt_templates (
    template_id      TEXT PRIMARY KEY,
    category         TEXT NOT NULL,                 -- 类目（对齐 M1 类目口径）
    template_name    TEXT NOT NULL,
    opening_seconds  INTEGER NOT NULL DEFAULT 3,    -- 片头秒数
    subtitle_style   TEXT NOT NULL DEFAULT '{"position":"bottom","font_size":36,"stroke":true}',
    badge_position   TEXT NOT NULL DEFAULT 'top-right',
    bgm_loudness     REAL NOT NULL DEFAULT -16.0,   -- LUFS
    cut_count        INTEGER NOT NULL DEFAULT 3,    -- 混剪片段数
    params_version   INTEGER NOT NULL DEFAULT 1,    -- 模板重训练后 +1
    status           TEXT NOT NULL DEFAULT 'active',  -- active/retired
    stats_json       TEXT,                          -- 训练统计：avg_roi/ctr/样本数
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
```

### opt_video_variants —— 视频二创版本（A/B 结构核心）

```sql
CREATE TABLE IF NOT EXISTS opt_video_variants (
    variant_id        TEXT PRIMARY KEY,
    product_id        TEXT NOT NULL,                -- 引用 M1 products（只读）
    source_asset_id   TEXT NOT NULL,                -- 引用 M2 assets（只读）
    variant_no        INTEGER NOT NULL,             -- 1..N，同商品 ≥2
    template_id       TEXT NOT NULL,                -- 引用 opt_templates
    copywrite_ids     TEXT NOT NULL,                -- JSON 数组：使用的文案候选
    template_params_snapshot TEXT NOT NULL,         -- 出片参数快照 JSON
    file_path         TEXT,                         -- 输出相对路径
    spec_check_json   TEXT,                         -- ffprobe 校验结果（分辨率/比例/时长/大小）
    spec_ok           INTEGER NOT NULL DEFAULT 0,
    compliance_json   TEXT,                         -- 规则预审结果
    review_status     TEXT NOT NULL DEFAULT 'pending',  -- pending/passed/rejected
    upload_status     TEXT NOT NULL DEFAULT 'local',     -- local/uploading/uploaded/rejected
    platform_material_id TEXT,                      -- 小店素材库 ID（M5 绑定用）
    evaluation        TEXT NOT NULL DEFAULT 'exploration',  -- 探索期/潜力/高效
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (product_id, variant_no)
);
```

### opt_image_batches —— 生图批次（M3 独立；与 09 既有 image_batches 的关系见文末「待总控裁定」）

```sql
CREATE TABLE IF NOT EXISTS opt_image_batches (
    batch_id       TEXT PRIMARY KEY,
    product_id     TEXT NOT NULL,
    image_type     TEXT NOT NULL,                   -- main/detail
    plan_json      TEXT,                            -- Kimi 规划结果快照
    target_count   INTEGER NOT NULL,
    gate_json      TEXT,                            -- 质量门禁统计
    status         TEXT NOT NULL DEFAULT 'pending', -- pending/generating/gate/reviewed/failed
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
```

### opt_images —— 主图/详情图资产

```sql
CREATE TABLE IF NOT EXISTS opt_images (
    image_id     TEXT PRIMARY KEY,
    batch_id     TEXT NOT NULL,                     -- 引用 opt_image_batches
    product_id   TEXT NOT NULL,
    image_type   TEXT NOT NULL,                     -- main/detail
    variant_no   INTEGER NOT NULL DEFAULT 1,        -- 主图 1..5 区分
    file_path    TEXT,
    phash        TEXT,                              -- 相似度去重（主图不全相同校验）
    quality_json TEXT,                              -- 门禁评分
    quality_ok   INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL DEFAULT 'pending',
    reject_reason TEXT,
    category_memory_key TEXT,                       -- 关联类目记忆
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE (batch_id, image_type, variant_no)
);
```

### opt_copywrites —— 文案（标题/口播稿/投放文案/角标）

```sql
CREATE TABLE IF NOT EXISTS opt_copywrites (
    copywrite_id  TEXT PRIMARY KEY,
    product_id    TEXT NOT NULL,
    copy_type     TEXT NOT NULL,                    -- title/script/ad/badge
    variant_no    INTEGER NOT NULL DEFAULT 1,
    content       TEXT NOT NULL,
    char_len      INTEGER NOT NULL,                 -- 标题 15~35 校验
    sku_basis_json TEXT,                            -- 口播稿 SKU 依据（防虚假承诺）
    compliance_json TEXT,                           -- 预审结果
    status        TEXT NOT NULL DEFAULT 'candidate',  -- candidate/passed/rejected/selected
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (product_id, copy_type, variant_no)
);
```

### opt_review_records —— 审核记录（闸门流水）

```sql
CREATE TABLE IF NOT EXISTS opt_review_records (
    review_id     TEXT PRIMARY KEY,
    target_type   TEXT NOT NULL,                    -- video/image/copywrite/material
    target_id     TEXT NOT NULL,                    -- variant_id/image_id/copywrite_id/asset_id
    gate_type     TEXT NOT NULL,                    -- rule/evaluate/manual/relevance
    result        TEXT NOT NULL,                    -- pass/reject/manual_review
    reasons_json  TEXT,
    reviewer      TEXT,                             -- system/human/<agent-id>
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opt_review_target ON opt_review_records(target_type, target_id);
```

> v1.1 增量（REC-迁移-03 C3 素材相关性门）：`gate_type=relevance`（target_type=material、
> target_id=M2 asset_id，reasons_json 留判定证据：verdict/confidence/frames/clustering/
> manual_note「多款式需人工确认目标款，禁止自动创建衍生商品」）；判定三态
> related（result=pass 放行）/ unrelated（result=reject 淘汰）/ multi_style
> （result=manual_review 人工确认）。契约见 data-audit DA-010 与
> `_management/data-exchange/m2-m3-m4-relevance-gate.json`。

### opt_category_memory —— 类目记忆（生图/模板策略经验）

```sql
CREATE TABLE IF NOT EXISTS opt_category_memory (
    category       TEXT PRIMARY KEY,
    pass_count     INTEGER NOT NULL DEFAULT 0,      -- 人工通过数
    reject_count   INTEGER NOT NULL DEFAULT 0,      -- 平台拒审数
    reject_reasons_json TEXT,                       -- 拒审原因统计
    image_strategy_json TEXT,                       -- 生图策略参数（按经验调整）
    template_stats_json TEXT,                       -- 模板参数训练结果
    updated_at     TEXT NOT NULL
);
```

### opt_evaluation_feedback —— 评估回写（A/B 闭环）

```sql
CREATE TABLE IF NOT EXISTS opt_evaluation_feedback (
    feedback_id      TEXT PRIMARY KEY,
    variant_id       TEXT NOT NULL,                 -- 关联 opt_video_variants
    platform_material_id TEXT,
    report_date      TEXT NOT NULL,                 -- 回写归属日（UTC）
    exposure         INTEGER NOT NULL DEFAULT 0,
    clicks           INTEGER NOT NULL DEFAULT 0,
    spend            REAL NOT NULL DEFAULT 0,       -- 元
    orders           INTEGER NOT NULL DEFAULT 0,
    roi              REAL NOT NULL DEFAULT 0,
    diagnosis_json   TEXT,                          -- 平台诊断回读
    score            REAL NOT NULL DEFAULT 0,       -- 素材评分 = f(ROI, CTR, 诊断)
    evaluation       TEXT NOT NULL DEFAULT 'exploration',
    stale            INTEGER NOT NULL DEFAULT 0,    -- 无新数据标记
    created_at       TEXT NOT NULL,
    UNIQUE (variant_id, report_date)
);
```

### opt_upload_records —— 小店素材库上传记录

```sql
CREATE TABLE IF NOT EXISTS opt_upload_records (
    upload_id      TEXT PRIMARY KEY,
    target_type    TEXT NOT NULL,                   -- video/image
    target_id      TEXT NOT NULL,
    batch_no       INTEGER NOT NULL DEFAULT 1,      -- 上传批次（≤50/批）
    mode           TEXT NOT NULL,                   -- api/ui（待定）
    status         TEXT NOT NULL,                   -- pending/uploading/uploaded/failed
    error_code     TEXT,                            -- 复用错误码表
    platform_material_id TEXT,
    platform_evaluation TEXT,                       -- 平台评估标签
    evidence_json  TEXT,                            -- 留证据（页面截图/响应）
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
```

## 迁移记录

| 版本 | 说明 | 日期 |
|---|---|---|
| v0 | Schema 规划稿（尚未建库） | 2025 体系建立日 |
| v1 | （待开发期）首版 DDL 落地 + init-db | — |
| v2 | （待集成期）PostgreSQL 迁移脚本 | — |

## 与其他模块库的关系

- `assets`（M2 拥有）：只读引用 source_asset_id / platform_material_id；assets.evaluation 同步由总控协调，M3 不直写。
- `products`（M1 拥有）：只读引用 product_id。
- `workflow_jobs` / `app_config` / `logs` / `ai_generation_logs`（M0 拥有）：只读；生成任务入队走总控协调的 WorkflowJob。

## 待总控裁定（已登记 decisions.md）

1. **09 文档既有表 `image_batches` / `image_assets`（列为「现有/复用」）与 M3 生图职责的归属**：生图代码按 03 文档归 M3 复用（image_generation.py/image_review.py），但该表若归 M1 则 M3 应只读引用；若归 M3 则应接管迁移。当前规划 M3 自建 opt_image_batches / opt_images，裁定后按结论调整。
2. **小店素材库上传 OpenAPI 可用性**：决定 M3_UPLOAD_MODE 默认值（api/ui）与 UI 兜底链路是否启用。
