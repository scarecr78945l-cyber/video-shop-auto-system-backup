# Codex 复核：数据字典与 P0 落库前修订建议

> 轮次：round-06，归属 CDX。  
> 复核基线：`14-新立项最终方案.md`、`15-数据字典.md`、`from-dsh/round-05-dsh-完整定稿同步.md`。  
> 本轮只做方案和字典评审，不拆 P0-0/P0-1 任务包，不开发业务代码。

## 一、总体结论

结论：**方向一致，但当前字段级字典尚未达到直接生成 P0-1 migration 的冻结条件。**

主要原因不是架构路线有分歧，而是存在若干落库阻断项：

1. 文档称“六组 25 表”，实际列出 **26 表**（5+5+4+3+4+5）；同时 `suppliers`、`pricing_decisions` 已被外键引用却未定义。补齐后基线应为 **28 表**，或重新明确哪些表移出 P0 范围。
2. 账号、凭证、运行环境以及 workflow run/step 存在循环外键或不清晰的主从关系。
3. `ad_report_snapshots` 的唯一约束不能识别“同一平台数据版本”，与“两次回读必须是两个不同版本”冲突。
4. `roi_feedback_events` 没有保存 §8.2 要求的完整归因维度、窗口、来源快照及幂等键。
5. CID v1 少了用户指定的 `S` 计算，也缺少 `Q/R/S` 的字段语义；当前成本快照不足以完整复算。
6. 素材的商品、SKU、店铺、上架实例之间没有形成可校验的使用上下文，无法可靠表达“首次用于某商品/店铺”和店级审核。
7. §10 的告警事实、投递、确认、升级、恢复、防风暴没有持久化模型；P0-1 所称“认证/审计”也缺最小操作者/租户成员模型或明确外部依赖。
8. NOT NULL、默认值、CHECK、FK 删除策略、索引、软删唯一性等 DDL 必要信息仍未统一。

因此本轮评审结果为：**先由 DSH 收敛 P0-0 字典修订，再做一次差异复核；复核通过后再拆 P0-0/P0-1 任务包。**

## 二、六组逐组复核

### 1. 租户与运行环境（当前 5 表）

**已对齐**

- `tenant → platform_account → shop` 层级清楚。
- 账号级 profile、登录态、限流和熔断方向与冻结架构一致。
- 业务库只保存凭证引用，不保存凭证明文，方向正确。

**缺失/冲突**

- `platform_accounts.credential_ref_id → credential_refs` 与 `credential_refs.account_id → platform_accounts` 形成循环；runtime profile 也存在同样循环。
- `platform_accounts.account_key` 仅声明 tenant 内唯一，跨平台同名会冲突；应为 `(tenant_id, platform, account_key)`。
- `shops.platform_shop_id` 的唯一范围不明确，建议至少为 `(account_id, platform_shop_id)`，并校验 shop、account 的 tenant 一致。
- §9.3 状态机末端写 `ready → degraded / suspended`，字典又把 `degraded` 放在 `health_state` 而非 `status`。需冻结为“接入生命周期”和“运行健康度”两条正交状态，不让同一含义落在两个字段。
- `secret_store_key` 是定位符；“原文只存这里”应改为“原文只存 secret store，业务表仅存定位符”。
- 店铺/账号/全局预算和止损配置在接入步骤中必填，但这组表没有可持久化的作用域配置引用。

**建议**

- 账号做父表；`credential_refs`、`account_runtime_profiles` 做子表。账号表不保存反向单一 FK。若必须指向当前生效记录，使用 nullable `active_*_id`，并明确延迟约束和切换事务。
- 为 profile 和 credential 增加用途、版本/轮换序号及“同账号仅一个 active”的部分唯一约束。
- 预算/止损/限流统一引用带 scope 的 `policy_versions` 或新增明确的 scope binding，避免散落 JSON 且无法审计生效版本。

### 2. 商品、供应链与选品（当前 5 表，实际至少应补 1 表）

**已对齐**

- 商品租户级复用、SKU 粒度判断、报价历史和成本快照的总体方向正确。
- `selection_decisions` 已覆盖合规、置信度、报价有效期和分层状态的主要字段。

**缺失/冲突**

- `suppliers` 没有定义，但 `products`、`supplier_offers` 已引用它，当前 DDL 无法建立。
- `products.supplier_id` 表达“一商品一个供应商”，与 `supplier_offers` 的多供应商/多报价设计冲突。
- `product_skus.offer_id/purchase_price/quote_expires_at/stock` 与 `supplier_offers`、`cost_snapshots` 重复，容易产生三个“当前事实”。
- `product_skus.material_bindings jsonb` 与正式 binding 表重复，且绕过 FK。
- `selection_decisions` 缺 `cost_snapshot_id`、`policy_version_id`、来源账号、批次/幂等键、来源链接、可用素材数量等 §4 要求的关键追溯字段。
- `cost_snapshots` 没有决策对象类型、店铺/上架上下文、报价引用；也缺 CID 所需的电商税 `L` 和奖励/补贴输入 `Q/R`。
- §4.4 的扫描批次、来源快照版本和候选池幂等没有明确落点；§4.5 的来源健康度历史只剩账号当前状态，无法解释单来源的降级/冷却。

**建议**

- 正式增加 `suppliers`；移除 `products.supplier_id`。多供应商关系由 `supplier_offers` 建立；首选供应商使用显式 `preferred_offer_id` 或独立偏好关系。
- `product_skus` 只保留稳定规格、重量/体积和合规/可售状态；动态价格、有效期、库存及观测时间进入 offer/snapshot。需要查询性能时可保留投影字段，但必须写明唯一事实源和刷新规则。
- 删除 `material_bindings jsonb`，以关联表为准，并补 SKU 粒度关联。
- 为选品决策补 `workflow_run_id/selection_batch_key`、`cost_snapshot_id`、`policy_version_id`、`source_account_id` 和幂等唯一约束；来源健康事件可新增事实表，或在流程/审计模型中给出明确、可查询的结构化事件定义。

### 3. 素材（当前 4 表）

**已对齐**

- `assets` 归 tenant，商品和店铺授权通过 binding 显式表达，符合跨店复用原则。
- 权利状态、来源证据、质量/相关性及审核记录已具备基础模型。

**缺失/冲突**

- `asset_product_bindings` 只有 product，没有 SKU；与 §6.4 的 SKU 图片/素材绑定不完整。
- `asset_shop_bindings` 只有 asset+shop+purpose，没有 product/listing 上下文。同一素材在同店同用途服务多个商品会被当前唯一约束错误阻止，也无法证明某批素材针对哪个 `product × shop` 通过闸门。
- `asset_reviews` 只关联 asset，无法表达首次用于某商品、某店铺或某投放计划的审核。
- `content_hash` 把 dHash/MD5 混为一项。dHash 是感知相似哈希，不是字节内容完整性哈希；MD5 也不宜作为证据完整性键。
- `mode` 中写成 `pill`，与全局约定的 `pillow` 不一致。
- 自动转码/裁切/二创后缺 `derived_from_asset_id`、变换版本及文件元数据，审核继承链不可重放。

**建议**

- 字节内容使用 SHA-256，感知去重另设 `perceptual_hash`。
- `asset_product_bindings` 增加可空 `product_sku_id`；店铺绑定应关联 `asset_product_binding_id` 或显式 `product_id/shop_listing_id`，唯一键包含使用上下文。
- `asset_reviews` 增加 review scope 和对应 binding/listing/campaign 引用；`asset_shop_bindings.review_status` 作为当前投影，最终事实以 review 记录为准。
- 为资产补 MIME、大小、宽高、时长、派生来源、处理器/参数版本，保证自动修复和审核继承可审计。

### 4. 上架（当前 3 表，实际至少应补 1 表）

**已对齐**

- `shop_listings` 与 `shop_listing_skus` 正确表达商品×店铺和店级 SKU。
- 上架事件流水具备状态迁移和证据基础。

**缺失/冲突**

- `shop_listings.price_setting_ref` 引用了未定义的 `pricing_decisions`。
- 一个 listing 下有多个 SKU，而 listing 只保存一个价格决策引用，无法落实“最终定价按店铺、SKU 重算”。
- `shop_listing_skus.shop_price/promo_price/floor_price` 与未来价格决策会形成重复事实，未定义哪一处是历史事实、哪一处是当前生效投影。
- 首次人工确认、自动修复次数、提交幂等键、平台拒审原始码/响应版本没有稳定字段；仅靠事件文本不足以防重复上架。
- 平台商品/SKU 标识缺平台作用域唯一约束，NULL 阶段也缺本地幂等键。

**建议**

- 新增独立 `pricing_decisions`，放入第 4 组并将组名改为“上架与定价”；一行对应一个店铺 listing SKU 的一次定价决策。
- listing SKU 上的价格字段只作为“当前生效投影”，由已批准且在有效期内的 pricing decision 更新；历史不可覆盖。
- 上架写入增加 `idempotency_key`、提交版本、平台请求/响应证据以及明确的人工审批引用。

### 5. 投放与回流（当前 4 表）

**已对齐**

- campaign 已落到 `shop_listing` 粒度，素材引用店级 binding，符合店级隔离。
- `feedback_coefficient` 命名正确，没有把 U 误作订单数。

**缺失/冲突**

- `ad_report_snapshots UNIQUE(campaign_id, captured_at)` 只能防止同一抓取时刻重复，不能判断同一统计窗口/归因口径/平台更新时间的数据版本；“同周期仅保留最新快照”的说明与约束不一致。
- 报表字段写 `sku_id → product_skus`，§8.2 要求的原始事实优先粒度是 `shop_listing_sku`，应使用 `shop_listing_sku_id`。
- 报表一行到底是 campaign 汇总还是 SKU/素材明细没有冻结；不同粒度混在一张表时唯一键会互相覆盖或重复。
- `roi_feedback_events` 缺 account/shop/listing/listing_sku、统计窗口、归因口径、来源 snapshot、聚合版本和幂等键；`source_type/source_id` 多态引用也缺数据库完整性。
- `value jsonb` 承载全部回写结果，核心分数、毛利和策略变更难以约束和索引。
- campaign 只保存当前预算/ROI，没有批准区间、审批引用、生效版本、累计消耗和各层预算约束的事实落点。`UNIQUE(shop_listing_id, platform_campaign_id)` 对 NULL 平台 ID 不能防止重复创建。
- CID v1 只写 M/N/O/P/V/X，遗漏用户确认的 `S = K - K/O - J - I - H - G + R + Q`；`Q/R/S` 也没有语义和存储位置。

**建议**

- 冻结报表事实粒度。推荐增加抓取批次/版本标识，并采用类似 `(campaign_id, shop_listing_sku_id, asset_binding_id, window_start, window_end, attribution_mode, platform_updated_at)` 的业务唯一键；可空维度需用规范化 sentinel、NULLS NOT DISTINCT 或表达式索引处理。
- `captured_at` 只表示抓取时间，`platform_updated_at` 或稳定 `report_version_key` 才表示平台数据版本；原始证据哈希可作为平台不提供版本时的后备判定。
- `roi_feedback_events` 显式关联 `source_snapshot_id` 和完整作用域，核心结果使用类型化列，扩展解释再放 JSON；增加聚合窗口/算法版本/幂等唯一键。
- campaign 增加本地 `idempotency_key`、批准预算/ROI/止损区间、approval 引用及作用域预算策略版本。
- CID v1 按用户指定 Excel 口径补全 M/N/O/P/S/V/X，并定义 K/J/I/H/G/L/Q/R/U 的单位、空值和除零规则；金额统一 bigint 分，比例用有精度约束的 numeric。

### 6. 流程与治理（当前 5 表）

**已对齐**

- 持久化业务流程 + 队列叶子步骤的方向正确。
- manual task、audit event、policy version 能承接闸门、人工处理和规则版本化的基础需求。

**缺失/冲突**

- `workflow_runs.current_step_id → workflow_steps` 与 `workflow_steps.run_id → workflow_runs` 再次形成循环；当前步骤本可从未完成步骤推导。
- `workflow_runs.status=waiting_confirmation` 仍保留旧语义，与 round-05 已冻结的“自动校验→自动回修→超限人工强审”不一致。
- `workflow_steps` 没有 tenant_id，却声明归属 tenant；若采用数据库 RLS，跨 tenant 隔离需经 join 才能判断。
- `manual_tasks.ref_type/ref_id` 无完整性与“一个对象只存在一个开放任务”的幂等约束，审批结果也缺 actor、规则版本和前后状态。
- `policy_versions` 被定义为全局且 `UNIQUE(policy_type, version)`，但方案要求平台默认、类目、店铺、商品多层覆盖；当前无法表达 tenant/scope/effective range 和优先级。
- §10 告警的去重、冷却、确认、升级、恢复、渠道投递没有表定义。
- P0-1 写明“认证/审计”，但字典没有操作者、租户成员、角色/权限模型，也未声明复用哪个外部身份系统。`reviewer/assignee/approved_by` 均为自由文本，审计主体不可校验。

**建议**

- 删除 `current_step_id` 或将其作为非权威缓存且延迟绑定；以 step 状态和顺序确定当前节点。
- workflow run 使用 `running / waiting_manual / paused / done / failed / cancelled`；自动回修由 step 的 `gate_retry` 和 attempt 表达，超限创建 manual task。
- `policy_versions` 增加 `tenant_id nullable`、`scope_type/scope_id`、`effective_from/effective_to`、`supersedes_id`；唯一约束覆盖作用域，系统模板与租户实例分清。
- 在 P0 字典补最小身份/成员关系，或明确外部 IdP 表契约；审计、审核、审批、分派统一使用 actor FK。
- 增加 `alert_events` 与 `alert_deliveries`（或等价模型），覆盖 fingerprint、severity、状态、首次/末次出现、计数、冷却、确认、升级、恢复及逐渠道投递结果。

## 三、`14-新立项最终方案.md` §4～§10 对齐检查

| 方案章节 | 对齐结论 | 主要差距 |
|---|---|---|
| §4 选品 | 部分对齐 | 四重过滤主要字段已有；缺扫描批次/幂等、cost/policy 强引用、素材数量与来源链接、来源健康历史 |
| §5 素材 | 部分对齐 | 来源/权利/质量已有；缺 SKU 与 product×shop 使用上下文、派生链、首次使用审核作用域 |
| §6 上架 | 阻断 | 商品×店铺模型已有；`pricing_decisions` 缺表且 listing 单一价格引用无法覆盖 SKU 级最终定价 |
| §7 托管 | 部分对齐 | 店级 campaign 已有；缺审批和多层预算事实、CID S/Q/R、创建幂等 |
| §8 回读/ROI | 阻断 | 当前快照唯一键不能证明不同平台版本；feedback 缺完整归因、窗口、来源和幂等 |
| §9 数据治理 | 阻断 | 25/26/28 表口径冲突；全表共同字段与实际字段不一致；DDL 约束未完整冻结 |
| §10 监控告警 | 阻断 | 字典没有告警事件和渠道投递的持久化模型 |

另外，§9.2 所称“核心表统一包含 source/mode/evidence_ref/policy_version”等字段，与 26 表实际定义明显不一致。建议不要机械给所有表铺同一字段，而是冻结字段矩阵：

- 主数据：tenant、状态、`created_at/updated_at`、`row_version`、`deleted_at`；
- 外部采集事实：source、mode、观测/抓取时间、证据和解析版本；
- 决策：policy version、成本快照、审批和决定时间；
- 不可变事件/快照：只追加，不做 updated/软删；
- 凭证：只保留 secret store 定位符、状态和轮换元数据。

## 四、三个待冻结项的明确建议

### 1. 主键策略

冻结为：

- 内部关系主键统一 `bigint generated always as identity`；金额也统一 `bigint` 分。
- 对 API 暴露、证据关联、跨系统同步和幂等任务增加不可猜测的 `public_id uuid`，默认唯一。
- 所有 FK 使用 bigint；业务唯一性由组合 UNIQUE/部分唯一索引表达，不拿主键代替业务约束。
- 跨 tenant 冗余 ID 必须用组合 FK、RLS 或写入校验保证归属一致。

不建议所有表直接以 UUID 作为聚簇主键；当前是单 Postgres 模块化单体，bigint 对索引和迁移更简单，public UUID 已覆盖外部引用需求。

### 2. `pricing_decisions` 落点

冻结为：**独立表，归入第 4 组“上架与定价”**。选品估算价仍属于 `selection_decisions`；`pricing_decisions` 专门保存上架前及后续调整的店铺 SKU 最终定价历史。

至少包含：

- `tenant_id/shop_id/shop_listing_id/shop_listing_sku_id`；
- `cost_snapshot_id/policy_version_id`；
- `decision_type`、成本底价、建议价、日常价、活动价、最低保护价、目标毛利；
- 竞品证据及观测时间；CID 相关输入/结果引用；
- `status=draft/pending_approval/approved/rejected/superseded/expired`；
- `approved_by/approved_at/effective_from/effective_to`；
- `evidence_ref/idempotency_key/created_at`。

`shop_listing_skus` 只保存当前生效价格投影；通过 FK 或服务事务保证它来源于一条已批准的 decision。

### 3. `suppliers` 主表

冻结为正式主表，至少包含：

- `id/public_id/tenant_id/supplier_code/name`；
- `source_platform/platform_supplier_id`；
- `contact_ref`（敏感联系方式引用）、`settlement_terms`、`payment_terms_days`；
- `fulfillment_mode/return_policy`；
- `health_state/status/source/mode/evidence_ref`；
- `created_at/updated_at/deleted_at/row_version`。

建议唯一约束：本地业务键 `(tenant_id, supplier_code)`；平台键 `(tenant_id, source_platform, platform_supplier_id)` 使用非空部分唯一索引。`supplier_offers` 再补供应商 SKU、库存/库存观测时间和报价幂等键。

## 五、P0-0 必须先修的阻断清单

1. 纠正 25/26 表计数，正式纳入 `suppliers`、`pricing_decisions`，冻结最终 P0 表清单。
2. 冻结主键/外部 UUID/金额 bigint 策略。
3. 消除 account↔credential/profile 和 workflow run↔step 的循环主从关系。
4. 处理 product、SKU、offer、cost snapshot 的事实源重复，并移除 JSON 素材绑定。
5. 补齐素材 product/SKU/shop/listing 使用上下文和审核作用域。
6. 补齐 pricing decision 字段、SKU 粒度、审批与当前价格投影规则。
7. 重做 report snapshot 的逻辑版本键、事实粒度和幂等约束。
8. 补齐 ROI feedback 的来源快照、完整归因、窗口、算法版本与幂等键。
9. 按用户指定口径补全 CID 的 S/Q/R，冻结除零、负毛利、空值和精度规则。
10. 让 policy version 支持 tenant 和多层 scope 覆盖，统一 gate/预算/止损规则生效模型。
11. 明确最小身份/租户成员契约，并为告警事件/投递增加持久化模型。
12. 给每表补齐 NOT NULL、DEFAULT、CHECK、FK ON DELETE、索引、软删唯一性、不可变表规则和保留策略。

以下不阻塞本轮业务模型冻结，可按既定阶段处理：MinIO 与本地目录的具体实现（先固定 `file_ref` 抽象）；日志/大体量快照 TTL 的最终天数（先规定永久或可配置）；真实平台字段与刷新周期（继续标“未确认”，待 P0-3 实测）。

## 六、是否可拆 P0-0/P0-1

- **P0-0/P0-1 实现任务包：暂不拆。** 当前字典存在 dangling FK、关键事实粒度和幂等约束未冻结，直接拆包会把分歧固化到 migration。
- **下一步：** DSH 依据第五节先修订 `14-新立项最终方案.md` 与 `15-数据字典.md`，发布新的接力文件并列出表清单/字段/约束的变更摘要。
- **复核门槛：** 28 表（或经裁决后的最终数量）逐表可生成无循环、无悬空引用的 DDL；CID 可从输入完整复算；快照和回写可证明幂等；tenant/account/shop 归属可由数据库约束或明确 RLS 契约验证；§10 告警与 P0-1 身份依赖有明确落点。
- 达到上述门槛后，Codex 再进行一次差异复核；通过后再拆 P0-0/P0-1 任务包。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-06-->
