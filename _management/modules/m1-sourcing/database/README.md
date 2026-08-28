# M1 自动选品 · 模块数据库（database）

> 本模块独立数据库：**`backend/data/db/m1-sourcing.db`**（SQLite 开发库，不入 git）。
> 铁律：只操作本模块库；其他模块库（含 M5 的 `ad_report_snapshots` 所在库）**只读经交换文件**；生产切 PostgreSQL 时迁移脚本放本目录。
> ORM 定义源：`backend/sourcing/tables.py`（DDL 以其为准，本文为文档化镜像）。

---

## 〇、库文件关系说明（m1-sourcing.db vs 旧 sourcing.db）

- **旧**：基线默认 `sqlite:///sourcing.db`（backend 相对 CWD），是 39 测试时代的开发库，**尚无数据**（`backend/data/db/` 当前为空，根目录无 .db 文件）。
- **新**：任务指定 `backend/data/db/m1-sourcing.db`。S1 阶段将 `config.py` 默认值改为 `sqlite:///data/db/m1-sourcing.db`（backend CWD 相对路径），测试库用临时路径隔离。
- 关系：**同一 Schema，新库是唯一正式开发库**；旧库不迁移（无数据）。若总控要求保留旧库兼容（D-2 备选），则默认值不动，仅文档说明。

## 一、现有表（复用基线 Schema）

| 表 | 用途 | 归属 |
|---|---|---|
| `app_config` | 运行时配置（类目白名单/权重/预算上限），键值+JSON | 共享（M0 定义，**本模块只读写入经总控协调**；基线已含 `get_config_value/set_config_value`） |
| `source_board_states` | 选品账本：每(平台,榜单)游标/节流/熔断/断点 | 本模块 |
| `source_platform_states` | 平台级风控状态（risk_control/探针/登录等待） | 本模块 |
| `source_runs` | 采集批次记录 | 本模块 |
| `source_collection_events` | 单条采集事件（证据留痕） | 本模块 |
| `products` | 商品主表：来源/匹配/询价/打分/合规/入池状态全字段（`score_breakdown`/`ad_conversion` 为 JSON 列） | 本模块 |
| `product_library` | 商品库：归一化名称/指纹去重/历史表现 | 本模块 |
| `product_fingerprint_claims` | 指纹认领（防并发重复入库） | 本模块 |
| `product_source_evidence` | 来源证据（平台+榜单+item+图片） | 本模块 |
| `suppliers` | 1688 供应商 | 本模块 |
| `sku` | 逐 SKU 询价成本（挂 products） | 本模块 |

> 09 文档中 `pricing/upload_history/wechat_upload_logs/category_listing_memory` 等属于 M4/基座范围，本模块不建。

## 二、新增表（本轮：「投放转化」相关，前缀 `m1_`）

> 依据宪法第 4 节表名前缀规则 + 宪法第 5 节跨模块只读纪律：M5 的 `ad_report_snapshots` 归 M5 库所有，
> 本模块**不建同名表**，而是建**本地缓存/审计表**接收 M5 经交换文件的聚合结果（C-2）。

### 1. `m1_ad_conversion_cache` — 类目级投放转化缓存（打分输入）
```sql
CREATE TABLE IF NOT EXISTS m1_ad_conversion_cache (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category      VARCHAR(80)  NOT NULL,            -- 类目锚点（与 products.category 一致，C-1）
    roi           REAL         NOT NULL DEFAULT 0,   -- 期间托管 ROI（成交额/花费）
    sales_amount  REAL         NOT NULL DEFAULT 0,   -- 期间托管成交额（元）
    sample_count  INTEGER      NOT NULL DEFAULT 0,   -- 计入商品数（<5 弱样本，打分降权/视为无数据）
    period_start  VARCHAR(20)  NOT NULL,             -- 快照期起 YYYY-MM-DD
    period_end    VARCHAR(20)  NOT NULL,             -- 快照期止 YYYY-MM-DD
    generated_at  DATETIME     NOT NULL,             -- M5 生成时间（新鲜度判定基准，R-14）
    source_file   VARCHAR(300) NOT NULL DEFAULT '',  -- 来源交换文件（审计）
    ingested_at   DATETIME     NOT NULL,             -- 本模块导入时间
    UNIQUE (category, period_start, period_end)      -- 幂等键：同周期重复导入覆盖
);
CREATE INDEX IF NOT EXISTS idx_m1_ad_cache_category ON m1_ad_conversion_cache (category);
CREATE INDEX IF NOT EXISTS idx_m1_ad_cache_period   ON m1_ad_conversion_cache (period_start, period_end);
```

### 2. `m1_ad_conversion_ingests` — 回写导入审计（幂等/追溯）
```sql
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
```

### 3.（规划，S2 后评审）`m1_scoring_runs` — 打分批审计（可选）
- 需求：验证「投放转化维度生效」的验收（04 第五节）与打分可解释抽查。若 M0 已有 `workflow_jobs` 覆盖批次审计则复用，不重复建表（**总控裁定后定**）。

## 三、迁移记录

| 版本 | 说明 | 日期 | 状态 |
|---|---|---|---|
| v0 | 基线 Schema（sourcing 包 tables.py） | 体系建立日 | 基线含 |
| v0.1 | 新增 `m1_ad_conversion_cache` + `m1_ad_conversion_ingests` DDL 落地 | S2 | 待开发 |
| v1.0 | db 默认路径切换至 `backend/data/db/m1-sourcing.db` | S1 | 待开发 |

> 迁移脚本目录：本 `database/` 下 `migrations/`（S1 建立），脚本幂等可重入（IF NOT EXISTS + 唯一键）。

## 四、备份与数据纪律
- 库文件不入 git（宪法第 7 节）；快照导出：`database/snapshots/`（总控协调频率）。
- 生产 PostgreSQL 迁移：ORM `tables.py` 已用 SQLAlchemy 通用类型，切换 DSN 即可；`m1_` 表随迁移脚本走。
