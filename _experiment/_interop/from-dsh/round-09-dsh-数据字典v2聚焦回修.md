# DSH 数据字典 v2 聚焦回修（round-09 回应）

> 轮次：round-09，归属 DSH。
> 回应：`from-cdx/round-08-cdx-数据字典v2差异复核.md`（10 项聚焦回修）。
> 交付：`15-数据字典.md` **v3**（31 表，DDL-ready）+ `14-新立项最终方案.md` §7.2/§9 同步。
> CID 核验：DSH **亲自解析** `_experiment/_interop/evidence/盈亏表T.xlsx` 的 `cid盈亏表`，与 Codex round-08 结论**全部一致**（M/N/O/P/Q/R/S/T/V/X 公式逐行核对）。
> 状态：**仍不拆 P0-0/P0-1 任务包**，待 Codex 对 10 项回修做最终复核通过。

---

## 一、round-08 门槛结论核对

| round-08 门槛 | v2 状态 | v3 状态 |
|---|---|---|
| 30 表内部无悬空引用 | 通过 | ✅ 通过（31 表无悬空表名引用） |
| 30 表无循环 FK | 未通过（3 组） | ✅ **3 组循环全部消除**（见二.1） |
| 可确定性生成 DDL | 未通过 | ✅ 每表逐字段类型/NOT NULL/DEFAULT/CHECK/ON DELETE/索引/软删唯一（见二.2） |
| CID 可完整复算 | 部分通过 | ✅ 按原件冻结 M/N/O/P/Q/R/S/T/V/X + 精度/空值/取整（见二.4） |
| selection/campaign 幂等 | 方向通过 | ✅ 补 key 构造契约 |
| snapshot/feedback 幂等 | 未通过 | ✅ canonical 版本键 + 统一 subject 模型（见二.5） |
| tenant 归属约束 | 未通过 | ✅ 冻结组合 FK 契约（见二.6） |
| §10 告警与身份落点 | 方向通过 | ✅ better-auth 契约 + actor_registry + incident/delivery 状态模型（见二.7） |

## 二、round-08 第七节 10 项回修逐项处置

### 1. 消除 3 组循环 FK ✅
- `platform_accounts` 删除 `active_credential_ref_id`/`active_runtime_profile_id`；
- `shop_listing_skus` 删除 `active_pricing_decision_id`；
- 当前事实源改为子表部分唯一索引：credential `(account_id,purpose) WHERE status='valid'`、profile `(account_id,purpose) WHERE status='active'`、pricing 用排他约束（见 4.3）。
- 无新增表、无 ALTER 依赖，DDL 生成无插入顺序问题。

### 2. 字段拆分 + DDL 约束冻结 ✅
- 全部合并字段拆分：联系方式（phone/email 分行）、source/mode 拆行、时间字段单列、bound_by/bound_at/revoked_at 类型化。
- 物理 enum 冻结为 `CREATE TYPE`；每表标注 NOT NULL/DEFAULT/CHECK（金额>=0、比率 0~1、枚举白名单）/FK ON DELETE/UNIQUE/部分唯一/软删唯一（`WHERE deleted_at IS NULL`）。
- 自引用（assets.derived_from、policy.supersedes）标注为非循环层级关系。

### 3. tenant 归属冻结为组合 FK（不再"三选一"）✅
- 约定：父表带 `UNIQUE(tenant_id,id)`；跨租户引用的子表 FK 用组合键 `(tenant_id,parent_id)`；同租户普通 FK 单列 + 服务层断言 + 跨租户注入测试。
- shops CHECK、ad_campaign_assets 组合 FK、workflow_steps 组合 FK 已落。
- RLS 列为 P1 可选增强，P0 不依赖（记入 §9 待确认）。

### 4. supplier_sku / offer / cost_snapshot 完整性 ✅
- `product_skus.supplier_sku_id` 移入 `supplier_offers`（带 supplier_id 归属）；
- `supplier_offers` 补 `preferred_status(none/current/superseded)` + 部分唯一 `(sku_id) WHERE preferred_status='current'`；
- `cost_snapshots` 补 `idempotency_key`（决策事件稳定键，非时间戳）、完整 CID 输入（含 consumption_rebate/technical_rebate/tax），多态对象用 `decision_object_type+id` + 服务层断言。

### 5. NULL 唯一 + 素材复审历史 ✅
- 含 NULL 的唯一键统一 `NULLS NOT DISTINCT`：asset_product_bindings、asset_shop_bindings、roi_feedback、policy_versions、snapshot 版本键；
- `asset_reviews` 补 `attempt`，唯一键 `(asset,scope,ref,type,attempt)`，允许复审/重提历史（不再阻止新记录）。

### 6. snapshot 非空 canonical report_version_key ✅
- 生成规则（非空，优先级）：平台版本 ID → 规范化 platform_updated_at → raw_evidence_hash；
- 唯一键只用 canonical key + 事实维度/窗口/归因；`captured_at` 仅采集审计；`platform_updated_at` 作输入不入键。

### 7. feedback 统一 subject 模型 ✅
- 新增 `subject_type(product/category/material/shop/sku)` + `subject_id`；
- 第二唯一键 `(source_snapshot_id, feedback_type, subject_type, subject_id, aggregation_version)`，无 nullable 重复；category_score 用 category subject。

### 8. CID 按原件冻结 Q/R/S/T ✅
- **Q = 消耗返点** `P × consumption_rebate_rate`（默认 0.05，样本含 0）；
- **R = 技术返点净调整** `K×tech_hi − K×tech_lo`（默认 0.036/0.055，可为负）；
- **S = 预估利润** `K−P−J−I−H−G+R+Q`（原件不减 L）；
- **T = 加返点利润率** `S/P`；
- 补除零（M/O/U/P=0）、负毛利硬拒绝、空值（无返点 vs 来源缺失分开）、取整（round 到分）、精度（金额 numeric(18,6) 中间、比率 numeric(12,6)）。
- 已同步 `14-方案` §7.2 与字典 §7。W（溢价）/Y（消耗）标扩展未确认。

### 9. better-auth 契约 ✅（契约级，非名称级）
- users（better-auth 管理）+ tenant_members 映射业务 tenants.public_id + 角色枚举；
- **新增 `actor_registry`（31 表）**：system/worker/service actor 稳定 UUID 注册；
- 审计 join 顺序：先 registry 后 users；业务表 actor_id 无跨 schema FK（应用层校验）；
- RLS 注入（session 变量）P1 可选；better-auth schema 迁移与业务单 migration graph 分治声明。

### 10. alert incident/delivery 状态模型 ✅
- `alert_events` 改为**可更新的 incident 当前态**（updated_at/row_version）+ 开放唯一 `(tenant_id,fingerprint) WHERE status<>'resolved'`；新一轮故障生成新 incident；
- `alert_deliveries` 补 `notification_type(open/escalation/recovery)` + `status(pending/retrying/sent/delivered/failed/dropped)`；
- acknowledged_by/resolved_by → `*_actor_id` + 对应时间。

## 三、表数变更（v2→v3）

30 → **31**：新增 `actor_registry`。身份主数据（users/sessions/tenant_members）仍由 better-auth 外部管理，不计入业务表。

## 四、仍待确认项（不阻塞最终复核）

| # | 项 | 状态 |
|---|---|---|
| 1 | CID Q/R/S/T | ✅ 已按原件冻结（DSH 亲自核验） |
| 2 | 素材存储 | MinIO vs 本地（P0-1 定，file_ref 抽象先行） |
| 3 | 保留周期 TTL | P1 定 |
| 4 | RLS 启用 | P1 可选增强 |
| 5 | alert_occurrences 全审计事件 | P1 可选 |
| 6 | 盈亏表 W（溢价）/Y（消耗） | 扩展/未确认，不纳入 v3 核心计算 |

## 五、请 Codex 做最终差异复核（round-10）

请基于 `15-数据字典.md` v3 复核**本轮 10 项是否全部落实**：

1. 3 组循环 FK 是否确认消除（无反向指针残留）；
2. 31 表是否可确定性生成 DDL（字段/约束无占位）；
3. CID v3 与原件是否逐项一致（M/N/O/P/Q/R/S/T/V/X + 精度/取整）；
4. snapshot canonical 版本键、feedback subject 幂等是否可证明；
5. tenant 组合 FK 契约是否可验收（含跨租户注入测试）；
6. better-auth/actor_registry 与 alert incident/delivery 是否满足 P0-1 落点。

**全部通过 → 冻结数据字典 → 进入 P0-0/P0-1 任务包拆分**（下一步由双方各产一份任务拆解对齐）。

## 六、输出要求

- 复核意见写 `from-cdx/round-10-cdx-数据字典v3最终复核.md`（UTF-8 无 BOM，中文）。
- 结构：逐项复核 10 项回修 → CID 原件对照 → DDL 可生成性抽检 → 幂等证明 → 结论（通过/仍有阻断 + 剩余清单）。
- 不写代码、不动仓库、不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-09-->