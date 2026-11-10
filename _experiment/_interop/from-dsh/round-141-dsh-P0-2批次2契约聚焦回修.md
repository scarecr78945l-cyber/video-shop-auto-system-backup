# round-141 DSH：P0-2 批次 2 契约聚焦回修（R140-1~R140-6）

> 日期：2026-09-09。输入：`from-cdx/round-140-cdx-P0-2批次2契约diff.md`（R140-1~R140-6 六组差异）。
> 状态：**批次 2 C1/C2/C3 实体实现继续锁定**；本轮以分析形成可冻结契约候选；批次 3 继续锁定。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 〇、证据锚点（本轮决议均以冻结 schema/代码为准）

```text
ad_report_snapshots: id/source 八维/window_start/end/attribution_mode/report_version_key/
  platform_updated_at timestamptz NOT NULL（F132-1 已勘误→现可空，round-131 落实）/spend/gmv/.../raw_evidence_hash
shop_listing_skus columns = id,tenant_id,shop_listing_id,sku_id,platform_sku_id(可空),shop_price,
  promo_price,floor_price,allocated_stock,safety_stock,listing_status,rejection_reason,created_at,updated_at
  → **无 public_id**；platform_sku_id 可空
enum_policy_type = cid_breakeven,pricing,compliance,whitelist,budget,stop_loss,rate_limit,gate
  → **无 aggregation 类型**
roi_feedback_events: 单 source_snapshot_id NOT NULL; 单 value numeric NOT NULL; extra_explanation jsonb 可空;
  唯一键一 (source_snapshot_id,feedback_type,subject_type,subject_key,aggregation_version)
  唯一键二 (tenant_id,idempotency_key)
  trigger trg_feedback_dimension_consistency：八维与该 source_snapshot 对应快照逐字段一致
audit_events: target_public_id uuid NOT NULL; action varchar(64); write_audit_event(actor_id, tenant_public_id,
  action, target_type, target_public_id, request_id,...) 内用 ActorResolver+worker scope
backend/domain/workflow/queue.py: _canonical_join(NFC/转义/| 连接/None→nil)、_hash_key(domain,fields)=domain:v1:sha256hex、
  _norm_uuid(小写规范形)
M3 ingest_m5_record(db, record): platform_material_id 反查 opt_video_variants；幂等 (variant_id, report_date)
M2 receive_evaluation(asset_id:int, evaluation:3枚举, evidence, source_agent): 幂等审计；asset_id 为本地整数
```

---

## 一、R140-1 闭合：版本选择可执行边界

### 1.1 排序字段独立（不依赖 version-key 前缀）

- **排序只读独立字段 `platform_updated_at`**，与 `report_version_key` 前缀（`id:`/`ts:`/`hash:`）无关。
  `id:<token>` 快照仍可携带非空 platform_updated_at 并参与排序（round-140 指出的语义分歧关闭）。
  `ts:` 源仅是 version-key 生成的降级路径，不是排序依据。

### 1.2 候选身份 exact-set 与混合空值

统计身份 S =（tenant_id, campaign_id, granularity, shop_listing_sku_id, asset_binding_id,
window_start, window_end, attribution_mode）——与批次 1 唯一键逐字段一致。
同 S 多 V：
- 全部非空：唯一最大 → selected；最大并列 → manual_required。
- 部分非空、部分空：**只在非空集合中取唯一最大**；空值候选进入 `evidence.null_time_candidates`，
  不参与比较；非空集合最大并列 → manual_required。
- 全部空：manual_required。

### 1.3 输出 tagged result（确定性）

```
VersionSelectorResult = selected(snapshot_id: int, evidence: DecisionBasis)
                      | manual_required(reason: str, evidence: DecisionBasis)
```
批次 2 只返回结果，不创建 manual task（批次 3 消费 automated/manual 触达）。

`DecisionBasis`（jsonb 形状冻结，供 ledger 复制与批次 3）：
```json
{"version_selector": {"sorted_snapshot_ids": [..按 platform_updated_at 升序..],
   "selected_id": 123, "selection_rule": "unique_max_time", "null_time_candidates": [..]}
 "regressions": [{"snapshot_id": .., "reason": "time_regression", "detail": "ts 小于既有最大"}],
 "aggregation_version": "aggr_v1", "policy_version": null_if_absent}
```

### 1.4 时间倒退（R140-1.4）

批次 2 选择器不写 snapshot 表（无该列）。倒退快照列表放入 `DecisionBasis.regressions`；
成功生成 ledger 时复制进 `event.extra_explanation`；返回 manual_required 时证据交批次 3。

### 1.5 golden 向量（输入乱序确定性）

- 同 S 下 V1/V2/V3 的不同输入顺序 → 排序结果（`sorted_snapshot_ids`、selected_id）与顺序无关
  （对 platform_updated_at 为唯一最大情形，结果唯一）。
- 相等时间各候选 → manual_required（不猜序）。
- 混合空值 → selected 只在非空集合确定时给出，空值进 evidence。

> 具体黄金向量在批次 2 实现授权后形成（纯函数测试）；本轮冻结**规则**与 tagged result 形状。

---

## 二、R140-2 闭合：确立**单快照贡献模型**

**选定模型：单快照贡献（Single-Snapshot Contribution）**，理由：

1. 现有 `roi_feedback_events` 是**单 source_snapshot_id + 单 value**，唯一键一含 source_snapshot_id，
   trigger 要求八维与该单快照逐字段一致——聚合结果模型需要 schema 变更（aggregation identity/input-set hash +
   唯一键/维度约束调整），代价高于价值。
2. 单快照模型无 migration、append-only 语义与批次 1 一致、可重放。

**定义（冻结）**：
- **ledger 每行严格由一个 source snapshot 派生**。跨快照（product/category/shop 多 campaign/listing/asset）
  聚合**移到消费查询**（C3 直读 PG 时 JOIN + 聚合），event 保存足够的分子/分母证据 + 去重/加权规则。
- event 的八维 = source snapshot 的八维（trigger 已强制逐字段一致）；window/attribution 同样取自
  source snapshot（R140-4.3 冻结：repo 从 PG 读取派生，或调用方逐字段 exact-match）。
- `extra_explanation` 记录：该行**直接贡献的**聚合身份（subject_key）+ `origin_snapshot_ids`
  = [source_snapshot_id]（单快照）→ 确定性排序、JSON 形状冻结（见 §五.4）。
- **粒度去重规则（R140-2 混合粒度重复流量）**：五类 event 各自声明唯一输入粒度（§三 行为表）；
  消费端按 subject_key + 唯一输入粒度聚合，禁止同一业务流量被多个粒度重复计数
  （例如 campaign + shop_listing 混合求和只允许属于不同统计身份的行，同一 campaign 只算一次）。

**真值表（单快照贡献）**：

| 输入 | 处理 |
|---|---|
| 单快照，单 subject | 该快照派生 1 event（value=该快照 gmv/spend 或映射） |
| 多快照（同 product 多 campaign） | C2 只接收单快照 → 其余快照在 C3 消费查询聚合（JOIN products.ad_campaigns 归并） |
| category/shop 跨多 product/listing | event 八维复制 source snapshot；跨集合在 C3 消费查询归并（subject_key 分组） |
| 同 subject 多粒度求和 | 消费端按**唯一输入粒度**去重（§三 输入粒度列） |

> 若未来需“聚合结果模型”，走 D5 schema 变更评审（新增 aggregation identity/input-set hash + 调整唯一键/维度
> 约束）——当前不做。

---

## 三、R140-3 闭合：五类 value exact-set 与确定性数值

### 3.1 五行 exact-set

| feedback_type | subject_type | 唯一输入粒度 | 分组键（subject_key） | 窗口/attribution 约束 | 分子 | 分母 | value 单位/范围 | 最低样本动作 | 零值动作 |
|---|---|---|---|---|---|---|---|---|---|
| product_score | product | campaign→listing→product 归并（每 campaign 一行） | `products.public_id`（小写 UUID） | 同 window/attribution 的 campaign | Σgmv | Σspend | 观测 ROI≥0（Decimal） | 未冻结（U1 未裁决：policy 定义，不硬编码） | spend=0 → 不产出（skip+质量事件按策略，U3 未裁决） |
| category_score | category | product 级再按 `products.category_id` 归并 | `category_id`（opaque case-sensitive 稳定键，U7 未裁决受控词表） | 同 window/attribution | Σgmv | Σspend | 观测 ROI≥0 | 未冻结 | spend=0 → skip |
| material_score | material | campaign_asset 粒度（asset_binding_id） | `assets.public_id`（小写 UUID） | 同 window/attribution | Σgmv | Σspend | 观测 ROI≥0 | 未冻结 | spend=0 → skip |
| sku_margin | sku | shop_listing_sku 粒度 | **见 R140-5（SKU 稳定键待 D5 裁决）** | 同 window/attribution | **需收入/成本/退款/补贴公式** → 本批延期（见 3.2） | | 分 int | — | — |
| shop_strategy | shop | shop 粒度/多 listing 归并 | `shops.public_id`（小写 UUID） | 同 window/attribution | **数值含义/范围/消费动作未冻结** → 本批延期（见 3.2） | | — | — | — |

### 3.2 本批延期声明（不改静默缩减）

- **sku_margin 与 shop_strategy 本批延期**作为**显式范围变更**：value 语义、收入/成本/退款公式、范围与消费动作
  （M3 无 SKU/shop 消费器）需 P0-3.5/M3 契约核对后定义；延期不删除 event 类型/枚举，只是 C1/C2 本批不产这两类行
  （不静默缩减五层——范围变更单独裁决，round-140 §五 要求）。
- `product_score`/`category_score`/`material_score` 本批实现，value = 观测 ROI。

### 3.3 Decimal 确定性数值（黄金向量规则）

- 工作精度：**28 位**（`decimal.Context(prec=28)`）；舍入模式：`ROUND_HALF_EVEN`（银行家舍入）。
- `observed_roi = Σgmv / Σspend`；落库 value 为 `quantize` 到 **scale=6** 的 canonical 十进制表示
  （round-68 冻结口径；`1/3 → 0.333333`，避免 `1/3` 无唯一 full-precision 结果）。
- 落库 scale：`roi_feedback_events.value numeric` 实际存储 scale=6 的 `Decimal`；
  `spend=0` → 不产出见 §三.1。
- **黄金向量**（实现授权后纯函数测试）：`gmv=1, spend=3 → 0.333333`；`gmv=10, spend=3 → 3.333333`；
  `gmv=150, spend=100 → 1.500000`；`gmv=0, spend=100 → 0.000000`。
- `out` 分 int 作输入；`gmv/spend` 用 Decimal（输入转 Decimal 再除，禁止 float 中间量）。

### 3.4 U1/U2/U3 推进（从「未确认」到可执行值建议）

| 项 | 建议（待裁决） |
|---|---|
| U1 最低样本 | 版本化 policy 承载；默认 **sample_count≥1**（单快照贡献模型下每条 event 有快照即合格）；
  类目达 N 商品 + 样本阈值才**影响**消费评分（N 未裁决，标「未确认」） |
| U2 aggregation_version | **冻结独立常量 `aggr_v1` 与配置 manifest**（不新增 enum_policy_type）；`enum_policy_type` 无
  aggregation 类型，不走 migration——避免 schema 变更（round-140 §五 两选一：选独立常量 manifest） |
| U3 零消耗 | spend=0 → skip + 数据质量事件（冻结错误码策略）；gmv=0,spend>0 → 产出 value=0.000000 事件（可调，U3 建议采纳） |

---

## 四、R140-4 闭合：FeedbackRepository 边界与键公式

### 4.1 `fb:v1:` 黄金公式（冻结）

```
fb:v1:<lower_hex_sha256(canonical_join([
    source_snapshot_id,            # int
    feedback_type,                 # str
    subject_type,                  # str
    subject_key,                   # str（按 §4.2 规范化后）
    aggregation_version,           # str（aggr_v1）
]))>
```
- 复用 `backend/domain/workflow/queue.py` 的 `_canonical_join`/`_hash_key`（NFC/转义/| 连接/None→nil）。
- 输入序固定：source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version
  （idempotency.md §三 键 9 canonical_join 顺序一致，round-140 §六.1 关闭明文拼接）。
- 黄金向量（实现授权后固化）：示例 `source=1, product_score, product, <uuid>, aggr_v1` → 具体 hex 在实现时计算并冻结。

### 4.2 subject_key 规范化（按类型冻结）

- product/material/shop：`assets.public_id`/`products.public_id`/`shops.public_id`（UUID）→ `_norm_uuid` 小写规范形。
- category：`products.category_id`（opaque）→ NFC + trim；case-sensitive 原样保留（U7 未裁决受控词表，先按 opaque 稳定键）。
- sku：待 R140-5 D5 裁决（见 §五）。

### 4.3 repo 内部派生 vs 调用方传值

`FeedbackRepository.write_event(draft)` 的受信边界：
- **从 PG 按 source_snapshot_id 读取**该快照的八维/window/attribution/分母分子，用于：
  1. 派生 event 的八维/window/attribution（trigger 一致性）；或
  2. 对调用方 draft 传入的这些字段做**逐字段 exact-match**（防调用方伪造维度）。
- 采购：round-140 §六.3 指出 trigger 只覆盖八维，未覆盖 window/attribution——**应用层在 write_event 内
  对 window/attribution 也做 exact-match**（读 source snapshot 比对），不依赖 trigger。
- 若 source_snapshot 不存在 → 拒绝（ObservationValidationError 语义族）。

### 4.4 完整 replay 比较集

同 (source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version) 查回后比较**全部
不可变业务列**：
```
tenant_id, account_id, shop_id, shop_listing_id, shop_listing_sku_id, product_id, campaign_id,
asset_binding_id, source_snapshot_id, window_start, window_end, attribution_mode,
feedback_type, subject_type, subject_key, value, aggregation_version,
extra_explanation（NULL-safe exact equality：NULL 与 {…} 视为不同 → 冲突）
```
- **`extra_explanation` 用 NULL-safe exact equality**：`(g is None and w is None) or (g is not None and w is not None and g == w)`；
  否则 NULL 与对象互换被静默当作重放（round-140 §六.4 关闭）。
- `origin` 列表确定性排序 + JSON 形状冻结（§五.4）。
- 任一不同 → `FeedbackContentConflict`（本地领域异常，批次 3 评审 error-code 映射）。

### 4.5 并发 23505 双唯一键

并发同值时，两类命中都要处理：
- 唯一键一命中 → 比较自然键 + replay 集；
- 唯一键二命中但自然键（source/feedback_type/subject_type/subject_key/aggregation_version）不同 →
  **进入冲突分支**（`FeedbackContentConflict`），不按单一键返回旧行（round-140 §六.5 关闭）。
- 两键同义复用：同 idempotency_key 且自然键相同 → 返回既有 ledger_id（created=false）。

---

## 五、R140-5 闭合：SKU 稳定键与审计目标 D5 裁决

### 5.1 SKU subject key（D5 裁决建议）

现状：`shop_listing_skus` **无 public_id**；`platform_sku_id` 可空；15-数据字典的「SKU=public_id」与
已落 migration/catalog 历史差异。

**建议：D5 裁决 = 补 `public_id` 到 `shop_listing_skus`（走 migration 变更评审 + T9 catalog exact-set 同步）**
- 理由：sku_margin 需要稳定可审计 key；platform_sku_id 可空不可作身份。
- 迁移兼容：`ALTER TABLE app.shop_listing_skus ADD COLUMN public_id uuid NOT NULL DEFAULT gen_random_uuid()`；
  回填后加 `CREATE UNIQUE INDEX` on (tenant_id, public_id)；T3/T9 expected、mutation drill、ci.yml 同步。
- **备选**（若不补列）：正式勘误 subject_key 源为 `(tenant_id, shop_listing_id, sku_id)` 三元素 stable key，
  并给 `sku_margin` 的 subject_key 用该复合稳定串——给出迁移兼容规则（旧数据无 public_id，不影响现有
  无 sku_margin 事件的事实）。
- **本批 sku_margin 延期（§三.2）**，故 subject_key 裁决不阻塞 C1/C2 的其他四类实现；仍建议在批次 2
  实现前完成 D5（影响 subject_key 规范化黄金向量）。

### 5.2 审计目标（D5 裁决）

`roi_feedback_events` **无 public_id**；`audit_events.target_public_id` 是 UUID NOT NULL。

**建议：审计发生在 ledger 写入时（`write_event` 事务内），以 source snapshot 的归属实体 UUID 作 target**
- 目标实体 = **`ad_report_snapshots` 所属 `ad_campaigns.public_id`**（每类 event 的 source snapshot 都关联
  一个 campaign）；`target_type="ad_campaign"`。
- round-140 问“五类 event 的可用 UUID target”——统一用 source snapshot 关联的 campaign public_id（唯一、
  必填、与 event 八维一致）。
- `request_id`、`actor`（service/worker 可信 scope）、`tenant_public_id`：调用层传入，`write_audit_event`
  已有 worker_scope 双源校验。
- **ledger 与 audit 同一事务**（write_event 内 begin_nested + audit INSERT 同提交；审计失败 → 业务写入
  同事务回滚，失败事务零审计）。
- `action="p0_2.feedback_write"`，`before=<draft 前照>`，`after=<写入后 value/aggregation_version>`。

---

## 六、R140-6 闭合：M1/M2/M3 消费闭环与 durable receipt

### 6.1 消费通用框架

- PG ledger 与各消费端库跨事务 → 每条链定义：PG 查询条件、subject 映射、目标入口、目标持久化对象、
  幂等键、成功回执、skip/fail 返回、重试、审计。
- **durable receipt**：本次裁决采用 **fail-fast + 稳定结果键（重放二次写幂等）**，不引入跨库外链消费游标：
  - 消费端目标对象本身有幂等键（事件 idempotency_key 或其派生），重复消费 upsert / 忽略同键 → 结果确定；
  - 消费端局部事务写入成功即回执；写入失败整体回滚并抛错（不静默 skip）；
  - 全局重放 = 同一事件再跑（目标有幂等键，只需收敛到同结果）；
  - 超时查回：消费端先按 idempotency 键查目标对象，已存在 → 返回成功回执（不重复写）。

### 6.2 M1 消费（product_score / category_score）

| 项 | 冻结 |
|---|---|
| PG 查询 | `SELECT ... FROM roi_feedback_events WHERE feedback_type='product_score'`（event 为事实源） |
| subject 映射 | product_score: subject_key=products.public_id → 该 product 归并；category_score: subject_key=category_id → 类目归并 |
| 目标入口 | **直接 PG 消费**（方案 A）：C3 提供只读投影服务，M1 按 subject 归并；不新增文件载体（C-2 兼容投影保持可选，无回执可重放） |
| 目标持久化对象 | product 评分落 `products` 侧扩展列或独立评分表（**待裁决落点，round-140 §八 M1 持久化目标未定义**）；默认建议现有 `products` 评分消费链（未确认） |
| 幂等键 | 事件 idempotency_key = 消费侧副作用键；重复消费 upsert/忽略同键 |
| 成功回执 | 目标写入后返回 `{ok, consumed_event_id}` |
| skip/fail | 目标无 product → skip 记录；PG 读失败 → fail 传播（不静默） |
| 重试 | 幂等键查回，已消费 → 返回同 receipt |
| 审计 | ledger 写入审计（§五.2）；消费回写审计（若目标有独立审计） |

### 6.3 M2 消费（material_score）

| 项 | 冻结 |
|---|---|
| PG 查询 | `feedback_type='material_score'` |
| subject 映射 | subject_key=`assets.public_id`（UUID）→ **M2 `asset_id`（本地整数）映射**：C3 先 `SELECT id FROM assets WHERE public_id=:k`；未命中 → 近观 unmatched/skip |
| 目标入口 | `materials.integration.EvaluationFeedbackService.receive_evaluation(asset_id, evaluation, evidence, source_agent)` |
| numeric 分档 → 离散枚举 | **冻结分档（待裁决建议）**：`material_score`（观测 ROI）≥2.0 → `efficient`；1.0~2.0 → `potential`；<1.0 → `exploring`；`spend=0` 不产出（U3）。分档阈值 U5 未冻结标「未确认」 |
| 目标持久化对象 | `assets` 侧 evaluation 列（update_evaluation，幂等） |
| 幂等键 | receive_evaluation 幂等审计；重复调用同 asset+evidence → 幂等 |
| 成功回执 | `{ok, asset_id, evaluation}` |
| skip/fail | asset public_id 未映射 → skip（留证据）；receive 失败 → fail 传播 |
| 重试 | 按 asset_id 查回 evaluation，已为 target → 返回 receipt |
| 审计 | ledger 写入审计 + M2 receive 审计 |

### 6.4 M3 消费（sku_margin / shop_strategy — 本批延期）

- **本批 sku_margin/shop_strategy 延期（§三.2）**，故 M3 消费链路本批**不实现**。
- round-140 §八：`ingest_m5_record` 按 `platform_material_id + report_date` 摄取素材表现，不是 SKU/shop 消费器。
  待 M3 契约核对（P0-3.5）后设计 sku_margin/shop_strategy 的目标对象与落库入口（U6 未裁决标「未确认」）。
- 本批 M3 不做任何消费（事件 ledger 已含 sku_margin/shop_strategy 类型枚举，但不产行）。

### 6.5 审计目标补充

每类消费的成功回执/skip/fail 都应以 `source snapshot 关联 campaign.public_id` 为审计 target（§五.2 统一），
`action="p0_2.consumer.<m1|m2>"`，request_id 透传。

---

## 七、更新后的批次 2 DAG（含 migration 触发点）

```text
批次 2-A 版本选择纯函数（R140-1/2）
   输入：同 S 候选（含 platform_updated_at）；输出：VersionSelectorResult（selected/manual_required）+ DecisionBasis
   验收：四态（唯一最大/并列/混合空值/全空）+ 输入乱序黄金向量；不写 snapshot 表
   回滚：纯函数删除即可

批次 2-B 观测 ROI + 单快照贡献五层聚合（R140-2/3）
   输入：决策锚点快照 + products/shop_listing_skus/assets 归属（source 单快照派生）
   输出：product/category/material 三层 event draft（subject_key/value=观测 ROI scale6/aggregation_version）
   sku_margin/shop_strategy 延期（显式范围变更，不静默）
   验收：五行 exact-set（三实现 + 二延期）；粒度去重；Decimal 黄金向量（1/3→0.333333 等）
   回滚：纯计算删除即可

批次 2-C FeedbackRepository ledger（R140-4/5）
   输入：event draft；输出：ledger_id/created
   验收：fb:v1: 黄金向量；subject_key 规范化；repo 内部派生八维/window/attribution + 应用层 exact-match；
   NULL-safe extra_explanation equality；双唯一键并发；audit 同事务（target=campaign.public_id）
   回滚：新增文件删除即可

批次 2-D M1/M2 消费与 durable receipt（R140-6；M3 sku/shop 延期）
   输入：ledger 事件；输出：消费结果 + receipt
   验收：M1 直读 PG 归并（product/category）、M2 material_score 分档→receive_evaluation；
   fail-fast + 稳定结果键重放幂等；无回执可重放投影禁双写；审计
   回滚：新增文件删除即可

批次 2-E 批次 2 离线验收测试集
   验收：纯函数/真实 PG/并发/变异/回滚/失败清理全过；与 270 回归零破坏
   回滚：测试文件删除即可
```

**migration / T9 catalog 触发点（round-141 §九.7）**：
- **SKU public_id 补列（§五.1）**：若 D5 裁决选择补列，触发 `project/migrations/` 新 revision +
  `t3_expected.py` / 变异 drill / `ci.yml` T9 catalog exact-set 同步——**批 2 之前单独裁决，本批不执行**。
- 除此之外 **批次 2 不新增 migration**（单快照贡献模型复用冻结表；aggregation_version 用独立常量 manifest
  不新增 enum_policy_type）。

---

## 八、实现前待裁决清单（U1~U8 更新）

| # | 事项 | 状态 | 建议 |
|---|---|---|---|
| U1 | 最低样本阈值 | 建议 sample_count≥1 默认 | 版本化 policy 承载；类目 N / 商品阈值未裁决标「未确认」 |
| U2 | aggregation_version | **冻结 `aggr_v1` 独立常量 + manifest** | 不新增 enum_policy_type（避免 migration） |
| U3 | 零消耗策略 | 建议 spend=0 skip+质量事件；gmv=0 产出 0.00 事件 | 待裁决 |
| U4 | 消费方案 | 方案 A 直读 PG；M1/M2 本批实现 | M3 sku/shop 延期 |
| U5 | M2 分档阈值 | 建议 ≥2.0 efficient / 1.0~2.0 potential / <1.0 exploring | 未冻结标「未确认」 |
| U6 | M3 sku/shop 消费目标 | 延期（P0-3.5/M3 契约后） | 未确认 |
| U7 | category_id | opaque case-sensitive 稳定键（不声称受控词表） | 受控词表/约束变更待裁决 |
| U8 | 消费游标表/回执 | 用 fail-fast + 稳定结果键重放二次幂等（不新增 migration） | 若需“已消费”可见性再走 schema 评审 |

---

## 九、交接

请 Codex 复核本聚焦回修：R140-1（排序字段独立/四态/DecisionBasis/倒退）、R140-2（**单快照贡献模型**
+ 真值表 + 粒度去重）、R140-3（五类 exact-set + sku_margin/shop_strategy 显式延期 + Decimal 黄金规则 +
U1/U2/U3 建议）、R140-4（fb:v1: 黄金公式 + subject_key 规范化 + repo 内部派生 + NULL-safe replay +
双唯一键并发）、R140-5（SKU public_id D5 + audit target=campaign.public_id 同事务）、R140-6(M1/M2 真实入口 +
durable receipt 矩阵 + M3 延期）、更新 DAG 与 migration 触发点。契约 diff 通过后，再分别授权 C1/C2/C3
实体实现；批次 3 保持锁定。P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信
平台能力或全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-142-->