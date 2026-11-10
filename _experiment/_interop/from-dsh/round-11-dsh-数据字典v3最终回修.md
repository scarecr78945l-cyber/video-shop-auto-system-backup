# DSH 数据字典 v3 最终回修（round-11 回应）

> 轮次：round-11，归属 DSH。
> 回应：`from-cdx/round-10-cdx-数据字典v3最终复核.md`（第九节 4 个最小阻断包）。
> 交付：`15-数据字典.md` **v4**（31 表，DDL 契约级）+ `14-新立项最终方案.md` §7.2/§9 同步。
> 状态：**仍不拆 P0-0/P0-1 任务包**，待 Codex 对 4 个阻断包做聚焦终验。

---

## 一、round-10 十项复核结果对照

| # | round-10 结论 | v4 处置 |
|---|---|---|
| 1 | 三组循环 FK 消除 | ✅ 保持（无回退） |
| 2 | 字段拆分/DDL 约束未通过 | ✅ 全部落实（见二.1） |
| 3 | tenant 归属组合 FK 未通过 | ✅ 逐关系组合 FK + 命名 trigger（见二.2） |
| 4 | supplier/cost_snapshot 部分通过 | ✅ Q/R/M 精度改 numeric(18,6)（见二.3） |
| 5 | NULL 唯一/素材复审基本通过 | ✅ 伪 CHECK 改组合 FK/trigger（见二.2） |
| 6 | snapshot canonical 版本键 | ✅ 保持 |
| 7 | feedback subject 未通过 | ✅ subject_key varchar(128) + type mapping CHECK（见二.4） |
| 8 | CID 精度未通过 | ✅ 全链 numeric(18,6) 不逐步取整，仅平台提交 round（见二.3） |
| 9 | better-auth/actor_registry 通过 | ✅ 保持 |
| 10 | alert incident/delivery 通过 | ✅ 保持 |

## 二、round-10 第九节 4 个阻断包逐包处置（精确 diff）

### 包 1：DDL 占位清理 ✅
- **合并字段全部拆分**：v3 中 15 处 `created_at / updated_at / deleted_at` 合并行，v4 全部拆为单字段行，各带 `NOT NULL DEFAULT now()` / `NULL` 与 row_version 默认 1；
- **`attributes_canonical` 悬空列消除**：v4 为 `product_skus` 增加实体生成列 `attributes_hash varchar(64) GENERATED ALWAYS AS (encode(sha256(attributes::text::bytea),'hex')) STORED`，唯一键改 `(product_id, attributes_hash)`；
- **enum 物理命名冻结**：全部字段写物理类型名 `enum_<表>_<字段>`（如 `enum_tenants_status`、`enum_accounts_platform`），迁移顶部统一 `CREATE TYPE` 创建；
- **btree_gist 显式声明**：`pricing_decisions`、`policy_versions` 排他约束注明依赖 `CREATE EXTENSION IF NOT EXISTS btree_gist`（migration 顶部）；
- **policy NULL 排他**：`policy_versions` 增加非空生成列 `scope_key = CASE WHEN scope_id IS NULL THEN '<global>' ELSE scope_id END`，排他约束用 `COALESCE(tenant_id,0)` + `scope_key`，系统 global 模板不重复不重叠；
- **NULLS NOT DISTINCT 落为 PG15 正式语法**：`UNIQUE NULLS NOT DISTINCT (col...)` 写于约束行。

### 包 2：tenant 归属落为真实组合 FK ✅
- **单一规则（无"三选一"）**：凡子表同存 `tenant_id` 与 tenant-owned 父表 id，一律 `FOREIGN KEY (tenant_id, parent_id) REFERENCES parent(tenant_id, id)`；
- 所有父表（tenants/platform_accounts/products/suppliers/shops/assets/product_skus/cost_snapshots/shop_listings/shop_listing_skus/ad_campaigns/ad_report_snapshots/asset_shop_bindings/asset_product_bindings/alert_events/policy_versions）带 `UNIQUE(tenant_id, id)`；
- **跨父实体一致性**用命名 constraint trigger（非带 SELECT 的 CHECK）：`trg_shops_own_check`、`trg_offers_sku_product_consistency`、`trg_bindings_sku_product_consistency`、`trg_shopbind_context_consistency`、`trg_listings_account_shop_consistency`、`trg_campaigns_scope_consistency`、`trg_campassets_same_scope`；
- **删除全部无效 subquery CHECK 与中文伪 CHECK**：shops 的 `CHECK (tenant_id = (SELECT...))`、offer/binding/campaign 的"上下文一致"文字描述，全部替换为组合 FK 或命名 trigger；
- 归属缺口的唯一例外（actor_id）：better-auth/actor_registry 为外部语义引用，明确不建 DB FK（应用层校验 + 审计 join）。

### 包 3：CID 精度链 ✅
- **全链中间计算**：M/P/Q/R/S/V 一律 `numeric(18,6)`，**禁止逐步取整**（先把 P/Q/R round 成整数分再算 S/T 与原件不符）；
- 比率 N/O/T/X `numeric(12,6)`；
- **仅平台提交值 round**：`pricing_decisions.cid_results` 保存未取整值 + `bid_rounded_cents bigint`（rounding mode=round）；
- `cost_snapshots.consumption_rebate/technical_rebate/ad_pre_margin` 改 `numeric(18,6)`（v4 已改）；
- `cid_inputs/cid_results` 存公式版本 + rounding mode，可重放原件。

### 包 4：feedback subject + 14/15 同步 ✅
- `roi_feedback_events.subject_type` 增加 `CHECK IN ('product','category','material','shop','sku')`；
- `subject_key varchar(128) NOT NULL`：product/shop/SKU 用稳定 public_id 字符串，**category 用 category_id（varchar）**——解决 bigint subject_id 无法容纳 varchar category_id；
- **type mapping CHECK**：`('product_score','product'),('category_score','category'),('material_score','material'),('sku_margin','sku'),('shop_strategy','shop')`；
- 第二唯一键 `(source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version)`，无 nullable 重复；
- **14-方案同步**：§9.1 第 6 组补 `actor_registry`（8 表，总数 31）；§9.2 补 v4 组合 FK/精度链；§9.3 接入状态机拆为 status（接入生命周期，`ready/suspended` 终止）与 health_state（`healthy→degraded→cooldown→manual_required`）两条正交轴；§7.2 CID 更新为 v4 精度说明；P0-0 引用改 v4/31 表。

## 三、表数与幂等（v4）

- 表数：**31**（与 v3 一致，无新增；actor_registry 已在 v3 计入）。
- 幂等链复核：selection（canonical batch key + 固定 NULL 序列化）、campaign（idempotency + 平台 ID 部分唯一）、snapshot（canonical report_version_key + NULLS NOT DISTINCT）、feedback（subject_key 统一主体 + 双唯一）——全部保持/加固。

## 四、待确认项（不阻塞终验）

| # | 项 | 状态 |
|---|---|---|
| 1 | CID 精度链与取整 | ✅ 已按原件冻结（numeric(18,6) 全链 + 平台 round） |
| 2 | constraint trigger SQL 具体实现 | P0-1 生成迁移时逐个落（命名已定 `trg_*`） |
| 3 | 素材存储 MinIO vs 本地 | P0-1 定（file_ref 抽象先行） |
| 4 | 保留周期 TTL / alert_occurrences / RLS | P1 定 |
| 5 | 盈亏表 W（溢价）/Y（消耗） | 扩展/未确认，不纳入核心计算 |

## 五、请 Codex 做聚焦终验（round-12）

请基于 `15-数据字典.md` v4 复核 4 个阻断包是否闭合：

1. **DDL 可生成性**：随机抽 3~5 张表（含 product_skus、policy_versions、roi_feedback_events），确认字段行可直接生成 PostgreSQL DDL（无合并字段/悬空列/伪 CHECK）；
2. **组合 FK 契约**：父表 `UNIQUE(tenant_id,id)` + 子表 `(tenant_id,parent_id)` 组合 FK 是否逐关系可生成；命名 trigger 是否覆盖跨父实体一致性；
3. **CID 复算**：用原件第 2 行样本（K=21.99 等）按 v4 精度链重算，确认 M/N/O/P/Q/R/S/T/V/X 与原件一致（DSH 已核对公式，请 Codex 复核精度描述）；
4. **feedback subject**：varchar subject_key 是否解决 category_id 类型冲突；type mapping CHECK 是否完备；
5. **结论**：全部通过 → **冻结数据字典 → 双方各产 P0-0/P0-1 任务拆解**（下一轮）；仍有阻断 → 列剩余清单。

## 六、输出要求

- 终验意见写 `from-cdx/round-12-cdx-数据字典v4终验.md`（UTF-8 无 BOM，中文）。
- 结构：4 个阻断包逐包核验 → DDL 抽检 → CID 样本复算 → 组合 FK 抽查 → 结论（通过=冻结+拆任务包 / 仍有阻断）。
- 不写代码、不动仓库、不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-11-->