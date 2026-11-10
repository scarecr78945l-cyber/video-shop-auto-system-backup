# round-147 DSH：P0-2 批次 2 向量与消费闭合回修（R146-1~R146-3）

> 日期：2026-09-12。输入：`from-cdx/round-146-cdx-P0-2批次2四门复核.md`（R146-1~R146-3 三组最小差异）。
> 状态：**C1-a、C1-b/c、C2、C3 实体实现继续锁定**；本轮仅闭合三组契约；批次 3 继续锁定。
> 通过项不再重复：aggr_v1 hash `aeaa6cc2...`、fb 三 digest（b45e40ca/ab235c27/d0284d20）、五类恢复、
> Validation/ContentConflict 分层方向、category NFC、SKU 追加方案、C2 核心回修。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 〇、本文件不执行 DDL/实体——仅重新冻结三类契约，供下一轮四门复核。

---

## 一、R146-1 闭合：真实 JSON 五向量 + 状态字段与排序一致

### 1.1 排序规则统一（round-146 §二.3 冻结其一）

- **时间展示列表** `sorted_snapshot_ids` 按 `(platform_updated_at ASC NULLS LAST, snapshot_id ASC)` 排序。
- **NULL/回退证据列表** `null_time_candidates` / `regressions` 按 `snapshot_id ASC`。
- 展示排序**不参与胜者判定**（胜者只看非空 platform_updated_at 唯一最大）。

### 1.2 状态字段三域 exact-set（修正 GV2/GV4 违法值）

```text
selection_rule = {unique_max_time, null}      # selected 输出 unique_max_time；manual 输出 null
manual_reason  = {max_time_tie, all_times_null}
evidence_reason= {time_regression}            # classify_arrival 专有
```
- **manual 输出的 `version_selector.selection_rule` 一律为 `null`**，manual reason 单独在
  `version_selector.manual_reason` 表达——不在 selection_rule 域内放 max_time_tie/all_times_null。
- DecisionBasis key exact-set 同步为：
  `version_selector`（`sorted_snapshot_ids`/`selected_id`/`selection_rule`/`manual_reason`(可空)/
  `null_time_candidates`）、`regressions`、`aggregation_version`、`policy_version`(可空)。

### 1.3 五个真实 JSON 向量（可直接 `json.loads`，无伪语法）

**GV1（唯一最大 → selected）**
```json
{"input": {"candidates": [
    {"snapshot_id": 101, "platform_updated_at": "2026-09-01T00:00:00Z"},
    {"snapshot_id": 102, "platform_updated_at": "2026-09-02T00:00:00Z"},
    {"snapshot_id": 103, "platform_updated_at": "2026-09-03T00:00:00Z"}]},
 "output": {"kind": "selected", "snapshot_id": 103,
    "evidence": {"version_selector": {
        "sorted_snapshot_ids": [101, 102, 103], "selected_id": 103,
        "selection_rule": "unique_max_time", "manual_reason": null,
        "null_time_candidates": []},
      "regressions": [], "aggregation_version": "aggr_v1", "policy_version": null}}}
```

**GV2（最大并列 → manual，selection_rule=null）**
```json
{"input": {"candidates": [
    {"snapshot_id": 101, "platform_updated_at": "2026-09-01T00:00:00Z"},
    {"snapshot_id": 102, "platform_updated_at": "2026-09-02T00:00:00Z"},
    {"snapshot_id": 103, "platform_updated_at": "2026-09-02T00:00:00Z"}]},
 "output": {"kind": "manual_required", "snapshot_id": null,
    "evidence": {"version_selector": {
        "sorted_snapshot_ids": [101, 102, 103], "selected_id": null,
        "selection_rule": null, "manual_reason": "max_time_tie",
        "null_time_candidates": []},
      "regressions": [], "aggregation_version": "aggr_v1", "policy_version": null}}}
```

**GV3（混合 NULL + 唯一最大 → selected；时间列表 NULL LAST，null 列表按 id）**
```json
{"input": {"candidates": [
    {"snapshot_id": 101, "platform_updated_at": "2026-09-01T00:00:00Z"},
    {"snapshot_id": 102, "platform_updated_at": null},
    {"snapshot_id": 103, "platform_updated_at": "2026-09-02T00:00:00Z"}]},
 "output": {"kind": "selected", "snapshot_id": 103,
    "evidence": {"version_selector": {
        "sorted_snapshot_ids": [101, 103, 102],
        "selected_id": 103, "selection_rule": "unique_max_time", "manual_reason": null,
        "null_time_candidates": [102]},
      "regressions": [], "aggregation_version": "aggr_v1", "policy_version": null}}}
```
（说明：`sorted_snapshot_ids=[101,103,102]` 按 time ASC NULLS LAST（102 NULL 排在最后）、id ASC；
`null_time_candidates=[102]` 按 id ASC。展示排序不参与胜者判定。）

**GV4（全 NULL → manual，selection_rule=null，null 列表按 id）**
```json
{"input": {"candidates": [
    {"snapshot_id": 101, "platform_updated_at": null},
    {"snapshot_id": 102, "platform_updated_at": null},
    {"snapshot_id": 103, "platform_updated_at": null}]},
 "output": {"kind": "manual_required", "snapshot_id": null,
    "evidence": {"version_selector": {
        "sorted_snapshot_ids": [101, 102, 103], "selected_id": null,
        "selection_rule": null, "manual_reason": "all_times_null",
        "null_time_candidates": [101, 102, 103]},
      "regressions": [], "aggregation_version": "aggr_v1", "policy_version": null}}}
```

**GV5（classify_arrival 时间倒退 → evidence_reason=time_regression）**
```json
{"input": {"new_snapshot": {"snapshot_id": 99, "platform_updated_at": "2026-08-31T00:00:00Z"},
           "prior_selected": {"snapshot_id": 101, "platform_updated_at": "2026-09-01T00:00:00Z"}},
 "output": {"kind": "time_regression",
    "detail": "platform_updated_at 2026-08-31T00:00:00Z is earlier than prior maximum 2026-09-01T00:00:00Z",
    "evidence_reason": "time_regression",
    "evidence": {"version_selector": {"sorted_snapshot_ids": [99, 101], "selected_id": 101,
                  "selection_rule": "unique_max_time", "manual_reason": null, "null_time_candidates": []},
      "regressions": [{"snapshot_id": 99, "reason": "time_regression",
                       "detail": "platform_updated_at 2026-08-31T00:00:00Z < 既有最大 2026-09-01T00:00:00Z"}],
      "aggregation_version": "aggr_v1", "policy_version": null}}}
```
（GV5 时间倒退为独立入口 classify_arrival；selector 只接收候选最终选择。）

### 1.4 验证要求

- 逐个 `json.loads` 成功；断言 GV1/GV3 的 `selection_rule=unique_max_time`（selected），
  GV2/GV4 的 `selection_rule=null` + `manual_reason∈{max_time_tie, all_times_null}`；
  GV5 的 `evidence_reason=time_regression`。
- 输入 candidates 置换顺序 → 输出 JSON 不变（展示列表按 §1.1 排序）。

---

## 二、R146-2 闭合：canonical-only + 有效 source 过滤 + 五类公式/typed outcome 与 manifest 同源

### 2.1 取消 fallback（round-146 §3.1 最小修正）

- **本版删除 fallback**：只消费 manifest 声明的 canonical granularity——product/category=campaign、
  material=campaign_asset、sku_margin=shop_listing_sku、shop_strategy=campaign。
- 无 cross-granularity 补位；同一业务流量若只以非 canonical 粒度存在 → 不产该 event（NO canonical source），
  记 insufficient（见 §2.4）。
- manifest 与 SQL 保持一致（不再有 SQL 缺 fallback 的冲突）。

### 2.2 有效 source 过滤（round-146 §3.1 负例）

- 聚合 JOINT 只消费**有效 source 集合**（version selector 已收敛的决策锚点快照）。append-only 历史事件
  不被错误纳入：
  ```sql
  WITH valid_sources AS (
    SELECT DISTINCT source_snapshot_id
    FROM roi_feedback_events
    WHERE tenant_id = :tenant AND feedback_type = :ft AND aggregation_version = 'aggr_v1'
  )
  SELECT s.tenant_id, s.feedback_type, s.subject_type, s.subject_key,
         s.window_start, s.window_end, s.attribution_mode, s.aggregation_version,
         sum(sn.gmv)::numeric / nullif(sum(sn.spend), 0) AS roi_scale6
  FROM roi_feedback_events s
  JOIN ad_report_snapshots sn ON sn.id = s.source_snapshot_id
  JOIN valid_sources v ON v.source_snapshot_id = s.source_snapshot_id   -- 仅有效 source
  WHERE s.feedback_type = :ft AND sn.granularity = :canonical_granularity
  GROUP BY s.tenant_id, s.feedback_type, s.subject_type, s.subject_key,
           s.window_start, s.window_end, s.attribution_mode, s.aggregation_version;
  ```
- 负例：旧版 source 已选中但旧版 ledger 仍存在 → 聚合只 JOIN 有效 source 集合，不含已废弃版本事件。

### 2.3 五类公式/单位/零消耗分支（按 feedback_type 联合类型，round-146 §3.2）

| feedback_type | numerator | denominator | value 单位 | 零消耗分支 | 跨 source 聚合 |
|---|---|---|---|---|---|
| product_score | Σgmv | Σspend | ROI≥0（scale6），spend=0→zero_spend_skipped | ROI 通用分支 | Σgmv/Σspend |
| category_score | Σgmv | Σspend | ROI（同上） | 同上 | Σgmv/Σspend |
| material_score | Σgmv | Σspend | ROI（同上） | 同上 | Σgmv/Σspend |
| **sku_margin** | **Σ(gmv − spend)** | **（无分母）** | **差额（分 int→numeric，可为负=亏损）** | **spend=0 不 skip**（gmv−0=gmv）；gmv<empty> | **Σ(gmv)−Σ(spend)** |
| shop_strategy | Σgmv | Σspend | ROI（同上） | 同上 | Σgmv/Σspend |

- **sku_margin 是投放后收入差额代理指标**（=gmv−spend，分），**不是含商品成本的毛利**（round-146 §3.2）：
  单位分；与最终 SKU 毛利（含 cost_snapshot 成本）差异标「未确认」待 P0-3.5。SKU 行**不被 ROI 的
  零分母分支误杀**——按 feedback_type 走各自公式，通用 ROI SQL 不适用于 SKU。
- 边界样例（round-146 §3.2 冻结）：
  - sku gmv=100, spend=0 → 代理差额=100 分（产出，非 zero_spend_skipped）；
  - sku gmv=50, spend=100 → 差额=−50 分（正常亏损结果）；
  - ROI gmv=100, spend=0 → zero_spend_skipped。

### 2.4 insufficient vs ValidationError 分层（round-146 §3.3）

- **写入非法 draft → `FeedbackValidationError`**（subject 与 source 不符、类型错误等）——固定写前异常。
- **纯计算缺字段 → typed result（非异常）**，`insufficient_inputs` reason exact-set：
  - `no_canonical_source`（该 subject 无 canonical granularity 有效 source）；
  - `subject_unresolvable`（subject_key 无法从 source 归属解析）；
  - `missing_numerator_or_denominator`（仅当外部/受损对象——正常 PG 行 gmv/spend NOT NULL 不触发，
    round-146 提示不要宣称正常 PG 行可空）。
  - `missing_fields` 列出缺失字段名；**转交行为**：本版返回 typed 结果供 C3 记录，批次 3 决定
    数据质量事件/manual task。
- 不把 subject 同源校验失败同时放 insufficient 与 ValidationError（round-146 §3.3 关闭）：
  **由校验方固定**——draft 写入路径的 subject 同源校验失败 → ValidationError；纯聚合找不到 subject 归属
  → insufficient（不同入口、不同结局）。

### 2.5 manifest 与公式同源（round-146 §3.1 单一真源）

- aggr_v1 manifest（round-145 §3.4 payload，hash `aeaa6cc2...`）为**唯一真源**；五类公式/粒度/单位
  以 manifest 为准；本轮不再改 manifest 内容（除非 fallback 删除需 manifest 表示——本版 canonical-only，
  manifest 已隐含单一粒度，无需改动即与 SQL 一致）。
- manifest 只列 canonical granularity；`sha256` 移到 manifest JSON fence 之外的单行标注
  （round-146 §一 格式提示）。

---

## 三、R146-3 闭合：M1/M3 消费范围 + tenant projection + M2 唯一事件回执/真实映射/失败矩阵

### 3.1 完成范围（round-146 §五.1：恢复原范围或待批变更）

- round-130/131 冻结 M1/M2/M3 消费及回执。**本轮提交明确范围变更裁决**（待 Codex/用户批准）：
  - **本批交付 = projection 只读 API（M1 消费查询）+ M2 消费适配器（material_score）**；
  - **M1 选品评分落库**（影响 products 决策）与 **M3 sku/shop 消费** 显式延至 P0-3.5/M3 契约核对——
    **不登记 U4 为全部冻结**，待批范围变更；批准前保持原完成定义。
- 若范围变更未获批准，C3 完成定义保持 M1/M2/M3 原范围，本批只交 projection 不算 M1 消费闭环。

### 3.2 projection 作用域（round-146 §五.2）

- 签名增加 **tenant 输入**：`subject_roi_projection(conn, *, tenant_id, feedback_type, subject_type,
  subject_key, window_start, window_end, attribution_mode, aggregation_version)`。
- SQL WHERE 加 `tenant_id = :tenant`（不仅分组防混算，且**只返回调用者租户**）。
- **结果身份含 tenant**：结果键 = `(tenant_id, feedback_type, subject_type, subject_key, window_start,
  window_end, attribution_mode, aggregation_version, valid_source_set)`。
  - 纯 `(feedback_type,...)` 查询参数不是不可变结果键（新事实到达后结果变化）；稳定结果身份须含
    `valid_source_set`（有效 source 集合哈希，§二.2）。

### 3.3 M2 唯一事件回执与映射（round-146 §五.3/五.4）

- **唯一事件身份 UNIQUE（单一，二选一）**：只保留 `event_idempotency_key` 唯一（接收源命名空间/tenant +
  event key），不再叠加 `(asset_id, evaluation, event_key)` 三元组唯一（该三元组允许同事件改 evaluation
  再写一行，round-146 §五.3 关闭）。
  - M2 migration：`asset_evaluations` 增 `event_idempotency_key varchar NOT NULL` +
    `UNIQUE (event_idempotency_key)`；asset_id/evaluation/evidence 作为 replay 内容比较；不同内容冲突，
    旧 receipt 保持。
- **跨库映射（round-146 §五.4）**：M2 增 `content_sha256`（= app.assets.content_sha256，取自内容字节
  SHA-256）——取值来源 = app 资产内容哈希（不截断冒充 md5，round-146 提示已撤回该路线）；旧资产回填/
  缺映射标「未确认」；唯一性与租户隔离：`UNIQUE (content_sha256)` + 显式租户条件（app 侧已
  tenant+active 唯一，映射时带 tenant 校验）。
- **失败矩阵（冻结）**：
  | 情形 | 结论 |
  |---|---|
  | 同 event_idempotency_key 已存在 | replay：返回已存 receipt（同 event 已消费证明） |
  | app.assets 无对应 content_sha256（有效 tenant 内） | skip（无映射，留证据） |
  | event_key 不同内容（同 key 不同 asset/evaluation） | conflict（FeedbackContentConflict 语义，旧 receipt 保持） |
  | DB 错误/崩溃（写前/写后） | fail：transactional receipt + 重试查回（幂等） |
  - 跨库写前/写后崩溃重试验收：本地事务提交为回执真源，重试查 `event_idempotency_key` 返回同 receipt。

---

## 四、SKU 追加方案（沿用，不再重复讨论）

round-146 §四确认单列 `UNIQUE(public_id)`、仅追加 head revision、默认 UUID 回填、逆序 downgrade、
head expected 与 T9/drill 同步通过；history 保持原哈希。实现启动时单独核验空库→head、旧 head→新 head、
降级/再升级、旧行非空/唯一、跨租户解析仍带 tenant 校验。全局 UUID 非租户可见性凭证。

---

## 五、验收 DAG 与下一裁决

- 本轮不进入实体；四门（C1-a、C1-b/c、C2、C3）实现与批次 3 继续锁定。
- 下一轮 CDX 按四门分别复核 R146-1/2/3 闭合；闭合后分别授权实现。
- P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 六、交接

请 Codex 复核本闭合：R146-1（真实 JSON 五向量 + manual selection_rule=null + 排序规则一致）、
R146-2（canonical-only 删除 fallback + 有效 source 过滤负例 + 五类公式/单位/typed outcome 与 manifest 同源
+ Validation/insufficient 分层）、R146-3（完成范围变更裁决 + tenant projection + M2 单一事件回执 UNIQUE +
SHA256 真实映射 + 失败矩阵）。通过后按四门分别授权；批次 3 保持锁定。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-148-->