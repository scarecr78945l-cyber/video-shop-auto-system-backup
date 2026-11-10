# round-139 DSH：P0-2 批次 2 契约收敛（仅分析，不实现）

> 日期：2026-09-09。输入：`from-cdx/round-138-cdx-P0-2批次1冻结确认与批次2契约启动.md`（批次 1 COMPLETE，
> 批次 2 契约收敛授权）+ round-130/131/132 已冻结语义（两快照真值表、五层矩阵、REPORT_MANUAL 全链、
> 四批 DAG）+ idempotency.md（键 9 fb:）+ t3_expected.py 实表 schema。
> 状态：**批次 1 COMPLETE**；本轮仅产出批次 2 冻结候选契约，**不进入实体代码**；批次 3 继续锁定。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 〇、批次 2 范围与证据锚点

批次 2 = 计算与回写层（round-130 §七 C1/C2/C3）：版本选择 + 观测 ROI + 五层聚合（C1）、
FeedbackRepository 幂等 ledger（C2）、M1/M2/M3 消费与回执（C3）。**不含** REPORT_MANUAL 人工任务/工作流
编排（批次 3）、manual_tasks 实体、workflow handler、error-code registry 新增、migration。

schema 锚点（t3_expected.py + 实表探针）：

```text
roi_feedback_events:
  id/tenant_id/account_id/shop_id/shop_listing_id/shop_listing_sku_id(product_id/campaign_id/asset_binding_id)
  source_snapshot_id int8 NOT NULL, window_start/end timestamptz NOT NULL, attribution_mode varchar(64) NOT NULL,
  feedback_type enum_feedback_type NOT NULL, subject_type enum_feedback_subject NOT NULL,
  subject_key varchar(128) NOT NULL, value numeric NOT NULL, extra_explanation jsonb NULL（F132-1 勘误）,
  aggregation_version varchar(64) NOT NULL, idempotency_key varchar(128) NOT NULL, created_at now()
  唯一键一 (source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version)
  唯一键二 (tenant_id, idempotency_key)
  trigger trg_feedback_dimension_consistency（ZT006：source_snapshot 与维度一致）
enum_feedback_type   = product_score / category_score / material_score / sku_margin / shop_strategy
enum_feedback_subject = product / category / material / shop / sku
enum_snapshot_granularity = campaign / shop_listing / shop_listing_sku / campaign_asset
ad_report_snapshots.report_version_key（id:/ts:/hash: 三源，captured_at 永不入键）
```

---

## 一、版本选择（C1-a）

### 1.1 候选集合与排序规则（F132-2 gate 冻结）

同一统计身份 S（campaign/granularity/SKU/asset/window/attribution 相同）存在多个 version key 的行时：

| 场景 | 判定 | 动作 |
|---|---|---|
| `platform_updated_at` 非空且唯一最大值 | 选择证据充分 | 决策锚点快照 = 该最大时间对应行 |
| 最大时间并列且 version key 不同 | 选择证据不足 | 不按 version key/id/hash/captured_at 猜序 → 人工任务（report_manual，批次 3 触发） |
| 所有候选 `platform_updated_at` 为空 | 选择证据不足 | 同上 → 人工任务（批次 3 触发） |

- **opaque token 不排序**：`id:<token>` 与 `hash:<digest>` 无时间/大小顺序（F132-2）；
  只有 `ts:` 源（规范化 platform_updated_at）参与排序。
- `captured_at` 仅表示本系统看到证据的时间，**不参与版本顺序**（展示采集顺序用，不用于决策）。

### 1.2 同窗口修订与时间倒退

- 同窗口修订（S 同、V 不同）：按 1.1 选最终有效版本，旧版本行保留（append-only 历史）。
- 时间倒退（新 V 的 platform_updated_at 小于既有最大值）：若 V 全新 → 仍 append 且
  `extra_explanation` 记录倒退事件（输入 snapshot id/hash 序列 + 选择规则）；数据质量事件走冻结错误码
  策略（U3 未冻结前标「未确认」，不引入新字符串）。
- 重复版本键重放：返回既有 id，不构成第二次快照（两快照必须两个不同 V）。

### 1.3 决策锚点快照（DecisionBasis）

- 单 `source_snapshot_id` 指向最终有效版本行 id。
- `extra_explanation`（jsonb）固定记录：全部输入 snapshot id/hash 序列、选择规则（排序依据、
  并列/空时间标记）、aggregation_version、policy_version_id（若有）。

---

## 二、五层聚合（C1-b）

### 2.1 聚合输入与层级

观测事实来自 `ad_report_snapshots`（决策锚点快照，见 §一），按 subject_type 五层聚合：

| subject_type | subject_key 来源 | 聚合输入（snapshot 维度） | 层级 |
|---|---|---|---|
| product | `products.public_id`（规范化小写） | campaign/SKU 粒度 → 归属 listing → product | 商品级 |
| category | **`products.category_id`（稳定 id，round-132 gate 1：非类目名）** | product 级再按 category_id 归并 | 类目级 |
| material | `assets.public_id`（经 asset_binding_id） | campaign_asset 粒度 → asset_binding → asset | 素材级 |
| sku | `shop_listing_skus.public_id` | shop_listing_sku 粒度直接 | SKU 级 |
| shop | `shops.public_id` | shop 粒度/多 listing 归并 | 店铺级 |

> **未确认/待裁决**：category_id 的稳定来源（products.category_id 当前是否有稳定受控词表）——round-132
> gate 1 要求定义稳定 category_id 来源；若缺失，product 级先产出、category 级标记「未确认」不静默用类目名。

### 2.2 窗口边界与数值口径

- `window_start/window_end`：平台统计窗口（round-131 已冻结：与抓取时间无关，不得用两次抓取合成）。
- 金额一律分（int8），聚合求和；`value numeric` 为观测 ROI（gmv/spend，Decimal 全精度，禁止 legacy float）。
- 零消耗：spend=0 → 不产出 ROI 事件（skip + 数据质量事件按策略，U3 未冻结标「未确认」）；
  gmv=0,spend>0 → ROI=0 事件可产出（策略决定，U3 未冻结标「未确认」）。
- 缺失值：字段缺失/非法 → snapshot 解析层已按默认值补齐（批次 1 已冻结）；聚合层只消费已入库快照，
  不再补造。

---

## 三、观测 ROI 与 CID 职责边界（C1-c）

### 3.1 观测 ROI 公式

```
observed_roi = gmv / spend        （Decimal 全精度，numeric 列存储）
```

- 字段来源：`ad_report_snapshots.gmv` / `.spend`（决策锚点快照）。
- 分母为零：spend=0 → **不计算**（见 §二.2 零消耗策略）。
- 负差分：gmv/spend 均非负（批次 1 校验），观测 ROI 恒 ≥ 0；不存在负差分输入。
- 平台返回 ROI 与重算值不一致：**以重算值为准**（观测 = 窗口事实 gmv/spend），平台值不直接入 value；
  差异记入 `extra_explanation`（数据质量事件按策略，U3 未冻结标「未确认」）。
- 异常串：**不引入「ROI 异常」等新字符串**；异常场景只走冻结错误码 + 策略动作（R130-4 冻结）。

### 3.2 CID 职责边界

- CID（backend/domain/cid.py）是目标 ROI/出价/止损**决策引擎**，可消费观测 ROI，但**不参与观测 ROI 生成**
  （R130-4 冻结）。观测 ROI 的公式/精度与 CID 引擎完全解耦。
- `aggregation_version` 定位到稳定算法/阈值版本：类目达最小商品数与样本量后才生效
  （U2 未冻结标「未确认」）；**不从 legacy 的 5 继承**（R130-4 冻结）。

---

## 四、FeedbackRepository 幂等 ledger（C2）

### 4.1 唯一 public 写入口

`FeedbackRepository.write_event(draft) -> FeedbackWriteResult(ledger_id, created)`：
- 入口携带聚合后的不可变 draft（含 source_snapshot_id、feedback_type、subject_type、subject_key、
  value、aggregation_version、extra_explanation），受信边界重验（镜像批次 1 write_observation 模式）。
- **身份键**：`fb:<source_snapshot_id>:<feedback_type>:<subject_type>:<subject_key规范化>:<aggregation_version>`
  （idempotency.md 键 9 冻结，canonical_join 顺序一致）。
- **append-only / 幂等冲突**：
  - 新事件 → INSERT（唯一键一/二），created=true；
  - 同源同键重放 → 返回既有 ledger_id，created=false（23505 精确查回比较）；
  - 同源同键但内容不同（value/extra_explanation 差异）→ 确定性 `FeedbackContentConflict`（本地领域异常，
    不入 error-code registry，批次 3 评审映射），旧行保持原值；
  - 并发同值 → 恰一 created=true，同 id。
- **不执行 UPDATE/DELETE**；审计写入走既有 ActorResolver+audit（批次 3 接 workflow 前，批次 2 先用
  service/worker actor 上下文写审计）。
- `trg_feedback_dimension_consistency`（ZT006）在 DB 层保证 source_snapshot 与维度一致——冲突由应用校验
  + trigger 共同闭合。

### 4.2 replay 比较集

同 (source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version) 查回后比较：
`value`、`extra_explanation`（若双方均非空）、维度字段（tenant/account/shop/listing/product/campaign/
asset，经 trigger 已一致，仍做防御比较）；排除 id/created_at。

### 4.3 origin_snapshot_ids 与 policy_version

- `extra_explanation.origin_snapshot_ids`：决策锚点快照 id + 参与聚合的全部 snapshot id/hash 序列。
- `extra_explanation.policy_version`：聚合算法/阈值版本引用（U2 未冻结标「未确认」）。
- `extra_explanation.selection_rule`：§一 1.1 选择规则快照（含并列/空时间标记）。

---

## 五、M1/M2/M3 消费与回执（C3）

### 5.1 方案 A（默认）：直接 PG 消费

- M1：`products` 评分消费（product_score/category_score）——从 `roi_feedback_events` 直接读，
  按 subject_type/subject_key 归并；幂等 = 事件 idempotency_key 复用。
- M2：`material_score` → `EvaluationFeedbackService.receive_evaluation()` 适配器
  （round-132 gate 2：receive_evaluation 接收离散 evaluation 枚举，不直接接 numeric material_score——
  需在批次 2 设计 numeric→离散枚举的投影规则，**未确认待裁决**）。
- M3：`sku_margin`/`shop_strategy` → `optimization/ab/ingest.py` 适配器
  （round-132 gate 2：当前按 platform_material_id 摄取，不是 SKU/shop 消费器——需设计 subject_key 映射，
  **未确认待裁决**）。

### 5.2 回执与事务边界（round-132 gate 3）

- 当前 `roi_feedback_events` **无消费状态/回执列**；“事件标记消费”在冻结表上没有落点。
- 方案 A 需要可执行持久化位置 + 事务边界。**默认技术建议**：
  1. **消费游标表（新增 `p0_2_consumption_cursor`，待裁决——需 schema 变更评审，D5 gate 触发）**，
     或
  2. **无回执只读投影 + 幂等重放**：M1/M2/M3 每次全量/增量按 subject_key 幂等重算，事件表本身为
     事实源，消费端不做“已消费”标记（可重放、无回执）。
- **禁止双写无回执**（round-131 冻结）：任何路径不得既写事件表又写文件却不记录消费状态。
- **默认建议**：选项 2（无回执只读投影）——不新增 migration、可重放、事件表保持纯 ledger；
  若 M1/M2/M3 需要“已消费”可见性，再走 schema 变更评审加游标表（批 3 前裁决）。

### 5.3 每类 exact-set 投影

| 消费端 | 事件类型 | 投影（subject_key → 消费对象） |
|---|---|---|
| M1 选品 | product_score | products.public_id → product 评分 |
| M1 选品 | category_score | products.category_id → category 评分 |
| M2 素材 | material_score | assets.public_id → evaluation（离散枚举投影，待裁决） |
| M3 优化 | sku_margin | shop_listing_skus.public_id → SKU 毛利 |
| M3 优化 | shop_strategy | shops.public_id → 店铺策略 |

---

## 六、REPORT_MANUAL 下游接口（批次 3 只读契约，批次 2 不实现）

批次 2 仅记录批次 3 需要的输入输出契约（**不实现** manual_tasks/工作流编排）：

- 触发条件（输入）：解析失败（批次 1 rejected 信号）、PAGE_CHANGED、版本选择证据不足（§一 1.1）、
  版本缺口、数据质量事件（U3 策略，未冻结标「未确认」）。
- 任务创建（批次 3）：`manual_tasks(task_type=report_manual, ref_type=workflow_step,
  ref_id=<step bigint id>, status=pending, reason=<冻结错误码>, before_state=<step 当前状态>)`；
  部分唯一 `px_tasks_open` 精确复用既有 open 任务。
- 审计锚：`audit_events.target_public_id` 用 **workflow step/run 的 public_id（uuid）**
  （manual_tasks 无 public_id，round-131 R130-5 冻结）；actor 权限（ActorResolver）批次 3 接。
- resume/fencing 依赖（批次 3）：行锁 + `WHERE id=? AND status='manual_review' AND attempt=?` +
  action idempotency key 不变 + claim 后 attempt 递增；与 cancel/pause/recover 竞态确定。
- 批次 2 交付物不包含 manual_tasks 写入、workflow handler、audit 的 manual 相关动作。

---

## 七、批次 2 验收 DAG（实现授权后）

```text
批次 2-A 版本选择纯函数（C1-a）
   输入：快照候选集（S 同多 V）；输出：决策锚点 snapshot_id + extra_explanation 选择规则
   验收：唯一最大时间/并列/全空三态；opaque 不排序；倒退记录；黄金向量
   回滚：纯函数删除即可

批次 2-B 观测 ROI + 五层聚合（C1-b/c）
   输入：决策锚点快照 + products/shop_listing_skus/assets/shops 归属
   输出：五层聚合事件 draft（subject_key/value/aggregation_version）
   验收：五层映射 exact-set；spend=0/gmv=0 策略；Decimal 全精度；负差分不存在；CID 不解耦验证
   回滚：纯计算删除即可

批次 2-C FeedbackRepository ledger（C2）
   输入：事件 draft；输出：ledger_id/created
   验收：append-only/幂等重放/内容冲突/并发单行/ZT006 合规/审计；五类 subject 正例 + 错配负例
   回滚：新增文件删除即可

批次 2-D M1/M2/M3 消费与回执（C3）
   输入：ledger 事件；输出：投影 + 消费幂等
   验收：方案 A 直读 PG；每类 exact-set 投影；无回执可重放；禁双写；适配器映射（待裁决项 U5/U6）
   回滚：新增文件删除即可

批次 2-E 批次 2 离线验收测试集
   输入：A~D 交付物
   验收：纯函数/真实 PG/并发/变异/回滚/失败清理全过；与 270 回归零破坏
   回滚：测试文件删除即可
```

依赖：A → B → C → D → E；每批内建测试；批次 2 完成后接批次 3（REPORT_MANUAL 全链 + workflow 编排）。

---

## 八、批次 2 实现前待裁决项（明确列出，未确认处不用 legacy 默认）

| # | 事项 | 状态 | 默认技术建议（待 Codex/用户裁决） |
|---|---|---|---|
| U1 | 最低样本阈值（五层各层） | 未确认 | 版本化 policy 定义（policy_versions），不在代码硬编码 |
| U2 | aggregation_version 算法/阈值版本来源 | 未确认 | policy_versions 承载 |
| U3 | 零消耗/数据质量事件策略 | 未确认 | spend=0 skip+质量事件；gmv=0 产出 ROI=0（可调） |
| U4 | 消费方案 A（直读 PG）vs B（C-2 投影） | 默认 A | A 直读；回执用无回执可重放投影（不新增 migration） |
| U5 | M2 material_score → 离散 evaluation 投影规则 | 未确认 | 阈值分档（numeric→枚举）待裁决 |
| U6 | M3 sku_margin/shop_strategy → platform_material_id 映射 | 未确认 | 需设计 subject_key → 消费器映射 |
| U7 | category_id 稳定来源 | 未确认 | products.category_id 受控词表；缺失则 category 级延期 |
| U8 | 消费游标表（如需“已消费”可见性） | 未确认 | 触发 schema 变更评审（D5 gate），批 3 前裁决 |

---

## 九、交接

请 Codex 复核本批次 2 冻结候选：版本选择三态、五层聚合映射（含 category_id 待裁决）、观测 ROI/CID
边界、FeedbackRepository ledger 身份键与幂等冲突、M1/M2/M3 直读 PG 消费与无回执可重放、REPORT_MANUAL
批次 3 只读契约、验收 DAG 与待裁决项 U1~U8。契约 diff 通过后，再授权批次 2 实体实现（C1/C2/C3）；
批次 3 继续锁定。P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁通过，不表示真实微信平台能力
或全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-140-->