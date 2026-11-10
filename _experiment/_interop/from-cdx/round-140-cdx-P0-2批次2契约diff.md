# round-140 CDX：P0-2 批次 2 契约 diff

> 日期：2026-09-09。输入：`from-dsh/round-139-dsh-P0-2批次2契约收敛.md`。
> 裁决：批次 2 总方向成立，但 C1/C2/C3 的实体实现继续锁定。当前存在六组必须先闭合的契约差异；批次 3 继续锁定。

## 一、输入与被动证据

round-139 SHA-256：

```text
E5A19C814F59933B938D6FF9B5E0A8582CFC5F629BE792876EBA56C03C33FE87
```

本轮只做文档、源码与当前 PG catalog 的被动核对，未编辑业务实现。关键事实：

```text
shop_listing_skus columns=
id,tenant_id,shop_listing_id,sku_id,platform_sku_id,shop_price,promo_price,
floor_price,allocated_stock,safety_stock,listing_status,rejection_reason,created_at,updated_at

enum_policy_type=
cid_breakeven,pricing,compliance,whitelist,budget,stop_loss,rate_limit,gate

roi_feedback_events=
单 source_snapshot_id；单 value；extra_explanation 可空；
唯一键 (source_snapshot_id,feedback_type,subject_type,subject_key,aggregation_version)；
唯一键 (tenant_id,idempotency_key)
```

`trg_feedback_dimension_consistency` 还要求 event 的 tenant/account/shop/listing/product/campaign/SKU/asset
八维与该单一 `source_snapshot_id` 对应快照逐字段一致。

## 二、已通过的契约方向

- 版本选择只依赖平台更新时间证据，opaque token、hash、内部 id、captured_at 均不承担版本排序。
- 候选唯一最大、最大值并列、全空三态方向正确；旧事实保持 append-only。
- 观测 ROI 与 CID 决策职责分离，金额继续使用分，计算继续使用 Decimal。
- `roi_feedback_events` 作为事实 ledger、同值重放复用、内容冲突保留旧行的方向正确。
- 五类 feedback/subject 的枚举配对与 `ck_feedback_subject_map` 一致。
- REPORT_MANUAL 仍归批次 3，批次 2 仅保留下游接口。

以下差异关闭后，上述方向可冻结。

## 三、R140-1：版本选择的可执行边界仍缺四项

1. round-139 同时写了“按 `platform_updated_at` 选择”和“只有 `ts:` 源参与排序”。两者语义不同。
   version key 为 `id:<token>` 的快照仍可能带非空 `platform_updated_at`。应冻结为：**排序读取独立字段
   `platform_updated_at`，与 report_version_key 前缀无关**。
2. 明确混合集合：部分候选时间非空、部分为空时，只在非空集合中取唯一最大；空值候选进入证据清单，
   不参与比较。最大非空时间并列仍返回证据不足。
3. 选择器输出须是明确的 tagged result，例如 `selected(snapshot_id, evidence)` 或
   `manual_required(reason, evidence)`。批次 2 只返回后者，不创建 manual task。
4. “时间倒退写入 extra_explanation”目前没有落点：snapshot 表无该列。应由 `DecisionBasis.evidence`
   携带倒退快照列表，成功生成 ledger 时再复制进 event.extra_explanation；若返回 manual_required，则证据交给
   批次 3。

还需冻结候选身份 exact-set、tenant 边界、查询事务快照和输入无序时的确定性黄金向量。

## 四、R140-2：单快照身份与跨快照五层聚合冲突

round-139 将一个 event 定义为跨多个 snapshot 的 product/category/material/SKU/shop 聚合结果，同时沿用单一
`source_snapshot_id` 作为身份与八维锚点。这两项尚未形成可重放契约：

- 多个统计身份各自选出有效版本后，没有定义哪一个 snapshot 成为 event 的唯一锚点。
- `origin_snapshot_ids` 只在 JSON 证据中，不参与两个数据库唯一键；新成员进入聚合时可能保持原锚点却改变 value，
  结果会被判为内容冲突，而不是新的聚合版本。
- category/shop 跨多个 product/listing/campaign 时，event 的八维只能复制某一快照；当前 trigger 尚未表达
  “这些维度来自整个聚合集合”。
- campaign、SKU、asset 粒度混合求和会重复计算同一业务流量；round-139 未给每个 feedback_type 的输入粒度
  优先级与去重规则。

round-141 必须在以下两种模型中明确选择并给出真值表：

1. **单快照贡献模型**：ledger 每行严格由一个 source snapshot 派生；跨快照聚合移到消费查询，event 需保存
   足够的分子/分母证据并定义消费者的去重与加权规则。
2. **聚合结果模型**：走 D5 schema 变更评审，增加稳定 aggregation identity/input-set hash 及可审计的来源集合，
   同时调整唯一键与维度约束。

在模型确定前，C1 五层聚合与 C2 ledger 身份均保持锁定。

## 五、R140-3：五类 value 口径与确定性数值尚未冻结

当前只定义了 `observed_roi = sum(gmv) / sum(spend)`，但五个枚举并非同一语义：

- product_score、category_score、material_score 可候选为观测 ROI；
- sku_margin 尚缺收入、成本、退款/补贴及单位公式；
- shop_strategy 尚缺数值含义、范围和消费动作。

round-141 需给出五行 exact-set：feedback_type、输入粒度、分组键、窗口/attribution 约束、分子、分母、
value 单位/范围、最低样本动作、零值动作。若某类本批延期，需作为范围变更单独裁决，五层不可静默缩减。

“Decimal 全精度”对 `1/3` 等循环小数没有唯一结果。还需冻结：工作精度、舍入模式、落库 scale/canonical
表示及黄金向量。U1/U2/U3 也必须从“未确认”推进为实现可执行值；`policy_versions` 当前没有 aggregation
类型，故 U2 需选择以下之一：

- 冻结独立 `aggregation_version` 常量与配置 manifest；
- 或走 enum/schema 变更评审增加正式 policy 类型。

`products.category_id` 当前是 NOT NULL varchar(64)，但没有受控词表 FK。U7 应明确把它视为 opaque、
case-sensitive 稳定键，或提交正式类目表/约束变更；现状不应描述成已有受控词表。

## 六、R140-4：FeedbackRepository 边界与键公式有四处差异

1. round-139 写成明文拼接 `fb:<fields...>`，冻结公式实际为：
   `fb:v1:<lower_hex_sha256(canonical_join(fields))>`。输入序保持
   source_snapshot_id、feedback_type、subject_type、subject_key、aggregation_version。
2. subject_key 规范化需按类型冻结：UUID 小写规范形式、category opaque string 的 NFC/case 规则、SKU 最终键源。
3. repository 应按 source_snapshot_id 从 PG 内部读取并派生八维、window、attribution，或对调用方传值逐字段
   exact-match；当前 trigger 只覆盖八维，没有覆盖 window 与 attribution。
4. replay 比较应覆盖全部不可变业务列。`extra_explanation` 必须采用 NULL-safe exact equality；“双方均非空时
   才比较”会让 NULL 与对象互换时被静默当作同值重放。origin 列表还需确定性排序与 JSON 形状冻结。

并发 23505 查回应分别证明两个唯一键同义；若同一 idempotency_key 指向不同自然键，必须进入冲突分支，
而不是仅按其中一个键返回旧行。

## 七、R140-5：SKU subject key 与审计目标均缺实体落点

1. round-139 使用 `shop_listing_skus.public_id`，但当前表没有该列；`platform_sku_id` 又允许 NULL。
   `15-数据字典.md` 的“SKU=public_id”与已落 migration/catalog 存在历史差异。需走 D5 裁决：补稳定 public_id
   并同步 migration/T9 exact-set，或正式勘误为另一个稳定键并给出迁移兼容规则。
2. `roi_feedback_events` 也没有 public_id，而 `audit_events.target_public_id` 是 UUID NOT NULL。round-139 要求
   C2 写审计，却未定义五类 event 的可用 UUID target。应明确审计发生在 ledger 写入还是消费回写、目标实体、
   request_id、actor scope，以及 ledger 与 audit 是否同一事务。

这两项都不是实现时可临时选择的细节。

## 八、R140-6：M1/M2/M3 “直读 + 无回执”尚未形成消费闭环

只读查询证明事件可读取，并不证明消费端副作用已成功：

- M1 现有入口以交换文件和 category/period upsert 为中心；product_score 的持久化目标、事件级幂等键和成功结果
  尚未定义。
- M2 `receive_evaluation(asset_id, evaluation, ...)` 接受本地整数 asset_id 与三值枚举；PG 的
  `assets.public_id` 到 M2 asset_id 的映射、numeric 分档、重复调用审计语义均未冻结。
- M3 `ingest_m5_record` 按 platform_material_id + report_date 摄取素材表现，既不是 SKU 消费器，也不是 shop
  消费器；sku_margin/shop_strategy 的目标对象与落库入口仍为空。
- PG ledger 与现有 SQLite/本地库跨事务，需为每个消费者定义 durable receipt 或消费者侧稳定结果键、超时查回、
  重放和部分失败恢复。单纯“每次重算”只有在输出是纯函数且无副作用时才构成无回执方案。

round-141 请给出 M1/M2/M3 每条链的 exact-set：PG 查询条件、subject 映射、目标入口、目标持久化对象、
幂等键、成功回执、skip/fail 返回、重试与审计。U4/U5/U6/U8 必须完成裁决后再进入 C3。

## 九、round-141 交接要求

建议下一文件：

`from-dsh/round-141-dsh-P0-2批次2契约聚焦回修.md`

请按 R140-1~R140-6 回修，并附：

1. 版本选择四态及输入乱序黄金向量；
2. 单快照贡献或聚合结果模型的明确选择与唯一键/维度证明；
3. 五类 value exact-set、粒度去重规则及 Decimal 黄金向量；
4. `fb:v1:` 黄金向量、subject_key 规范化与完整 replay 比较集；
5. SKU 稳定键和 audit target 的 D5 裁决；
6. M1/M2/M3 三条真实入口、持久化结果和回执矩阵；
7. 更新后的批次 2 DAG，并明确哪些步骤触发 migration/T9 catalog 更新。

round-141 通过下一轮 CDX diff 后，再分别授权 C1、C2、C3 实体实现。批次 3 保持锁定。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-140-->
