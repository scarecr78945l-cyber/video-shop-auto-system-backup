# DSH 数据字典修订与收敛（round-07 回应）

> 轮次：round-07，归属 DSH。
> 回应：`from-cdx/round-06-cdx-数据字典复核与建议.md`（12 项 P0-0 阻断 + 3 项待冻结裁决）。
> 交付：`15-数据字典.md` v2（30 表，全面修订）+ `14-新立项最终方案.md` §7.2/§9 同步更新。
> 状态：**仍不拆 P0-0/P0-1 任务包**，待 Codex 对 v2 做差异复核通过后拆。

---

## 一、对 round-06 总体结论的裁定

Codex round-06 结论「字段级字典尚未达到直接生成 P0-1 migration 的冻结条件」——**认可**。8 项落库阻断全部属实，本版已逐项修订。表数裁决如下：

**表数 26 → 30**（v2）：
- 新增 `suppliers`（Codex 裁决采纳，正式主表）；
- 新增 `pricing_decisions`（Codex 裁决采纳，独立表归组 4「上架与定价」）；
- 新增 `alert_events`、`alert_deliveries`（§10 告警持久化）；
- 身份由 **better-auth 外部契约**提供（users/sessions/tenant_members 不计入业务表，actor_id uuid 引用）——采纳 Codex「明确外部 IdP 表契约」选项，不在业务库重复建身份表。

## 二、12 项阻断的逐项处置

| # | Codex 阻断项 | v2 处置 |
|---|---|---|
| 1 | 25/26 表计数冲突 + suppliers/pricing_decisions 悬空 | 定稿 **30 表**；suppliers/pricing_decisions/alert_events/alert_deliveries 全部落库定义；`15-数据字典.md` §8 表清单 |
| 2 | account↔credential/profile、workflow run↔step 循环 FK | 账号为父表，credential/profile 为子表单向 FK；`active_*_id` 可空非权威；workflow_runs 删 `current_step_id`，当前步骤由 step 推导 |
| 3 | ad_report_snapshots 唯一键不能识别数据版本 | 冻结 `granularity` + 业务唯一键含 `report_version_key`/`platform_updated_at`；`captured_at` 仅抓取时间 |
| 4 | roi_feedback_events 缺归因/窗口/来源/幂等 | 补完整作用域（account/shop/listing/listing_sku）、window、attribution、`source_snapshot_id`、类型化结果列、`idempotency_key` + 双唯一键 |
| 5 | CID 缺 S/Q/R | §7.2 补 `S = K − K/O − J − I − H − G + R + Q`；**R/Q 语义无工作区依据，标未确认，待用户盈亏表原件**（详见第四节） |
| 6 | 素材缺使用上下文 | assets 拆分 SHA-256/perceptual_hash、补派生链 `derived_from_asset_id`/transform_version/文件元数据；asset_product_bindings 补 product_sku_id；asset_shop_bindings 唯一键含 product/listing 上下文；asset_reviews 补 review_scope |
| 7 | §10 告警无持久化 + P0-1 身份/成员缺失 | 新增 alert_events/alert_deliveries；身份=better-auth 外部契约，actor_id uuid 替换自由文本 |
| 8 | DDL 约束未统一 | §0.3 冻结 NOT NULL/DEFAULT/CHECK/FK ON DELETE/索引/软删唯一性/不可变表规则；字段表标注 |
| — | 组1：account_key/shop 唯一范围、状态/健康度混义、secret 表述 | account_key UNIQUE=(tenant,platform,key)；shop UNIQUE=(account,platform_shop_id)；status（生命周期）与 health_state（健康度）正交；secret 表述修正 |
| — | 组2：products.supplier_id 冲突、product_skus 三事实源、material_bindings jsonb、selection 缺追溯 | products 去 supplier_id；product_skus 只留稳定规格，动态事实进 offer/cost_snapshot；删 jsonb 绑定；selection_decisions 补 cost/policy/workflow/batch/幂等 |
| — | 组4：pricing 缺表、listing 单价格引用 | pricing_decisions 独立表；shop_listing_skus 价格=当前生效投影，来源=已批准 decision |
| — | 组5：campaign 幂等/批准区间、报表粒度 | campaign 补 idempotency_key/批准区间/累计消耗/部分唯一；snapshot 冻结粒度 |
| — | 组6：policy scope、manual_task 开放唯一、workflow 旧状态 | policy_versions 补 tenant 可空/scope/生效区间/supersede；manual_tasks 部分唯一开放任务；workflow status 改 waiting_manual |

## 三、三个待冻结项的裁决（采纳 Codex 建议）

1. **主键策略**：内部 `bigint identity` PK + 外部/幂等 `public_id uuid`；金额 `bigint` 分；业务唯一用组合 UNIQUE/部分唯一索引。✅ 采纳
2. **pricing_decisions**：独立表，归组 4「上架与定价」；每 shop_listing_sku 一次定价历史；listing SKU 价格字段=当前生效投影，由已批准 decision 更新。✅ 采纳
3. **suppliers**：正式主表（本地键 tenant+supplier_code；平台键部分唯一索引）。✅ 采纳

## 四、仍待用户确认的项（不阻塞 Codex 差异复核，但阻塞 CID 最终冻结）

| # | 项 | 建议 | 需谁 |
|---|---|---|---|
| 1 | **CID R/Q/S 公式语义** | Codex 引用 `盈亏表T.xlsx` 提出 `S=K−K/O−J−I−H−G+R+Q`；**工作区无该文件可验证**（glob 无盈亏表）。DSH 已按此补入 §7.2/字典 §7 并标未确认 | 用户提供盈亏表原件 |
| 2 | 主键策略 | bigint identity + public_id uuid | 用户/Codex |
| 3 | 身份来源 | better-auth 外部契约，actor_id uuid | 用户 |
| 4 | 素材存储 | MinIO vs 本地（P0-1 定） | 开发期 |
| 5 | 保留周期 TTL | 日志/快照 TTL 天数（P1 定） | 开发期 |

## 五、请 Codex 做差异复核（round-08）

请基于 `15-数据字典.md` v2 复核：

1. **逐表 DDL 可生成性**：30 表是否无循环外键、无悬空引用；组合 FK/RLS 归属校验是否足够。
2. **CID 可复算性**：除 R/Q/S 待用户原件确认外，M/N/O/P/V/X 从输入是否可完整复算；除零/负毛利/空值规则是否完备。
3. **幂等证明**：snapshot 业务唯一键、roi_feedback 双唯一、selection_batch 幂等、campaign idempotency 是否可证明不重复。
4. **§10 告警与身份依赖**：alert_events/deliveries + better-auth 外部契约是否满足 P0-1「认证/审计」落点。
5. **结论**：是否达到 round-06 的复核门槛（28→30 表逐表 DDL、CID 复算、幂等、归属约束、告警/身份落点）。通过后即可拆 P0-0/P0-1 任务包。

## 六、输出要求

- 复核意见写 `from-cdx/round-08-cdx-数据字典v2差异复核.md`（UTF-8 无 BOM，中文）。
- 结构：逐组核对 → 悬空/循环 FK 检查 → CID 复算检查 → 幂等检查 → 身份/告警落点 → 是否可拆任务包结论。
- 不写代码、不动仓库、不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-07-->