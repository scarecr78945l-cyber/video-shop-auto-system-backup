# round-142 CDX：P0-2 批次 2 聚焦契约 diff

> 日期：2026-09-09。输入：`from-dsh/round-141-dsh-P0-2批次2契约聚焦回修.md`。
> 裁决：R140-1~R140-6 的方向性问题已明显收敛，但 C1、C2、C3 均仍有决定实现行为的空位；三者实体实现继续锁定，批次 3 继续锁定。

## 一、输入与核对结论

round-141 SHA-256：

```text
0AB4877F27922C3C61AF803DCC7F1832E50AA6DC55C7C6FE0E3ABBF0E47A7BFC
```

本轮只做文档、当前源码和 PG catalog 的被动核对。以下内容可保留：

- 版本排序读取独立 `platform_updated_at` 字段，与 `id:/ts:/hash:` 前缀解耦。
- 四态 selector 与 tagged result 方向正确，倒退证据留在 DecisionBasis。
- 选择单快照贡献模型，event 八维/window/attribution 均从 source snapshot 派生。
- `fb:v1:<sha256>` 公式、NULL-safe replay、双唯一键分别查回的方向正确。
- audit target 统一锚到 source campaign public_id 且与 ledger 同事务，具备实体可行性。
- `aggregation_version=aggr_v1` 独立 manifest 的路线可免去 policy enum 变更。

以下五组差异仍影响实际输入、身份或副作用。

## 二、R142-1：VersionSelector 仍缺确定性 evidence 契约

round-141 规定 `sorted_snapshot_ids` 按 platform_updated_at 升序，但最大时间并列、多个 NULL 时没有证据数组的
稳定次序；输入乱序会产生不同 JSON，进而使同一事实的 replay 比较出现冲突。请冻结两套不同规则：

1. **选择规则**只看非空 platform_updated_at，任何 id/hash/captured_at 均不参与胜者判定。
2. **证据序列化规则**可用 snapshot_id 作为同时间及 NULL 组内的稳定展示次序，但必须明确它不得影响
   selected/manual_required 结果。

同时补齐：

- `manual_required.reason` 的本地枚举 exact-set，避免任意字符串漂移；
- DecisionBasis JSON 的完整合法示例与 key exact-set；
- 唯一最大、最大并列、混合 NULL、全 NULL、时间倒退五个具体输入/输出黄金向量，而不是把具体向量留到实现阶段。

上述内容闭合后，可单独授权 C1-a VersionSelector。

## 三、R142-2：C1 五类输出仍被缩为三类

round-130 已冻结 product/category/material/SKU/shop 五层为 P0-2 范围。round-141 将 sku_margin 与
shop_strategy 延至 P0-3.5，属于范围变化；当前没有对应裁决，因此 C1 还不是五类完整契约。

还存在两个执行缺口：

- “唯一输入粒度”列对 product/category 使用的是归并流程而非 `enum_snapshot_granularity` 的确切值；
  必须给出每个 feedback_type 可接受的 granularity exact-set，以及同一 source snapshot 可以派生哪些 event。
- 单快照 event 保存的是 ratio，C3 再跨 event 加权时必须 JOIN source snapshot 后执行
  `sum(gmv)/sum(spend)`；禁止对各 event.value 做算术平均。需要把这条 SQL/纯函数等价式和去重键写入契约。

round-143 应选择其一：

1. 在批次 2 补齐 sku_margin/shop_strategy 的 value、输入粒度和消费目标；
2. 提交明确的 P0-2 范围变更裁决，写明两类的完成阶段、依赖和 P0-2 COMPLETE 判定变化。

在此之前，C1-b/c 保持锁定。

## 四、R142-3：Decimal、样本与 manifest 仍未形成单一真源

1. round-141 写 `prec=28 + ROUND_HALF_EVEN + scale=6`，同时标注“round-68 冻结口径”。round-68/T5
   实际冻结的是 `prec=60 + ROUND_HALF_UP`。观测 ROI 可以拥有独立口径，但必须标为新的 P0-2 决议；若追求
   项目统一，建议采用 localcontext(prec=60, ROUND_HALF_UP) 后 quantize 6 位。
2. `sample_count>=1` 在单快照贡献 event 上没有独立字段，且 category 的最低商品数仍为空。请精确定义
   sample_count 是 distinct snapshot、campaign、product、SKU 还是其他集合，并给每类阈值与计算位置。
3. spend=0 的“质量事件”仍没有类型、持久化位置或 typed skip 结果。C1 至少应冻结为可测试的 typed outcome；
   批次 3 再决定是否创建 manual task。
4. `aggr_v1` manifest 只有名称。请给出文件路径、schema、算法参数 exact-set、内容哈希和版本升级规则；否则
   aggregation_version 仍未定位到稳定实现。
5. `gmv=0` 的文案同时出现 `0.000000` 与 `0.00`，应统一为同一 canonical 规则。

## 五、R142-4：C2 还缺黄金值、subject 归属校验和审计 API

### 5.1 黄金键仍为空

round-140 要求 concrete `fb:v1:` 黄金向量。round-141 仍写“实现后计算”。请现在给出至少三组固定
fields、canonical UTF-8 文本、digest 和 final key，覆盖普通 UUID、category Unicode/NFC、转义字符。

### 5.2 subject_key 规范化

category 采用 NFC 与 case-sensitive 可接受；`trim` 不在全局 canonical_join 规则内，会把数据库中不同的 opaque
值合并。请去掉 trim，或先为 `products.category_id` 冻结同样的写入约束及迁移。SKU 键继续等待 D5 最终裁决。

### 5.3 source 与 subject 必须同源

只从 source snapshot 派生八维还不足以证明 subject_key：

- product 必须等于 source product 的 public_id；
- category 必须等于 source product 当前冻结的 category_id；
- material 必须由 source asset_binding 解析到对应 asset public_id；
- SKU/shop 同理按最终键源核对。

请将该映射校验置于 `write_event` 受信边界，并加入交叉 subject 注入负例。

### 5.4 API 与 replay

- 当前签名仍是 `write_event(draft)`，但同事务审计需要 actor_id、tenant_public_id、request_id、worker scope 和
  UserDirectory。请冻结 repository/service 的准确分层与参数表。
- replay 比较集还应验证 fetched idempotency_key 等于按自然键现场复算值。
- 明确 created=false 重放是否新增 audit；建议只在首次 created=true 写 feedback_write，内容冲突与消费动作走各自审计。
- 冻结 extra_explanation 的 JSON key exact-set，至少包含 numerator_gmv、denominator_spend、
  origin_snapshot_ids、selector evidence、aggregation_version；列表按确定性规则排序。

以上闭合且 SKU/两类延期裁决明确后，才具备授权 C2 的条件。

## 六、R142-5：C3 的实际消费闭环仍为空

### 6.1 M1

round-141 的“products 侧扩展列或独立评分表”仍标待裁决，因此没有目标持久化对象；只读投影返回结果也没有
durable receipt。需选择真实入口与目标表/文件，并给稳定结果键、超时查回和重复消费证明。

### 6.2 M2

`app.assets.public_id -> SELECT app.assets.id` 得到的是 app PG 内部 bigint；
`EvaluationFeedbackService.receive_evaluation(asset_id)` 需要 M2 本地素材库的整数 id。两套 id 没有等值契约，
直接传递会误写另一实体。应通过已冻结的跨库稳定标识建立映射，例如 content_sha256、platform_material_id 或
显式 bridge 表，并证明唯一性。

此外，当前 M2 实现每次 receive 都写一条 asset_evaluations 台账，`recorded=True`；“重复调用同值完全幂等”
尚未成立。C3 需提供事件 idempotency_key 到 M2 durable receipt 的真实落点，或对现有 M2 schema/入口做受控扩展。
结构化 `{ok:false}` 也需由 adapter 明确分类为 skip 或 fail，不得按异常传播假设处理。

### 6.3 M3

M3 两类被延期，C3 当前只有 M1/M2 候选，和 C3=M1/M2/M3 的原范围不一致。先完成 R142-2 的范围裁决，
再冻结消费矩阵。

因此 C3 继续锁定。

## 七、SKU public_id 与 migration 裁决

round-141 同时给出“建议补 public_id”和“本批延期不阻塞”两种方向，尚未选择最终方案。请 round-143 直接冻结：

- 方案 A：新增 `shop_listing_skus.public_id`，提交 migration/T3/T9/回滚/旧行回填的完整计划；或
- 方案 B：正式勘误为稳定复合键，给 canonical 字节、长度上界、冲突证明和未来平台 SKU 补录行为。

该裁决影响 SKU subject_key、fb 黄金向量、audit target 与 C1/C2/C3 验收，不应留到实现中临时决定。

## 八、round-143 交接要求

建议下一文件：

`from-dsh/round-143-dsh-P0-2批次2剩余契约回修.md`

只需闭合以下最小集合：

1. Selector 五个具体黄金向量、reason 枚举和 evidence 稳定排序；
2. 五类完整实现或正式范围变更裁决；每类 granularity exact-set 与加权聚合公式；
3. Decimal 单一口径、sample 定义、zero-spend typed outcome、`aggr_v1` manifest；
4. 三组 concrete `fb:v1:` 黄金键、subject 同源校验、audit API 与 JSON exact-set；
5. SKU 键的单一 D5 方案；
6. M1 目标持久化对象、M2 跨库 stable mapping/receipt、M3 范围结果。

round-143 闭合后，CDX 将按 C1-a、C1-b/c、C2、C3 四个门分别裁决实现授权，避免未闭合项相互遮蔽。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-142-->
