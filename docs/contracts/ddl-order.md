# ddl-order.md — P0-0 批 B 契约：DDL 生成顺序

> 来源：`15-数据字典.md` v6（round-16 冻结）+ round-18 §2（Codex 独立顺序图）+ round-19 §二（DSH 合并裁决，采纳 Codex 版）。
> 基线：round-16 机械断言（60 enum/31 表/17 父键/58 FK/4 NULLS/17 trigger/2 exclusion/15 partial；reciprocal FK=0）。
> 用途：P0-1 T1~T4（Alembic migration）唯一生成顺序输入。

---

## 一、顺序原则（冻结）

1. **PostgreSQL 版本**：`server_version_num >= 150000`（4 处 `UNIQUE NULLS NOT DISTINCT` 的语法前提）。
2. **命名空间（round-33 B1 冻结取值，非"固定"动词）**：
   - `business_schema = app`（业务 31 表全部置于该 schema，不混入 public）；
   - `search_path = app, pg_catalog`（有序；migration 内显式 `SET search_path TO app, pg_catalog`，不依赖进程级默认）；
   - `migration_role = ${MIGRATION_ROLE}`（环境变量，**启动时必填门禁**：缺失即拒绝执行迁移；部署文档须给出该 role 的 CREATE SCHEMA/DDL 权限基线）；
   - `pg_catalog` exact-set 断言一律限定 `business_schema = app`；
   - better-auth schema/version 由批 C `auth-boundary.md` 冻结，不属本取值。
3. **事务**：迁移在单一事务或明确可恢复分段事务中；每 revision 带 upgrade/downgrade。
4. **FK 关系说明**：字段行 `parent_id FK→parent.id` 是关系说明；tenant-owned 父表只生成冻结的组合 FK `(tenant_id,parent_id) REFERENCES parent(tenant_id,id)`，不重复生成单列 parent FK。
5. **基础 FK 与组合 FK 分开统计**：`tenant_id → tenants.id` 基础 FK 与 58 业务组合 FK 分开；`policy_versions.tenant_id` 按 v6 原文处理（NULL=global 模板）。
6. **父候选键先于组合 FK**：17 个 `UNIQUE(tenant_id,id)` 先于 58 条组合 FK；被 trigger 查询的表/键/约束先于 trigger 安装。
7. **better-auth 表**：users/tenant_members 不属 31 业务表、不计 60 enum；迁移所有权按 `auth-boundary.md`（Alembic 唯一部署入口应用其 schema snapshot）。
8. **普通非唯一索引**：PostgreSQL 不自动为 FK 建索引；普通索引由 `index-registry.md` 冻结，不属本顺序图内联。

---

## 二、正向 DAG（G0~G11，冻结）

```text
G0 预检/命名空间
  ├─ PostgreSQL server_version_num >= 150000
  ├─ business_schema = app；search_path = app, pg_catalog；migration_role = ${MIGRATION_ROLE}（启动必填门禁）
  └─ 确认 better-auth schema/revision 快照与业务 graph 边界
       ↓
G1 扩展
  └─ CREATE EXTENSION IF NOT EXISTS btree_gist
       ↓
G2 类型
  └─ 严格按 enum-registry.yaml（60 项）顺序 CREATE TYPE
       ↓
G3 31 表骨架
  ├─ 列、PK、identity、NOT NULL、DEFAULT、generated column、普通 CHECK
  ├─ public_id 等非依赖 UNIQUE
  └─ 依赖顺序见 §三（W0~W8）
       ↓
G4 父候选键
  └─ 17 × UNIQUE(tenant_id,id)
       ↓
G5 关系约束
  ├─ tenant_id → tenants.id 基础 FK（按 v6 各表明示项）
  ├─ 58 × (tenant_id,parent_id) 组合 FK
  └─ 自引用 FK（assets.derived_from、policy.supersedes）在父表及父候选键存在后添加
       ↓
G6 业务唯一性
  ├─ 普通完整 UNIQUE
  └─ 4 × UNIQUE NULLS NOT DISTINCT
       ↓
G7 校验函数与 trigger
  └─ 每项先 CREATE FUNCTION，后 CREATE TRIGGER；17 项，顺序见 §五
       ↓
G8 排他约束
  ├─ pricing_decisions 当前批准区间
  └─ policy_versions 同 scope 生效区间
       ↓
G9 索引
  ├─ 15 个部分唯一索引（index-registry.md 列名）
  └─ index-registry.md 普通查询/FK/队列索引
       ↓
G10 种子与 fixtures
  ├─ actor_registry：system/worker/service
  ├─ CID global policy（policy_versions cid_breakeven v5）
  ├─ 错误码应用注册表加载/校验（16 项，非第 61 个 PG enum）
  └─ CID 第 2 行 fixture；mode=fixtures，不标真实平台能力
       ↓
G11 机械断言 + 行为测试 + revision 打标
```

> round-19 采纳 Codex 顺序：在 17 trigger 前补普通/NULL 唯一（G6），在排他约束后补普通索引与种子（G9/G10）；排他约束与部分唯一索引之间无语义依赖，保持 DSH 顺序便于合并。

---

## 三、31 表依赖序（W0~W8，冻结）

| 波次 | 建表顺序 | 说明 |
|---|---|---|
| W0 | tenants → actor_registry → policy_versions | 根、actor 本地注册、global/tenant policy；policy 自引用 FK 后装 |
| W1 | platform_accounts → shops → account_runtime_profiles → credential_refs | 账号/店铺链；shops 的 policy 校验后装 trigger |
| W2 | suppliers → products → product_skus → supplier_offers | 供应链与商品父链 |
| W3 | assets → shop_listings → shop_listing_skus | assets 自引用后装；listing 先于多个上下文表 |
| W4 | asset_product_bindings → asset_shop_bindings → asset_reviews | 店铺素材绑定依赖商品绑定/listing；review 多态引用不生成 DB FK |
| W5 | cost_snapshots → workflow_runs → workflow_steps → selection_decisions | cost 依赖 offer/shop/listing；selection 依赖 cost/run |
| W6 | pricing_decisions → listing_events | pricing 依赖 listing_sku/cost；事件依赖 listing |
| W7 | ad_campaigns → ad_campaign_assets → ad_report_snapshots → roi_feedback_events | 投放、素材、事实快照、回写严格串联 |
| W8 | manual_tasks → audit_events → alert_events → alert_deliveries | 治理/审计/告警；manual 多态引用不生成 DB FK |

> 即使 G5 延迟安装 FK，仍保持此顺序，便于单表回滚、审阅与未来将安全约束内联。

---

## 四、17 父候选键（G4，exact-set 冻结）

```text
platform_accounts, shops,
suppliers, products, product_skus, supplier_offers, cost_snapshots,
assets, asset_product_bindings, asset_shop_bindings,
shop_listings, shop_listing_skus,
ad_campaigns, ad_report_snapshots,
workflow_runs, policy_versions, alert_events
```

---

## 五、58 条组合 FK 分组（G5，验收基线）

| 子表 | 数量 | 子表 | 数量 |
|---|---:|---|---:|
| shops | 1 | account_runtime_profiles | 1 |
| credential_refs | 1 | product_skus | 1 |
| supplier_offers | 3 | cost_snapshots | 3 |
| selection_decisions | 4 | assets | 2 |
| asset_product_bindings | 3 | asset_shop_bindings | 5 |
| asset_reviews | 1 | shop_listings | 3 |
| shop_listing_skus | 2 | pricing_decisions | 4 |
| listing_events | 1 | ad_campaigns | 3 |
| ad_campaign_assets | 2 | ad_report_snapshots | 7 |
| roi_feedback_events | 8 | workflow_steps | 1 |
| policy_versions | 1 | alert_deliveries | 1 |
| **合计** | **58** | | |

> FK 创建顺序按父表组排序；删除顺序严格反向。`assets`、`policy_versions` 自引用 FK 归入 58。
> global policy 例外（v6 §9）：对 `policy_versions` 的引用**不用组合 FK**，改用命名普通 trigger「同 tenant 或 global」；polymorphic 引用分类（round-33 B2 冻结 + round-35 修正，避免相反指令）：
> - `cost_snapshots.decision_object_type/id`：不生成 DB FK，由已登记命名 trigger `trg_cost_context_consistency`（17 trigger exact-set 内）+ 应用层断言校验；
> - **`manual_tasks.ref_type/ref_id`：仅应用层断言 + 审计，不新增任何 DB trigger**（v6 §9 冻结处理；17 trigger 中无其他 manual 相关 trigger——唯一的 `trg_manual_policy_ref` 只校验 policy_version_id，不校验 polymorphic ref）；
> - **`asset_reviews.review_scope/scope_ref_id`：仅应用层断言，不新增任何 DB trigger**（round-18 冻结裁决；详见 §五 边界）。
> - 全文不得出现任何 manual 通配 trigger 名（以 `trg_manual` 开头的通配/占位写法）；17 trigger exact-set/顺序保持不变。

---

## 六、17 个 trigger 安装顺序（G7，冻结）

```text
1. trg_policy_supersede_scope
2. trg_shops_policy_ref
3. trg_cost_policy_ref
4. trg_selection_policy_ref
5. trg_pricing_policy_ref
6. trg_campaigns_policy_ref
7. trg_manual_policy_ref
8. trg_offers_sku_product_consistency
9. trg_bindings_sku_product_consistency
10. trg_listings_account_shop_consistency
11. trg_cost_context_consistency
12. trg_shopbind_context_consistency
13. trg_pricing_context_consistency
14. trg_campaigns_scope_consistency
15. trg_campassets_same_scope
16. trg_snapshots_dimension_consistency
17. trg_feedback_dimension_consistency
```

- 每个函数/trigger 具名；每个错误通过 SQLSTATE + 稳定错误码（error-codes.yaml 16 项）输出；测试不得依赖完整自然语言错误文本。
- 全部为普通 `BEFORE ... FOR EACH ROW` trigger（非 constraint trigger）；policy 引用 trigger 事件含 `tenant_id`（见 v6 §8）。
- **边界（冻结）**：`asset_reviews.scope_ref_id` 按「应用层断言，无新增 DB trigger」解释；**禁止生成第 18 个 trigger**。

---

## 七、特殊唯一性与排他约束（G6/G8）

- **4 × `UNIQUE NULLS NOT DISTINCT`**：asset_product_bindings、asset_shop_bindings、ad_report_snapshots、policy_versions（PG15 正式语法，关键字在列清单前）。
- **2 × exclusion**：pricing_decisions（单 SKU 单当前生效，`WHERE status='approved'`）、policy_versions（同 scope 生效区间，`COALESCE(tenant_id,0)` + scope_key）；均在 `btree_gist` 后创建。
- **15 × 部分唯一索引**：见 `index-registry.md`（14 条表内 WHERE 记录 + tenants.name 1 条）。

---

## 八、downgrade 与回滚边界（冻结）

```text
删 fixtures/seed
→ 删普通/部分唯一索引
→ 删 exclusion
→ DROP TRIGGER（逆序）
→ DROP FUNCTION（逆序）
→ 删普通/NULL 唯一和 58 组合 FK（先 58 组合 FK，再其依赖的 17 父候选键）
→ 删 17 父候选键
→ DROP TABLE（W8→W0，先子后父）
→ DROP TYPE（60 enum 注册表逆序）
→ btree_gist 仅在"本 migration 确认创建且无外部依赖"时删除（预存扩展默认保留；禁止 DROP EXTENSION ... CASCADE）
```

- downgrade 是开发/空库演练能力，不等价于线上有数据场景的自动回退；
- 已发生外部平台写入时，schema downgrade 不承担平台补偿（由 T1 补偿动作和 reconciliation 负责）；
- migration 开始前记录 schema/version/扩展所有权；禁止 CASCADE 掩盖悬空依赖。

---

## 九、自检断言（G11，P0-1 验收基准）

| 断言 | 期望 |
|---|---:|
| enum exact set（v6 §0.3 / enum-registry.yaml） | 60，缺失=0，多余=0 |
| 业务表 exact set | 31，缺失=0，多余=0 |
| `UNIQUE(tenant_id,id)` exact set | 17 |
| 组合 FK | 58 |
| 组合 FK 父候选键缺失 | 0 |
| reciprocal FK | 0 |
| `UNIQUE NULLS NOT DISTINCT` | 4，旧语法=0 |
| 普通 `BEFORE ... FOR EACH ROW` trigger | 17 |
| 非 BEFORE/constraint trigger | 0 |
| policy trigger 未覆盖 tenant_id 更新 | 0 |
| exclusion | 2 |
| 部分唯一索引 | 15 |

> 数据库验收必须按 schema + exact names 查询 `pg_catalog`，不能使用 `typname LIKE 'enum_%'` 或全库表数这类会被旧对象污染的计数（round-18 §2.9）。
