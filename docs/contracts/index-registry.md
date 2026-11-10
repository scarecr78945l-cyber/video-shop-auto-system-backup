# index-registry.md — P0-0 批 B 契约：索引注册表

> 来源：`15-数据字典.md` v6（round-16 冻结）+ round-18 §2.7（普通非唯一索引需独立注册；PostgreSQL 不自动为 FK 建索引）。
> 用途：P0-1 T3（31 表 schema）G9 阶段索引生成的唯一依据；列名/索引名在此冻结后进入 migration。

---

## 一、约定

- 索引命名：`ix_<表>_<列组合>`（普通），`uq_<表>_<列组合>`（唯一），`px_<表>_<列组合>`（部分唯一）；`ex_<表>_<约束名>`（排他，由 ddl-order G8 生成，不入本表）。
- 本注册表只列**显式创建的索引**；`UNIQUE(tenant_id,id)` 父候选键、组合 FK 隐含约束见 `ddl-order.md`。
- 15 个部分唯一索引（round-16 断言）是 P0-1 验收基线；普通查询/FK/队列索引按本表冻结。
- 删除顺序：逆注册顺序（与 downgrade 边界一致）。

---

## 二、15 个部分唯一索引（P0-1 验收 exact-set=15）

| # | 表 | 索引名 | 列 | WHERE | 语义 |
|---|---|---|---|---|---|
| 1 | tenants | px_tenants_name | (name) | deleted_at IS NULL | 主体名软删唯一 |
| 2 | platform_accounts | px_accounts_platform_key | (tenant_id, platform, account_key) | deleted_at IS NULL | 账号平台键 |
| 3 | shops | px_shops_account_shop | (account_id, platform_shop_id) | deleted_at IS NULL | 账号内店铺唯一 |
| 4 | account_runtime_profiles | px_profiles_active | (account_id, purpose) | status='active' | 同账号每用途一个 active |
| 5 | credential_refs | px_creds_valid | (account_id, purpose) | status='valid' | 同账号每用途一个有效凭证 |
| 6 | suppliers | px_suppliers_code | (tenant_id, supplier_code) | deleted_at IS NULL | 本地业务键 |
| 7 | suppliers | px_suppliers_platform | (tenant_id, source_platform, platform_supplier_id) | deleted_at IS NULL AND platform_supplier_id IS NOT NULL | 平台键 |
| 8 | products | px_products_title | (tenant_id, title_base) | deleted_at IS NULL | 标题软删唯一 |
| 9 | supplier_offers | px_offers_preferred | (sku_id, preferred_status) | preferred_status='current' | 每 SKU 一个当前首选 |
| 10 | assets | px_assets_sha256 | (tenant_id, content_sha256) | deleted_at IS NULL | 字节去重键 |
| 11 | shop_listings | px_listings_shop_product | (shop_id, product_id) | deleted_at IS NULL | 一店一商品一条 |
| 12 | shop_listings | px_listings_platform_product | (tenant_id, platform_product_id) | platform_product_id IS NOT NULL AND deleted_at IS NULL | 平台商品键 |
| 13 | ad_campaigns | px_campaigns_platform | (shop_listing_id, platform_campaign_id) | platform_campaign_id IS NOT NULL AND deleted_at IS NULL | 平台计划键 |
| 14 | manual_tasks | px_tasks_open | (tenant_id, ref_type, ref_id, task_type) | status IN ('pending','in_progress') | 同对象同类型一个开放任务 |
| 15 | alert_events | px_alerts_open | (tenant_id, fingerprint) | status <> 'resolved' | 开放 incident 唯一 |

---

## 三、普通查询/队列索引（round-33 B4 回修：仅保留需显式创建的）

> round-32 确认 N3/N6/N8/N9/N11/N13/N15 已被既有完整 UNIQUE/UNIQUE NULLS NOT DISTINCT 的**左前缀或同列组合**覆盖，另建只会增加写放大与对象数——改为 `covered_by_constraint` 映射，不创建独立索引。**普通索引 CREATE exact-set 为下表 N1/N2/N4/N5/N7/N10/N12/N14 共 8 项**（不再机械锁死 15）。

### 3.1 显式创建（8 项）

| # | 表 | 索引名 | 列 | 用途 |
|---|---|---|---|---|
| N1 | workflow_steps | ix_steps_status_updated | (status, updated_at) | 隐式租约 claim/recover（SKIP LOCKED 候选扫描） |
| N2 | workflow_runs | ix_runs_status_updated | (status, updated_at) | 流程状态扫描 |
| N4 | manual_tasks | ix_tasks_status | (status) | 待处理人工任务扫描 |
| N5 | alert_deliveries | ix_deliveries_pending | (status) | 待发送投递扫描 |
| N7 | ad_report_snapshots | ix_snaps_window | (window_start, window_end) | 报表窗口查询（决策窗口/两次回读） |
| N10 | selection_decisions | ix_decisions_state | (state) | 选品状态扫描（material_ready/listing_ready 池） |
| N12 | ad_campaigns | ix_campaigns_listing | (shop_listing_id) | 店级计划查询（组合 FK 引用；平台部分唯一索引不含 NULL 行，需独立索引） |
| N14 | audit_events | ix_audit_actor_time | (actor_id, created_at) | 审计查询 |

### 3.2 covered_by_constraint 映射（7 项，不创建）

| 原 N | 表 | 计划列 | 已有约束 | 覆盖关系 |
|---|---|---|---|---|
| N3 | workflow_steps | (run_id) | UNIQUE(run_id, step_type, attempt) | 左前缀 |
| N6 | alert_deliveries | (alert_event_id) | UNIQUE(alert_event_id, channel, notification_type, attempt) | 左前缀 |
| N8 | ad_report_snapshots | (campaign_id) | UNIQUE NULLS NOT DISTINCT(campaign_id, ...) | 左前缀 |
| N9 | roi_feedback_events | (source_snapshot_id) | UNIQUE(source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version) | 左前缀 |
| N11 | selection_decisions | (tenant_id, selection_batch_key) | UNIQUE(tenant_id, selection_batch_key, product_id) | 左前缀 |
| N13 | shop_listing_skus | (shop_listing_id) | UNIQUE(shop_listing_id, sku_id) | 左前缀 |
| N15 | workflow_steps | (tenant_id, action_idempotency_key) | UNIQUE(tenant_id, action_idempotency_key) | 同列组合（完全重复） |

---

## 四、验证方式（round-33 B3 回修：FK 两端区分）

1. **exact-set=15**：`pg_catalog.pg_indexes` 按 schema 查询部分唯一索引，缺失=0、多余=0（不变）；
2. **显式普通索引**：N1/N2/N4/N5/N7/N10/N12/N14 共 8 项存在；
3. **FK 被引用端**：58 组合 FK 的被引用侧由 **17 个父候选键 `UNIQUE(tenant_id,id)`** 满足（58/58，round-32 §4.2 确认），此声明成立；
4. **FK 引用端（子表侧）**：PostgreSQL 不自动为引用列建索引。round-32 机械检查引用端有效前缀覆盖 14/58、未覆盖 44/58；本注册表**只覆盖经说明的高频路径**（N1/N2/N4/N5/N7/N10/N12/N14 + covered_by_constraint 7 项），**不承诺 58 引用端全覆盖**——缺失索引的查询按需经 Codex diff 补入，禁止静默新增；
5. **命名唯一**：索引名无冲突；
6. 索引创建在 G9（排他约束之后），删除在 downgrade 先于 exclusion。

---

## 五、变更规则

- 新增/删除普通索引：须更新本表 + P0-1 migration，且经 Codex diff；不改 15 部分唯一 exact-set 断言；
- covered_by_constraint 项若因约束删除而失效，须先回本表登记为显式创建后再删约束（保持查询路径不中断）。
