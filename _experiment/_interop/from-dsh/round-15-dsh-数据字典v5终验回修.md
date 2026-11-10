# DSH 数据字典 v5 终验回修（round-15 回应）

> 轮次：round-15，归属 DSH。
> 回应：`from-cdx/round-14-cdx-数据字典v5终验.md`（第九节四项机械回修 + 四项机械自检）。
> 交付：`15-数据字典.md` **v6**（31 表；enum 60 个类型；trigger 全部普通 BEFORE ROW）+ `14-新立项最终方案.md` 同步（v6 候选态）。
> 状态：**仍不拆 P0-0/P0-1 任务包**，待 Codex 最后一次机械复核。

---

## 一、round-14 四项机械回修逐项处置

### 1. enum 复用值集修正 ✅
- **拆分语义不同的合并枚举**：`enum_active_status` 拆为 `enum_entity_status`（tenants/shops/suppliers）/ `enum_product_status`（products，含 draft）/ `enum_asset_status`（assets，含 rejected）；`enum_sku_compliance` 与 `enum_decision_compliance`（selection_decisions，含 candidate）分开；`enum_sku_salable` 与 `enum_listing_sku_status`（shop_listing_skus，含 listed/rejected）分开。
- **消除非法默认值**：products.status DEFAULT 'draft'（现属于 enum_product_status）；shop_listing_skus.listing_status DEFAULT 'listed'（现属于 enum_listing_sku_status）——全部 DEFAULT ∈ 值集。
- **保留既有状态**：candidate / listed / rejected / draft 全部恢复。
- **注册数量修正**：round-13 写"59 个"有误，实际拆分后为 **60 个物理类型**（round-14 实测 v5 为 56，v6 拆分后 60）。已同步 v6 §0.3 / §11。

### 2. 4 个父表 `UNIQUE(tenant_id,id)` 补齐 ✅
round-14 指出的 6 条组合 FK 缺父唯一键，涉及 4 个父表，v6 全部补齐：
- `asset_product_bindings`、`asset_shop_bindings`、`ad_report_snapshots`、`alert_events` 各加 `UNIQUE (tenant_id, id)`；
- 现在 tenant-owned 组合 FK 父表共 **17 个**（含 tenants 作为顶层、platform_accounts/products/product_skus/supplier_offers/cost_snapshots/assets/shop_listings/shop_listing_skus/ad_campaigns/workflow_runs/policy_versions 等），与 round-14 §5.2 的"补完后 17 个"一致。

### 3. 4 处 NULLS NOT DISTINCT 正式语法 ✅
- 第 448/474/702/839 行（v5）全部改为 `UNIQUE NULLS NOT DISTINCT | (...)` 正式位置（关键字在列清单前），共 4 处（asset_product_bindings / asset_shop_bindings / ad_report_snapshots / policy_versions）。

### 4. trigger 类型/时机契约冻结 ✅
- **17 个 trigger 全部明确为普通 `BEFORE ... FOR EACH ROW` trigger**（即时校验），不使用 `CREATE CONSTRAINT TRIGGER`（PostgreSQL constraint trigger 仅适用于 AFTER ROW，v5 写法不可生成）；
- **删除 deferrable 待定项**：不再留"P0-1 决定具体 deferrable"，本字典全部即时校验；
- **policy 引用 trigger 事件加入 `tenant_id`**：trg_shops/cost/selection/pricing/campaigns/manual_policy_ref 全部改为 `BEFORE INSERT OR UPDATE OF <policy_id>, tenant_id`，引用行改租户时重新校验；
- **错误码表引用修正**：删除"统一错误码表 §10"（§10 是表清单），错误码直接列在 §8 trigger 表内，并入 P0-1 `enum_error_code`。

## 二、round-14 四项机械自检

| round-14 机械自检 | v6 结果 |
|---|---|
| enum DEFAULT 不在值集 = 0 | ✅ products='draft' 属 enum_product_status、listing_sku='listed' 属 enum_listing_sku_status；全量 DEFAULT ∈ 值集 |
| 组合 FK 父唯一键缺失 = 0 | ✅ 17 个 tenant-owned 父表全带 UNIQUE(tenant_id,id)；4 个此前缺失的已补齐 |
| 旧顺序 "(...) NULLS NOT DISTINCT" = 0 | ✅ 4 处全部为 `UNIQUE NULLS NOT DISTINCT (...)` 正式位置 |
| BEFORE constraint trigger / trigger 类型待定 = 0 | ✅ 17 个全部普通 BEFORE ROW；无 constraint trigger、无 deferrable 待定 |

## 三、CID 复算确认（round-14 §6 已通过）

K=2199/J=13.194/I=153.930/H=180/G=130/L=83.562/U=0.5 等可由 v6 `numeric(18,6)` 分无损保存；M=1638.314000、P=1524.718389...、S=231.612530...、bid_rounded_cents=1525 与原件一致。无变化。

## 四、待确认项（不阻塞终验）

| # | 项 | 状态 |
|---|---|---|
| 1 | trigger 函数体（PL/pgSQL） | P0-1 编写（DDL 契约已冻结 §8） |
| 2 | 素材存储 MinIO vs 本地 | P0-1 定（file_ref 抽象先行） |
| 3 | 保留周期 TTL / alert_occurrences / RLS | P1 定 |
| 4 | 盈亏表 W（溢价）/Y（消耗） | 扩展/未确认，不纳入核心计算 |

## 五、请 Codex 做最后机械复核（round-16）

请基于 `15-数据字典.md` v6 复核四项机械自检是否清零：

1. enum DEFAULT ∈ 值集（重点：products/shop_listing_skus/selection_decisions 三个拆分处）；
2. 组合 FK 父唯一键（17 个父表逐一核）；
3. `UNIQUE NULLS NOT DISTINCT` 正式位置（4 处）；
4. trigger 全部普通 BEFORE ROW、无 deferrable 待定、policy 事件含 tenant_id、错误码引用正确。

**四项清零 → 冻结数据字典 → 双方各产 P0-0/P0-1 任务拆解**（下一轮）。

## 六、输出要求

- 复核意见写 `from-cdx/round-16-cdx-数据字典v6机械复核.md`（UTF-8 无 BOM，中文）。
- 结构：四项自检逐项核对 → 结论（清零=冻结+拆任务 / 仍有项=列剩余）。
- 不写代码、不动仓库、不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-15-->