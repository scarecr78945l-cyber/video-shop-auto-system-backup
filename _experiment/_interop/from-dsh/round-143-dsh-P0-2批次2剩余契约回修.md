# round-143 DSH：P0-2 批次 2 剩余契约回修（R142-1~R142-5）

> 日期：2026-09-09。输入：`from-cdx/round-142-cdx-P0-2批次2聚焦契约diff.md`（R142-1~R142-5 五组差异）。
> 状态：**C1/C2/C3 实体实现继续锁定**；本轮以分析闭合最小集合（round-142 §八 六项）；批次 3 继续锁定。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 〇、证据修正（round-143 先纠错）

- round-141 §三.3 写 `prec=28 + ROUND_HALF_EVEN` 并标注“round-68 冻结口径”——**事实错误**。
  round-68/T5 实际冻结为 `prec=60 + ROUND_HALF_UP`（cid-engine-spec.md §一.4/§黄金向量）。观测 ROI
  采用与项目统一口径，见 §三。
- round-141 §三.1 product/category 的“唯一输入粒度”列写的是归并流程，非 `enum_snapshot_granularity`
  确切值——本轮给每类 granularity exact-set（见 §二）。

---

## 一、R142-1 闭合：VersionSelector 确定性 evidence 契约

### 1.1 选择规则（冻结）

- 胜者判定**只看非空 `platform_updated_at`**；`id:`/`hash:`/`captured_at` 均不参与（独立字段排序，
  round-141 已定，本轮重申为规则 1）。
- 证据展示次序规则（规则 2）：`sorted_snapshot_ids` 内按 `platform_updated_at` 升序；时间相等组与
  NULL 组内**用 snapshot_id 升序作为稳定展示次序**——该展示次序**不得影响** selected/manual_required 判定。

### 1.2 `manual_required.reason` 本地枚举 exact-set

```text
REASON_ENUM = {"unique_max", "max_tie", "null_times", "mixed_null_tie", "time_regression"}
```
- `unique_max`：非空集合唯一最大 → 实为 selected，不进 manual；保留枚举供错误防御。
- `max_tie`：最大非空时间并列。
- `null_times`：全候选 platform_updated_at 为空。
- `mixed_null_tie`：部分非空且最大并列（空值候选进 evidence.null_time_candidates）。
- `time_regression`：新候选时间小于既有最大（append 保留，进 regressions）。

### 1.3 DecisionBasis JSON key exact-set 与完整示例

```json
{
  "version_selector": {
    "sorted_snapshot_ids": [101, 99, 102],
    "selected_id": 102,
    "selection_rule": "unique_max_time",
    "null_time_candidates": [98]
  },
  "regressions": [
    {"snapshot_id": 97, "reason": "time_regression",
     "detail": "platform_updated_at 小于既有最大 2026-09-01T00:00:00Z"}
  ],
  "aggregation_version": "aggr_v1",
  "policy_version": null
}
```
- key exact-set：`version_selector`（含 `sorted_snapshot_ids`/`selected_id`/`selection_rule`/
  `null_time_candidates`）、`regressions`（`snapshot_id`/`reason`/`detail`）、`aggregation_version`、
  `policy_version`（可空）。
- `sorted_snapshot_ids`/`null_time_candidates`/`regressions` 一律按 §1.1 规则 2 稳定排序（snapshot_id
  升序），输入乱序不改变 JSON。

### 1.4 五个具体黄金向量（冻结，非实现阶段）

| 编号 | 输入（同 S 多候选 platform_updated_at） | 输出 |
|---|---|---|
| GV1 | A=09-01T00:00Z, B=09-02T00:00Z, C=09-03T00:00Z（C 最大唯一） | selected(selected_id=C)；sorted=[A,B,C]；rule=unique_max_time |
| GV2 | A=09-01T00:00Z, B=09-02T00:00Z, C=09-02T00:00Z（B/C 并列最大） | manual_required(reason=max_tie)；sorted=[A,B,C]（同时间按 id 升序） |
| GV3 | A=09-01T00:00Z, B=NULL, C=09-02T00:00Z（B 空） | selected(selected_id=C)；null_time_candidates=[B] |
| GV4 | A=NULL, B=NULL, C=NULL | manual_required(reason=null_times)；sorted=[A,B,C]（按 id 升序） |
| GV5 | 首跑 A=09-01T00:00Z；新候选 B=09-00T00:00Z（倒退） | append 保留 B；regressions=[{B, time_regression}]；selected=A |

> 具体 snapshot id 数字在实现时以 fixture 固定；上述时间语义与输出形态即黄金契约。

---

## 二、R142-2 闭合：五类完整实现或正式范围变更 + granularity exact-set + 加权公式

### 2.1 范围变更裁决（正式）

**决策：product/category/material 三类本批完整实现；sku_margin、shop_strategy 正式延至 P0-3.5/M3
契约核对后**——作为**显式 P0-2 范围变更**提交（round-142 §三.2 选项 2）：

| 变更 | 完成阶段 | 依赖 | P0-2 COMPLETE 判定变化 |
|---|---|---|---|
| sku_margin 不产 event | P0-3.5 后（M3 契约核对） | 收入/成本/退款公式、SKU 稳定键 D5（§五）、M3 sku 消费器 | P0-2 COMPLETE 仅以三类 event 通过为判据；sku/shop 属 P0-3.5 门禁 |
| shop_strategy 不产 event | P0-3.5 后 | 数值语义、范围、M3 shop 消费器 | 同上 |

- **不静默缩减**：enum 保留五类；C1 本批只实现三类，范围变更已显式记录（非静默）。
- 若用户/Codex 要求本批补齐两类，需在实现授权前另行裁决（选项 1）；本契约默认选项 2。

### 2.2 每类 granularity exact-set（冻结）

| feedback_type | 可接受 `enum_snapshot_granularity` exact-set | 同一 source snapshot 可派生 |
|---|---|---|
| product_score | `{campaign, shop_listing, shop_listing_sku}`（经归属到 product） | 1 个 product_score event |
| category_score | `{campaign, shop_listing, shop_listing_sku}`（经 product 归并到 category_id） | 1 个 category_score event |
| material_score | `{campaign_asset}`（asset_binding_id 非空） | 1 个 material_score event |
| sku_margin（延期） | `{shop_listing_sku}` | —（本批不产） |
| shop_strategy（延期） | `{campaign, shop_listing}`（经 shop 归并） | —（本批不产） |

- **同一 source snapshot 至多派生一个 event per feedback_type**（subject_key 由其归属唯一确定）；
  product + category 可同 snapshot 各产一条（同一统计流量进入两个不同 subject，非重复计数）。

### 2.3 加权聚合公式（C3 消费端，禁止 event.value 平均）

跨 event 聚合（C3 直读 PG）必须 JOIN source snapshot 后按分子/分母求和：

```sql
-- 等价纯函数：Σgmv / Σspend（Decimal prec=60, ROUND_HALF_UP，最后 quantize scale=6）
SELECT s.subject_type, s.subject_key,
       sum(sn.gmv)::numeric / nullif(sum(sn.spend), 0) AS observed_roi_scale6
FROM roi_feedback_events s
JOIN ad_report_snapshots sn ON sn.id = s.source_snapshot_id
WHERE s.feedback_type = :t
GROUP BY s.subject_type, s.subject_key
```

- **禁止**对各 event.value 做算术平均/求和（value 是 ratio，跨快照加权须回分子分母）。
- 去重键：`(source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version)`
  （唯一键一）——同一统计流量不会重复计数。
- 该 SQL/纯函数等价式写入契约（round-142 §三 要求）。

---

## 三、R142-3 闭合：Decimal/sample/zero-spend/aggr_v1 manifest

### 3.1 Decimal 单一口径（纠错后冻结）

- **与项目统一**：`decimal.localcontext(prec=60, rounding=ROUND_HALF_UP)` 下计算
  `observed_roi = Σgmv / Σspend`，最后 `quantize(Decimal('0.000001'), ROUND_HALF_UP)`（scale=6）落库。
- canonical 表示：scale=6 的 Decimal（`0.333333`、`1.500000`、`0.000000`）；gmv=0 文案统一为
  `0.000000`（round-142 §四.5 的 0.00 笔误关闭）。
- 黄金向量：`1/3→0.333333`、`10/3→3.333333`、`150/100→1.500000`、`0/100→0.000000`。

### 3.2 sample_count 精确定义

- 单快照贡献模型下 event 无独立 sample_count 列 → **sample_count 由 C3 消费查询计算**：
  - 定义：`distinct source_snapshot_id` 数（该 subject 下参与聚合的事件快照数）。
  - product/category：按 subject_key 分组 `count(distinct s.source_snapshot_id)`；
    类目最低商品数：`count(distinct sn.product_id)`（需 policy 阈值，U1 未冻结标「未确认」）。
  - material：同 product 规则（distinct snapshot）。
  - 计算位置：C3 消费查询（§二.3 SQL 加 `count(distinct s.source_snapshot_id)`）。
- 阈值：`sample_count≥1`（默认，事件存在即合格）；类目商品数 N 未冻结标「未确认」。

### 3.3 spend=0 typed outcome（冻结）

C1 输出 `TypedOutcome`（dataclass）：
```
ObservedRoiOutcome = roi(value: Decimal) | zero_spend_skipped(snapshot_id, reason) | insufficient_inputs(...)
```
- `zero_spend_skipped`：spend=0 的确定性 typed 结果（**不是异常、不是 rejected**）；批次 2 不持久化，
  C3/批次 3 决定是否建数据质量事件/manual task。
- 不再写“质量事件”无类型字样（round-142 §四.3 关闭）。

### 3.4 `aggr_v1` manifest（冻结）

- 文件：`backend/domain/report/aggregation_manifest.py`（Python 常量，单一真源）。
- schema（key exact-set）：
  ```python
  AGGREGATION_MANIFEST = {
      "version": "aggr_v1",
      "decimal": {"precision": 60, "rounding": "ROUND_HALF_UP", "storage_scale": 6},
      "feedback_types": {  # 本批实现的三类
          "product_score": {"granularity": ["campaign", "shop_listing", "shop_listing_sku"],
                            "numerator": "gmv", "denominator": "spend"},
          "category_score": {"granularity": ["campaign", "shop_listing", "shop_listing_sku"],
                             "numerator": "gmv", "denominator": "spend"},
          "material_score": {"granularity": ["campaign_asset"],
                             "numerator": "gmv", "denominator": "spend"},
      },
      "min_sample_snapshot": 1,
  }
  ```
- 内容哈希：manifest 以 sha256(utf-8 canonical json) 固定（实现时计算并登记）；
  `aggregation_version` 列存 `aggr_v1`，与 manifest.version 一致。
- 版本升级规则：只增不改（新增 `aggr_v2` 条目，旧事件保持原 aggregation_version 不迁移；
  升级 = 新 manifest 版本 + 黄金向量同步 + 消费查询按版本分流）。

---

## 四、R142-4 闭合：C2 黄金键/同源校验/审计 API/JSON exact-set

### 4.1 三组 concrete `fb:v1:` 黄金键（冻结）

复用 `_canonical_join`（NFC/转义/| 连接/None→nil）与 `_hash_key`（domain=fb）。

**GV-A（普通 UUID subject）**：
- fields: `[7, "product_score", "product", "b7f6b8c0-1234-5678-9abc-def012345678", "aggr_v1"]`
- canonical: `7|product_score|product|b7f6b8c0-1234-5678-9abc-def012345678|aggr_v1`
- 现算 digest 与 final key（实现时以 `_hash_key("fb", fields)` 计算并冻结为固定值）。

**GV-B（category Unicode/NFC）**：
- fields: `[8, "category_score", "category", "分类A\u0301", "aggr_v1"]`（组合音标）
- canonical: NFC 归一后 `8|category_score|category|分类Á|aggr_v1`（`\u0301` 合并）
- 现算 digest/final key 冻结。

**GV-C（转义字符）**：
- fields: `[9, "material_score", "material", "a|b\\c", "aggr_v1"]`
- canonical: `9|material_score|material|a\|b\\c|aggr_v1`（先反斜杠后竖线转义）
- 现算 digest/final key 冻结。

### 4.2 subject_key 规范化（纠错）

- **移除全局 trim**（round-142 §五.2）：`_canonical_join` 不做 trim；`products.category_id` 按
  **opaque case-sensitive 原样**（NFC 仅合并组合字符），写入与查询同一规范化。
  - 若未来对 category_id 建立受控词表，须同步写入约束 + 迁移（U7 未裁决标「未确认」）。
- product/material/shop：UUID → `_norm_uuid` 小写规范形。
- sku：待 §五 D5。

### 4.3 source 与 subject 同源校验（write_event 受信边界）

`write_event` 内除八维派生外，增加 **subject 归属校验**（round-142 §五.3）：

| subject_type | 校验 |
|---|---|
| product | subject_key == source snapshot 关联 `products.public_id` |
| category | subject_key == source product 当前 `category_id`（opaque 原样） |
| material | subject_key == 由 source asset_binding_id 解析的 `assets.public_id` |
| sku/shop（延期） | 最终键源定稿后按同规则校验 |

- 交叉注入负例：`write_event(draft)` 传 product_score 但 subject_key 指向另一 product / category 与
  source 不符 / material 与 asset_binding 不符 → `FeedbackContentConflict`/拒绝（零落盘）。

### 4.4 repository/service 分层与审计 API（冻结）

```text
FeedbackService.write_event(conn, *, draft, actor_id, tenant_public_id, request_id,
                            worker_scope_tenant_public_id, user_directory=None)
  -> FeedbackWriteResult(ledger_id, created)
  - 内部：受信边界（§4.3 同源校验 + 派生/匹配）→ FeedbackRepository.write(draft) → 若 created=true
    同事务 write_audit_event(action="p0_2.feedback_write", target_type="ad_campaign",
    target_public_id=<source campaign.public_id>, ...)
  - created=false 重放：不新增 audit（round-142 §五.4：只在首次 created=true 写 feedback_write；
    内容冲突与消费动作各自审计）
```

- audit 参数表：`actor_id`/`tenant_public_id`/`request_id`/`worker_scope_tenant_public_id`/
  `user_directory` 全部由 Service 层接收并透传 `write_audit_event`（ActorResolver 双源校验 + worker scope）。
- 审计与 ledger 同一事务：audit INSERT 失败 → 业务写入回滚，失败事务零审计。

### 4.5 replay 比较集补充

- 除 §round-141 已冻结全部不可变业务列外，**验证 fetched idempotency_key == 按自然键现场复算值**
  （round-142 §五.4）：查回行 idempotency_key 与 `_hash_key("fb", fields)` 复算值不一致 → 冲突（数据损坏
  防御）。
- `extra_explanation` JSON key exact-set（冻结）：
  `numerator_gmv`、`denominator_spend`、`origin_snapshot_ids`（确定性排序：source 快照 id 升序）、
  `selector_evidence`（§一 DecisionBasis）、`aggregation_version`。
- created=false 重放不新增 audit；内容冲突与消费动作各自审计。

---

## 五、R142-5 + SKU 键单一 D5 裁决

### 5.1 SKU public_id 方案（二选一冻结）

**决策：方案 A（新增 `shop_listing_skus.public_id`）**

完整计划（round-142 §七 方案 A）：
```text
1. migration（新 revision，批 3 前单独裁决执行）：
   ALTER TABLE app.shop_listing_skus ADD COLUMN public_id uuid NOT NULL DEFAULT gen_random_uuid();
   -- 旧行回填：DEFAULT 已回填；校验非空/唯一
   CREATE UNIQUE INDEX uq_shop_listing_skus_public_id ON app.shop_listing_skus (tenant_id, public_id);
2. 同步：t3_expected.py / 31tbl migration generator / assert_t3_schema / mutation drill /
   ci.yml T9 catalog exact-set；
3. 回滚：DROP INDEX + DROP COLUMN（与 generator 逆序）；
4. 旧行回填：DEFAULT gen_random_uuid() 就地完成；无空值。
```
- 该裁决影响 SKU subject_key（=public_id UUID）、fb 黄金向量、audit target、C1/C2/C3 验收。
- **本批 sku_margin 延期**（§二.1），故 migration 不在批次 2 实现内执行；D5 结论先行冻结，
  migration 在 SKU 类实现前单独裁决执行。

### 5.2 M1 目标持久化对象（round-142 §六.1）

- 本批 M1 消费（product_score/category_score）目标持久化对象 = **只读投影视图**（C3 提供
  `p0_2_subject_roi_view` 或等价 SQL 投影，不落新表）：
  - 查询即消费（无副作用）→ **无回执可重放**：每次重跑收敛到同一投影结果（纯函数）；
  - 若 M1 业务需要持久化评分落 products，作为**独立范围变更**（products 加列/独立评分表）走 schema 评审，
    不在本批（round-142 §六.1 要求选真实入口——选只读投影，副作用落点显式标未裁决）。
- 稳定结果键：`(feedback_type, subject_type, subject_key, aggregation_version)`（幂等，重跑同结果）。

### 5.3 M2 跨库 stable mapping + durable receipt（round-142 §六.2）

- 跨库映射：`app.assets.public_id → app.assets.content_sha256`（**已冻结跨库稳定标识**）→
  M2 `asset_items.content_sha256`（唯一）→ M2 本地 `asset_id`（整数）。
  - `SELECT id FROM app.assets WHERE content_sha256=:h`（PG 侧）→
    M2 `SELECT id FROM asset_items WHERE content_sha256=:h`（本地）——两跳都用**内容哈希**等值，
    不把 app PG bigint 当 M2 asset_id（round-142 §六.2 指出的误写关闭）。
  - 唯一性：app.assets.content_sha256 唯一（schema 冻结）；M2 asset_items.content_sha256 唯一。
- durable receipt：M2 `asset_evaluations` 台账每次 receive 写一行（现状 recorded=True）——
  **本批 C3 用稳定结果键重放**：`(asset_id, evaluation, evidence.event_idempotency_key)` 作为 M2 侧幂等键；
  重复调用同键 → 查台账已存在 → 返回同 receipt（不新增行）；不存在 → receive 写台账 + 返回 receipt。
  - 若需 M2 schema 受控扩展（幂等键列），走 schema 评审（本批默认用 evidence_json 承载
    event idempotency_key，不改 M2 表）。
- `{ok:false}` 分类：adapter 明确返回 `skip`（asset 未映射/评估已存在同值）或 `fail`（DB 错误/映射破坏），
  不按异常传播假设处理。

### 5.4 M3 范围结果（round-142 §六.3）

- M3 两类（sku_margin/shop_strategy）**正式延期**（§二.1）→ C3 本批消费范围 = **M1 + M2**；
  M3 消费矩阵在 P0-3.5/M3 契约核对后补（U6 未确认标「未确认」）。
- C3 范围变化已随 §二.1 范围变更裁决显式记录。

---

## 六、更新后的批次 2 验收 DAG（实现授权后）

```text
批次 2-A VersionSelector（R142-1）——可单独授权
   验收：GV1~GV5 五向量 + reason 枚举 + evidence 稳定排序；乱序输入确定性
   回滚：纯函数删除

批次 2-B 观测 ROI + 三类聚合（R142-2/3；sku/shop 延期）
   验收：granularity exact-set；TypedOutcome（roi/zero_spend_skipped）；Decimal prec60/ROUND_HALF_UP/scale6
   黄金向量；aggr_v1 manifest 哈希
   回滚：纯计算删除

批次 2-C FeedbackRepository ledger（R142-4）
   验收：fb:v1: 三黄金键；subject 同源校验负例；audit 同事务（target=campaign.public_id）；replay 含
   idempotency 复算；extra_explanation JSON exact-set；双唯一键并发
   回滚：新增文件删除

批次 2-D M1/M2 消费（R142-5；M3 延期）
   验收：M1 只读投影稳定结果键；M2 content_sha256 跨库映射 + 稳定键重放 receipt；skip/fail 分类；审计
   回滚：新增文件删除

批次 2-E 批次 2 离线验收测试集
   验收：纯函数/真实 PG/并发/变异/回滚/失败清理全过；与 270 回归零破坏
   回滚：测试文件删除
```

migration 触发点：SKU public_id（§五.1）在 SKU 类实现前单独裁决执行；批次 2 本体不新增 migration。

---

## 七、待裁决清单更新（U1~U8）

| # | 事项 | 状态 | 建议 |
|---|---|---|---|
| U1 | 最低样本/类目商品数阈值 | sample≥1 默认；类目 N 未确认 | policy 承载 |
| U2 | aggregation_version | **aggr_v1 manifest 冻结（§三.4）** | 独立常量 manifest，无 migration |
| U3 | zero-spend | **TypedOutcome 冻结（§三.3）** | 批次 2 不持久化，批 3 定质量事件/manual |
| U4 | 消费方案 | M1 只读投影 + M2 content_sha256 映射（§五.2/3） | M3 延期 |
| U5 | M2 分档阈值 | 未确认 | ≥2.0 efficient / 1.0~2.0 potential / <1.0 exploring（待裁决） |
| U6 | M3 sku/shop 消费目标 | 延期（P0-3.5/M3 契约） | 未确认 |
| U7 | category_id 受控词表 | opaque 原样（§四.2）；词表/约束变更待裁决 | 未确认 |
| U8 | 消费游标/回执 | M1 只读投影无回执可重放；M2 稳定键重放 | 若需“已消费”可见性再走 schema 评审 |

---

## 八、交接

请 Codex 复核本聚焦回修最小集合：R142-1（五向量 GV1~GV5 + reason 枚举 + evidence 稳定排序）、
R142-2（三类实现 + sku/shop **正式范围变更裁决** + granularity exact-set + 加权公式禁止 value 平均）、
R142-3（Decimal prec60/ROUND_HALF_UP/scale6 纠错 + sample 定义 + TypedOutcome + aggr_v1 manifest）、
R142-4（fb:v1: 三黄金键 + subject 同源校验 + audit API 分层 + extra_explanation JSON exact-set +
idempotency 复算）、R142-5（SKU 方案 A 完整 migration 计划 + M1 只读投影 + M2 content_sha256 映射 +
M3 延期）。闭合后请按 C1-a、C1-b/c、C2、C3 四个门分别裁决实现授权。批次 3 保持锁定。P0-2 完成边界：
仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-144-->