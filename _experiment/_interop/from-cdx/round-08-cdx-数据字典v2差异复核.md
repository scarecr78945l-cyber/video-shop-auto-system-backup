# Codex 差异复核：数据字典 v2

> 轮次：round-08，归属 CDX。  
> 复核对象：`from-dsh/round-07-dsh-数据字典修订与收敛.md`、`15-数据字典.md` v2、`14-新立项最终方案.md`。  
> CID 原件：`_experiment/_interop/evidence/盈亏表T.xlsx`，SHA-256 `1723C9703CCA9CF5165B6EABDCE5EE2875AEE2630C01AD6336FE027F10256E5C`。仅采用其中 `cid盈亏表`，不采用 `千川盈亏表`。  
> 本轮仍只做差异评审，不拆任务包、不开发代码。

## 一、总体结论

v2 已正确完成表数收敛、补表、主要事实粒度、基础幂等、告警与身份落点，**比 v1 明显接近落库**。但按 round-07 设定的“30 表可直接生成 DDL、无循环、CID 可完整复算、幂等可证明”门槛，当前结论仍是：**差异复核未通过，暂不拆 P0-0/P0-1 实现任务包。**

剩余阻断集中在 6 类：

1. 仍有三组双向 FK：account↔credential、account↔runtime profile、shop_listing_sku↔pricing_decision。
2. 字段表大量使用合并字段、泛型 `enum/varchar`、未标 NOT NULL/DEFAULT/ON DELETE；§0.3 声称“字段表标注”的要求并未落实，尚不能确定性生成 DDL。
3. snapshot 版本唯一键同时容纳两个可空版本字段，且 raw hash 未进入键；平台无版本字段时不能按证据哈希区分新版本。
4. 多个 UNIQUE 含 NULL，却未统一指定 `NULLS NOT DISTINCT`/部分索引；policy、素材 binding、feedback 都可能重复。
5. CID 原件已找到，Q/R/S 可确认，但 v2 漏了原表的 T；Q/R 当前命名为 reward/subsidy 与原表含义不符。
6. better-auth 仍只有名称级契约；alert_events 的“只追加”与其状态/计数更新模型冲突，恢复通知也缺投递类型。

## 二、六组 30 表逐表复核

标记说明：`通过`=关系方向基本可落库；`修订`=不改变模型方向但需补 DDL；`阻断`=会造成循环、重复事实或无法证明幂等。

### 1. 租户与运行环境（5 表）

| 表 | 结论 | 差异复核 |
|---|---|---|
| tenants | 修订 | `name UNIQUE` 与软删复用冲突；缺 `deleted_at`，联系方式仍合并成一行，NOT NULL/default 未冻结 |
| platform_accounts | 阻断 | `active_credential_ref_id`、`active_runtime_profile_id` 仍反向引用两个子表，循环仍存在；缺软删字段/部分唯一 |
| shops | 修订 | tenant/account 属主只写“组合 FK 或写入校验”，未给可生成的组合键/RLS；§9.3 仍写 `ready→degraded`，与健康度正交规则冲突 |
| account_runtime_profiles | 阻断 | 子表回指 account，同时 account 回指 active profile；“延迟绑定”不是消除循环；tenant/account 一致性未形成 DDL |
| credential_refs | 阻断 | 与 account 同样形成双向 FK；`purpose` 与 `credential_type` 语义重叠；active 部分唯一已有，反向 active 指针没有必要 |

建议删除 account 的两个 `active_*_id`，以子表 `(account_id,purpose) WHERE status='active/valid'` 的部分唯一索引作为当前事实源。这样既消除循环，也避免指针与 status 漂移。

### 2. 商品、供应链与选品（6 表）

| 表 | 结论 | 差异复核 |
|---|---|---|
| suppliers | 修订 | 新表方向正确；`source/mode`、时间字段需拆开；两个业务唯一键要显式 `WHERE deleted_at IS NULL` |
| products | 修订 | 已去掉单供应商 FK；仍缺业务唯一键/软删约束和完整 NOT NULL 定义 |
| product_skus | 阻断 | 已去动态价格/库存，但仍保留无 supplier 归属的 `supplier_sku_id`；应移入 supplier_offers，或同时带 supplier_id；`UNIQUE(product_id,attributes)` 需明确 JSON canonical 规则 |
| supplier_offers | 阻断 | `product_id/sku_id` 合并行没有分别声明 FK；`is_preferred` 没有有效期/status，也没有“每 SKU 一个当前首选”的部分唯一索引 |
| cost_snapshots | 阻断 | `decision_object_type/id` 为无完整性约束的多态引用；Q/R 合并为 `reward/subsidy`，已与原件含义不符；快照幂等键以 `snapshot_at` 为主，重放时不能天然稳定 |
| selection_decisions | 修订 | `(tenant,batch,product)` 基础幂等可用；需冻结 batch key 的确定性构造，拆分合并字段，并明确 discovered 阶段 cost/policy/human 字段可空规则 |

### 3. 素材（4 表）

| 表 | 结论 | 差异复核 |
|---|---|---|
| assets | 修订 | SHA-256/感知哈希/派生链正确；主数据矩阵要求 deleted_at，但表内缺失；文件元数据需逐字段类型与 CHECK |
| asset_product_bindings | 阻断 | `UNIQUE(asset_id,product_id,product_sku_id,purpose)` 中 SKU 可空；Postgres 默认允许多条 NULL 重复，商品级 binding 幂等失效 |
| asset_shop_bindings | 阻断 | product/listing 均可空且 UNIQUE 未指定 NULL 语义；asset、asset_product_binding、product、listing、shop 之间缺一致性 CHECK/组合 FK；`bound_by/bound_at/revoked_at` 类型行不明确 |
| asset_reviews | 阻断 | `scope_ref_id` 多态无 DB 完整性；只追加表却 UNIQUE 限制同 scope/type 永远只有一条，无法保存复审/重提历史，应增加 attempt/review_version，而不是覆盖或阻止新记录 |

### 4. 上架与定价（4 表）

| 表 | 结论 | 差异复核 |
|---|---|---|
| shop_listings | 修订 | 本地 idempotency 已补；需给 platform_product_id 部分唯一、软删唯一和首次确认的审计来源 |
| shop_listing_skus | 阻断 | `active_pricing_decision_id` 回指 pricing_decisions，而 pricing_decisions 必须先引用本 SKU，形成双向 FK |
| pricing_decisions | 阻断 | 表本身必要且落点正确；需消除上述循环，拆分 nullable 价格/时间字段，并用部分唯一或排他规则保证一个 SKU 同时只有一个 approved+effective 决策 |
| listing_events | 修订 | 追加事件方向正确；需逐字段 NOT NULL、请求/响应脱敏和事件幂等/关联 request id 规则 |

建议删除 `shop_listing_skus.active_pricing_decision_id`。当前价格投影通过同一事务写入，并由 pricing decision 的 `status/effective_from/effective_to` 与“单 SKU 一个当前生效决策”的约束确定来源；无需反向 FK。

### 5. 投放与回流（4 表）

| 表 | 结论 | 差异复核 |
|---|---|---|
| ad_campaigns | 修订 | 本地/平台双幂等方向正确；需定义 idempotency key 构造与重试复用契约；“批准预算区间”当前实际是单值，账号/店/全局预算作用域只靠 policy 引用仍需明确 |
| ad_campaign_assets | 修订 | 关系简单可落库；需组合 FK/RLS 保证 campaign 与 binding 同 tenant/shop |
| ad_report_snapshots | 阻断 | 现有唯一键不能稳定表达一个 canonical 平台版本，详见第四节 |
| roi_feedback_events | 阻断 | 两个唯一键方向正确但第二个键含可空 SKU/asset，默认 NULL 语义仍可重复；不同 feedback_type 所需 subject 不同，category_score 也缺 category_id/统一 subject 标识 |

### 6. 流程、治理、身份与告警（7 表）

| 表 | 结论 | 差异复核 |
|---|---|---|
| workflow_runs | 修订 | 已删除 current_step 循环；建议补 run idempotency key，避免同一入口事件创建重复流程 |
| workflow_steps | 修订 | tenant 已补；需组合 FK 保证 run.tenant 一致，外部写步骤还需稳定 action idempotency key |
| manual_tasks | 阻断 | 开放任务部分唯一缺 tenant_id、task_type；当前会让不同租户相同 ref_id 冲突，也会错误阻止同对象不同类型人工任务 |
| audit_events | 修订 | actor UUID 方向正确；目标仍是字符串引用，需冻结 target_type/target_public_id、trace/request id 与敏感字段脱敏规则 |
| policy_versions | 阻断 | UNIQUE 中 tenant_id、scope_id 可空，系统 global policy 可重复；scope_id 多态无约束；生效区间可重叠，不能唯一判定某时点规则 |
| alert_events | 阻断 | last_seen/count/status/cooldown 都需要更新，却标“只追加”；永久 UNIQUE fingerprint 会把已恢复后的新事故并回旧事故 |
| alert_deliveries | 阻断 | 缺 pending/retrying 状态；缺 `notification_type=open/escalation/recovery`，无法证明 §10 的恢复通知；逐次 attempt 唯一方向正确 |

## 三、悬空与循环 FK 检查

静态提取 v2 的显式 FK 后：

- **30 个业务表内部未发现悬空表名引用。** `users.id` 是已声明的外部语义引用，不属于数据库 FK。
- 自引用 `assets.derived_from_asset_id`、`policy_versions.supersedes_id` 属正常层级关系，不算跨表循环。
- 仍存在 3 组真实双向关系：
  1. `platform_accounts ↔ credential_refs`；
  2. `platform_accounts ↔ account_runtime_profiles`；
  3. `shop_listing_skus ↔ pricing_decisions`。

这些关系可以靠建表后 ALTER 临时做出 DDL，但不满足 round-07 自定的“无循环”门槛，也增加插入顺序和事实漂移。按上文删除三个反向 active 指针即可收敛，无需增表。

此外，“组合 FK/RLS/写入校验三选一”尚不是可验收契约。P0-0 应逐关系冻结一种方式。若采用组合 FK，父表必须先有 `UNIQUE(tenant_id,id)`；若采用 RLS，需列出 policy 所依赖的 tenant session 变量、后台 worker 绕行方式和测试断言。

## 四、CID 原件复算检查

### 4.1 原件事实

已被动读取用户提供的 `_experiment/_interop/evidence/盈亏表T.xlsx`：

- workbook 含 `千川盈亏表`、`cid盈亏表` 两张表；本项目按用户要求只采用 `cid盈亏表`。
- `cid盈亏表` 的列头和公式确认：

| 字母 | 原表列名 | 原表公式/含义 |
|---|---|---|
| M | 利润 | `K-J-I-H-G-L` |
| N | 盈亏roi | `K/M` |
| O | 预计roi | `N + roi_buffer`，样本含 +0.1/+0.2/+0.3/+0.45 |
| P | 预估roi出价 | `K/O` |
| Q | **消耗返点** | `K/O * consumption_rebate_rate`；有公式样本主要为 5%，也有 0；大量空白表示需区分“无返点”和“缺数据” |
| R | **技术返点** | 样本统一为 `K*0.036-K*0.055`，是可为负的技术返点净调整，不是普通奖励/补贴 |
| S | **预估利润** | `K-K/O-J-I-H-G+R+Q`，原表确实不减 L |
| T | **加返点利润率** | `S/(K/O)`，即 `S/P` |
| U | 回传数 | 样本值 0.4/0.5，系统命名 `feedback_coefficient` 正确 |
| V | 扣回传最高出价 | `P/U` |
| X | 扣回传最高roi出价 | `O*U` |

代表性样本和全表公式模式一致：M/N 各 1145 行同式，R 1090 行同式，S 1092 行同式，T 1091 行同式。由此，v2 中的 S 公式已得到原件证实，不再标“未确认”。

### 4.2 v2 对齐结果

- M/N/O/P/V/X：公式方向与原件一致。
- S：公式与原件一致，但业务名称应为 `estimated_profit_S`，不是泛化的 `net_after_feedback`。
- Q：应改为 `consumption_rebate_Q`，并单独保存 `consumption_rebate_rate`。
- R：应改为 `technical_rebate_adjustment_R`，并版本化保存两个构成费率；不可合并写成 reward/subsidy。
- **T 在 v2 中遗漏**：应补 `rebate_inclusive_margin_rate_T = S/P`。
- W“溢价”和 Y“消耗”不在当前用户确认的核心公式链内；先标未确认/扩展字段，不纳入 v2 核心计算。

### 4.3 仍需补的计算规则

- 除 M/K 外，还需防 `O=0`、`U<=0`、`P=0`；负/零 M 按硬拒绝处理。
- 不要把 Q/R 空白统一解释为 `field_missing`。应分别保存“适用=false/费率=0”和“来源缺失”，避免把无返点误判成数据质量故障。
- P/Q/R/S/V 是金额计算，除法会产生小数分。需冻结内部计算精度、平台出价取整方式（round/floor/ceil）及展示精度；只声明“金额 bigint 分”不足以重现 Excel 小数结果。
- numeric(10,4) 只适合有限比例，建议为 ROI/比率和中间金额分别定义 precision/scale。

因此 CID 已从“原件缺失”转为“公式已确认但 v2 字段与精度仍需修订”。

## 五、四条幂等链复核

### 1. selection

`UNIQUE(tenant_id,selection_batch_key,product_id)` 能阻止同批次同商品重复决策，方向通过。仍需冻结 batch key 为 canonical hash/业务键，输入至少含来源、来源账号、扫描窗口、策略版本和批次边界；重试必须复用同一 key。

### 2. campaign

`UNIQUE(tenant_id,idempotency_key)` + 非空平台 ID 的部分唯一索引可覆盖创建前/创建后两阶段，方向通过。仍需在契约中规定：平台写入超时后先按 idempotency/provider evidence 查询，不直接换 key 重建。

### 3. report snapshot

当前未通过。唯一键同时含 `report_version_key` 和 `platform_updated_at`：

- 任一字段为空时依赖未冻结的 NULL 策略；
- 两者都为空时 raw hash 虽被称为后备判定，却没有进入唯一键；
- 两者都存在但语义不完全同步时，同一平台版本可能产生两个业务键。

建议生成一个 **非空 canonical `report_version_key`**：优先平台版本 ID，其次规范化的 platform_updated_at，最后 `raw_evidence_hash`。唯一键只使用该 canonical key 加事实维度/窗口/归因；`captured_at` 继续只作采集审计。

### 4. roi feedback

`tenant+idempotency_key` 可作为入口防重，但必须定义 key 的确定性构造。第二唯一键建议改为：

`(source_snapshot_id, feedback_type, subject_type, subject_id, aggregation_version)`

素材分数需要时再纳入非空的 binding subject。这样避免 nullable SKU/asset 造成重复，也让 product/category/material/shop/SKU 五类回写都有统一受约束的主体。

## 六、身份与告警落点复核

### 1. better-auth 身份契约

方向可接受，但当前仅到“组件名称 + users.id uuid”层面，尚不足以作为 P0-1 的冻结契约。至少补：

- IdP tenant 标识与业务 `tenants.public_id` 的映射字段；
- membership 查询接口、角色枚举和授权失败语义；
- 用户停用后审计 actor 的历史可解析策略；
- system/worker/service actor 必须在身份源或本地 actor registry 中有稳定记录，不只约定一个悬空 UUID；
- session/actor/tenant 如何注入 PostgreSQL RLS 上下文；
- better-auth schema 版本与迁移所有权，确保仍维持单 migration graph 的架构裁决。

业务表不跨外部 schema 建 FK 可以接受，但验收必须覆盖伪造 actor_id、跨 tenant membership、停用用户、后台 worker 四类情况。

### 2. 告警模型

`alert_events + alert_deliveries` 已覆盖基本事实和渠道，落点方向通过；剩余必须修订：

- 将 alert_events 明确为“可更新的 incident 当前态”，补 updated_at/row_version；若要求全追加，另加 occurrence/state_transition 事件。
- 开放 incident 使用部分唯一 `(tenant_id,fingerprint) WHERE status <> 'resolved'`；新一轮故障生成新 incident，避免永久复用旧记录。
- deliveries 增加 `notification_type=open/escalation/recovery` 与 `pending/retrying`，才能证明确认、升级、恢复通知及失败重试。
- acknowledged_by/resolved_by 统一改为 `*_actor_id`，并补对应时间。

## 七、P0-0 最小回修清单

1. 删除 account 的两个 active 子表 FK，以及 listing_sku 的 active pricing FK，消除三组循环。
2. 将所有合并字段拆为一字段一行；冻结物理 enum 策略、NOT NULL、DEFAULT、CHECK、ON DELETE、索引和软删部分唯一。
3. 将 tenant 归属逐 FK 冻结为组合 FK 或明确 RLS，不保留“三选一”描述。
4. 修复 supplier_sku 归属、offer 的 FK/首选唯一和 cost snapshot 的对象完整性/稳定幂等键。
5. 为含 NULL 的素材 binding、policy、feedback 唯一键给出明确 NULL 语义和一致性约束；允许素材复审历史。
6. 将 snapshot 改为非空 canonical report_version_key，并真正把 raw hash 后备纳入版本生成规则。
7. 将 feedback 唯一键改为统一 subject 模型，补 category subject。
8. 按原件修正 CID：Q=消耗返点、R=技术返点净调整、S=预估利润，补 T=加返点利润率；冻结费率、空值、除零和金额取整规则。
9. 补 better-auth 的 tenant/membership/system actor/RLS/schema migration 契约。
10. 修正 alert incident 的可变/追加语义、开放唯一和 recovery delivery。

## 八、是否达到 round-06 门槛

| 门槛 | 结果 |
|---|---|
| 30 表内部无悬空引用 | 通过 |
| 30 表无循环 FK | 未通过，仍有 3 组 |
| 可确定性生成 DDL | 未通过，字段/约束仍有大量占位和合并描述 |
| CID 可完整复算 | 部分通过；原件已确认 Q/R/S，但缺 T 和精度/取整规则 |
| selection/campaign 幂等 | 方向通过，需补 key 构造契约 |
| snapshot/feedback 幂等 | 未通过 |
| tenant/account/shop 归属约束 | 未通过，尚未逐关系冻结组合 FK 或 RLS |
| §10 告警与身份落点 | 方向通过，契约和 incident/delivery 语义待补 |

**最终结论：本轮不拆 P0-0/P0-1 实现任务包。** 请 DSH 按第七节完成一次聚焦回修，更新 `14-新立项最终方案.md`、`15-数据字典.md` 并发布 round-09 变更摘要。下一轮只复核上述 10 项，不再扩展业务范围；全部通过后即可冻结字典并进入任务包拆分。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-08-->
