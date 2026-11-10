# round-145 DSH：P0-2 批次 2 契约闭合回修（round-144 §七 六项）

> 日期：2026-09-11。输入：`from-cdx/round-144-cdx-P0-2批次2四门契约裁决.md`（C1-a/C1-b-c/C2/C3 继续锁定 +
> SKU migration 修正）。状态：**四门继续锁定**；本轮闭合 round-144 §七 最小六项；批次 3 继续锁定。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 〇、独立复算证据（round-145 先固定数值）

### fb 三黄金键（独立脚本复算，与 round-144 §四.1 完全一致）

```text
GV-A canonical: 7|product_score|product|b7f6b8c0-1234-5678-9abc-def012345678|aggr_v1
    digest = b45e40ca322be2d7c29d22fb344e2f67644ebb450131f9bf8eee41ff052ef43f
    final  = fb:v1:b45e40ca322be2d7c29d22fb344e2f67644ebb450131f9bf8eee41ff052ef43f
GV-B canonical: 8|category_score|category|分类Á|aggr_v1          （Á = NFC(分类A\u0301)）
    digest = ab235c2771ec14e2ab75a5ba123b8cbc37c941819126fc2d74131743208f4dd4
    final  = fb:v1:ab235c2771ec14e2ab75a5ba123b8cbc37c941819126fc2d74131743208f4dd4
GV-C canonical repr: '9|material_score|material|a\\|b\\\\c|aggr_v1'
    digest = d0284d2061bbbc0eea8db93ddce30463e9410b687057f31b8bc5edeed32d175c
    final  = fb:v1:d0284d2061bbbc0eea8db93ddce30463e9410b687057f31b8bc5edeed32d175c
```

### aggr_v1 manifest（本文件即单一真源；canonical payload 与 SHA-256 已计算）

canonical payload（`sort_keys=True, ensure_ascii=False, separators=(",", ":")` 序列化）与
`SHA-256 = aeaa6cc2fe77a32b601c85700195ef047ca1dcc9ff01e9ddbd9f61258fdc62d1`
（见 §三.4；实现时以同一序列化规则复算并登记）。

---

## 一、C1-a 闭合：selector 五向量（合法可解析）+ 三域枚举 + arrival 入口

### 1.1 三域 disjoint exact-set（round-144 §二.4 冻结）

```text
selection_rule  = {unique_max_time}            # selector 的唯一成功结果
manual_reason   = {max_time_tie, all_times_null}  # selector 的 manual 结果
evidence_reason = {time_regression}             # classify_arrival 的质量证据
```
- 三个集合不相交：selector 输出要么 `selection_rule=unique_max_time`（selected），要么
  `manual_reason∈{max_time_tie, all_times_null}`（manual_required）——不存在 selected 携带 manual reason
  的无效状态。
- 混合 NULL 且非空最大并列 → `manual_reason=max_time_tie`（mixed 状态由
  `null_time_candidates` 列表本身表达，不新增枚举值）。

### 1.2 入口拆分（round-144 §二.2）

```text
select_final(conn, statistical_identity S) -> SelectionResult
  - 输入：同 S 的候选快照集合（无序，含 platform_updated_at）
  - 输出：selected(snapshot_id, evidence) | manual_required(reason, evidence)

classify_arrival(new_snapshot, prior_selected) -> ArrivalClass
  - 输入：新到快照 + 既有决策锚点
  - 输出：normal | time_regression(detail)      # 独立入口，不混入 selector
```
- selector 只处理候选最终选择；时间倒退由 classify_arrival 判定并产出 `evidence_reason=time_regression`。

### 1.3 五个黄金向量（固定值、完整输入输出对象）

**GV1（唯一最大 → selected）**
```json
INPUT  candidates=[{id:101,t:2026-09-01T00:00:00Z},{id:102,t:2026-09-02T00:00:00Z},
                   {id:103,t:2026-09-03T00:00:00Z}]
OUTPUT {"kind":"selected","snapshot_id":103,
        "evidence":{"version_selector":{"sorted_snapshot_ids":[101,102,103],
                     "selected_id":103,"selection_rule":"unique_max_time",
                     "null_time_candidates":[]},
          "regressions":[],"aggregation_version":"aggr_v1","policy_version":null}}
```

**GV2（最大并列 → manual）**
```json
INPUT  candidates=[{id:101,t:2026-09-01T00:00:00Z},{id:102,t:2026-09-02T00:00:00Z},
                   {id:103,t:2026-09-02T00:00:00Z}]
OUTPUT {"kind":"manual_required","reason":"max_time_tie",
        "evidence":{"version_selector":{"sorted_snapshot_ids":[101,102,103],
                     "selected_id":null,"selection_rule":"max_time_tie",
                     "null_time_candidates":[]},
          "regressions":[],"aggregation_version":"aggr_v1","policy_version":null}}
```
（并列组内按 snapshot_id 升序展示，不参与胜者判定。）

**GV3（混合 NULL + 唯一最大 → selected）**
```json
INPUT  candidates=[{id:101,t:2026-09-01T00:00:00Z},{id:102,t:null},{id:103,t:2026-09-02T00:00:00Z}]
OUTPUT {"kind":"selected","snapshot_id":103,
        "evidence":{"version_selector":{"sorted_snapshot_ids":[101,103,102],
                     "selected_id":103,"selection_rule":"unique_max_time",
                     "null_time_candidates":[102]},
          "regressions":[],"aggregation_version":"aggr_v1","policy_version":null}}
```

**GV4（全 NULL → manual）**
```json
INPUT  candidates=[{id:101,t:null},{id:102,t:null},{id:103,t:null}]
OUTPUT {"kind":"manual_required","reason":"all_times_null",
        "evidence":{"version_selector":{"sorted_snapshot_ids":[101,102,103],
                     "selected_id":null,"selection_rule":"all_times_null",
                     "null_time_candidates":[101,102,103]},
          "regressions":[],"aggregation_version":"aggr_v1","policy_version":null}}
```

**GV5（arrival 时间倒退 → evidence）**——修正 round-143 非法日期 `09-00T00:00Z`：
```json
INPUT  new_snapshot={id:99,t:2026-08-31T00:00:00Z}, prior_selected={id:101,t:2026-09-01T00:00:00Z}
OUTPUT {"kind":"time_regression","detail":"platform_updated_at 2026-08-31T00:00:00Z < 既有最大
         2026-09-01T00:00:00Z","evidence_reason":"time_regression"}
```

### 1.4 DecisionBasis JSON 合法性与 key exact-set

- key exact-set：`version_selector`（`sorted_snapshot_ids`/`selected_id`/`selection_rule`/
  `null_time_candidates`）、`regressions`（`snapshot_id`/`reason`/`detail`）、`aggregation_version`、
  `policy_version`（可空）。
- 五向量 JSON 均合法可解析（修复 round-143 示例缺逗号；本文件 §1.3 已全部给出完整对象）。
- 全部列表按 snapshot_id 升序稳定排序（展示次序不影响判定）。

---

## 二、C1-b/c 闭合：五类范围恢复 + canonical granularity + 完整作用域

### 2.1 五类范围裁决（round-144 §三.1：恢复五类，round-130 冻结）

**决策：恢复五类为 P0-2 输出**（round-130 冻结语义优先）；round-143 的“三类 + 两类延期”范围变化
**撤回**，不作为范围变更登记。五类 event 本批均产：

| feedback_type | value 语义（冻结公式） | subject_key | canonical granularity |
|---|---|---|---|
| product_score | observed ROI = Σgmv/Σspend（scale6） | `products.public_id`（小写 UUID） | campaign |
| category_score | observed ROI = Σgmv/Σspend（scale6） | `products.category_id`（NFC/case-sensitive 原样） | campaign |
| material_score | observed ROI = Σgmv/Σspend（scale6） | `assets.public_id`（小写 UUID） | campaign_asset |
| sku_margin | **value = gmv − spend（分 int → numeric）** | SKU 稳定键（§六 D5） | shop_listing_sku |
| shop_strategy | observed ROI = Σgmv/Σspend（scale6） | `shops.public_id`（小写 UUID） | campaign（经 shop 归并） |

- sku_margin 用 `gmv − spend`（毛利近似 = 收入−投放消耗，快照字段直接可得）；收入/成本/退款/补贴的
  精细化公式（含 cost_snapshots 联表）标「未确认」待 P0-3.5——**不影响本批产行**。
- shop_strategy 的消费动作（M3 策略调整）标「未确认」待 P0-3.5；本批产事件。

### 2.2 canonical granularity + fallback/suppression（round-144 §三.2）

- **每类单一 canonical granularity**（§2.1 表）：product/category=**campaign**，material=campaign_asset，
  sku_margin=shop_listing_sku，shop_strategy=campaign。
- **fallback 规则（同一业务流量多粒度快照并存时防重复）**：
  - product/category 聚合**只消费 granularity='campaign' 的快照**；若 campaign 缺失，可用
    'shop_listing' 快照补位（fallback），但同一业务流量在 campaign 与 shop_listing 都有快照时**只计
    campaign 一次**（suppression）。
  - SKU 级快照只服务 sku_margin，不参与 product/category/shop 聚合。
  - 反例（验收必含）：同一流量同时存在 campaign/shop_listing/shop_listing_sku 三粒度快照时，
    product/category 只按 campaign 计一次；sku_margin 只用 SKU 级。
- 唯一键一（source_snapshot_id,...）消除同一快照的重复 event；§2.3 作用域 + canonical granularity
  消除跨粒度重复。

### 2.3 聚合 SQL 完整作用域（round-144 §三.3）

```sql
SELECT s.tenant_id, s.feedback_type, s.subject_type, s.subject_key,
       s.window_start, s.window_end, s.attribution_mode, s.aggregation_version,
       sum(sn.gmv)::numeric / nullif(sum(sn.spend), 0) AS observed_roi_scale6
FROM roi_feedback_events s
JOIN ad_report_snapshots sn ON sn.id = s.source_snapshot_id
WHERE s.feedback_type = :t
  AND sn.granularity = :canonical_granularity          -- §2.2 canonical/fallback
GROUP BY s.tenant_id, s.feedback_type, s.subject_type, s.subject_key,
         s.window_start, s.window_end, s.attribution_mode, s.aggregation_version
```
- 限定/分组维度（round-144 §三.3 冻结）：`tenant_id, feedback_type, subject_type, subject_key,
  window_start, window_end, attribution_mode, aggregation_version`——跨 tenant/window/attribution/version
  不会混算。
- version selector 已先把每个 S 收敛为单一有效 source snapshot（§一）；加权结果只能
  `sum(snapshot.gmv)/sum(snapshot.spend)`，禁平均 event.value。

---

## 三、数值与 manifest 单一真源（round-144 §三.4）

### 3.1 Decimal（接受 prec60/ROUND_HALF_UP/scale6）

- `decimal.localcontext(prec=60, rounding=ROUND_HALF_UP)` 计算，`quantize(scale=6, ROUND_HALF_UP)` 落库。
- 四向量：`1/3→0.333333`、`10/3→3.333333`、`150/100→1.500000`、`0/100→0.000000`。
- gmv=0 文案统一 `0.000000`（0.00 笔误关闭）。

### 3.2 sample_count 与类目商品数（round-144 §三.4）

- `sample_count = count(distinct source_snapshot_id)`（subject 下参与聚合的事件快照数）——消费查询计算。
- 类目最低商品数：**本批冻结 `category_min_products = 1`**（manifest 中显式给出实现值，
  §3.4 payload）；“阈值影响消费”门**本批启用为 sample_count≥1 且商品数≥1**——不再写“未知 N”。
  若未来调高，走 aggr_v2 manifest 升级（§3.4 升级规则）。

### 3.3 zero_spend / insufficient_inputs exact-set（round-144 §三.4）

```
TypedOutcome = roi(value: Decimal)
             | zero_spend_skipped(snapshot_id, reason="denominator_spend_zero")
             | insufficient_inputs(snapshot_id, missing_fields: [...])
```
- `zero_spend_skipped`：spend=0（触发条件：spend==0）；后续动作=本批不持久化，C3/批次 3 决定
  数据质量事件/manual task。
- `insufficient_inputs`：触发条件 exact-set——`source_snapshot_id 无对应行`、`subject 归属无法解析`
  （§四.3 同源校验失败）、`numerator/denominator 字段为 NULL`（normalize 后仍缺）。
  字段：`missing_fields`（列出缺失字段名）；后续动作=rejected（不产 event）。
- 两类都是 typed outcome，非异常非 rejected 语义混淆。

### 3.4 aggr_v1 manifest 单一真源（round-144 §三.4，本文件即冻结 payload）

canonical payload（`sort_keys=True, ensure_ascii=False, separators=(",", ":")`）：
```json
{"category_min_products":1,"decimal":{"precision":60,"rounding":"ROUND_HALF_UP","storage_scale":6},
 "feedback_types":{"category_score":{"denominator":"spend","granularity":["campaign"],"numerator":"gmv"},
   "material_score":{"denominator":"spend","granularity":["campaign_asset"],"numerator":"gmv"},
   "product_score":{"denominator":"spend","granularity":["campaign"],"numerator":"gmv"},
   "shop_strategy":{"denominator":"spend","granularity":["campaign"],"numerator":"gmv"},
   "sku_margin":{"denominator":"1","granularity":["shop_listing_sku"],"numerator":"gmv_minus_spend"}},
 "min_sample_snapshot":1,"version":"aggr_v1"}
SHA-256 = aeaa6cc2fe77a32b601c85700195ef047ca1dcc9ff01e9ddbd9f61258fdc62d1
```
- 实现：`backend/domain/report/aggregation_manifest.py` 以同一序列化规则输出上述 payload，内容哈希
  恒为上述值；`roi_feedback_events.aggregation_version='aggr_v1'` 与 manifest.version 一致。
- 升级规则：只增不改——新增 `aggr_v2` 条目（新 payload + 新哈希），旧事件保持原 aggregation_version
  不迁移；消费查询按 aggregation_version 分流。

---

## 四、C2 闭合：固定 digest + 异常分层 + NFC 一致 + 依赖闭合

### 4.1 fb 三黄金键（采用 round-144 §四.1，独立复算一致）

见 §〇；实现时以 `_canonical_join`/`_hash_key("fb", fields)` 复算并断言等于上述固定 digest。

### 4.2 异常分层（round-144 §四.2）

```text
FeedbackValidationError   # 新 draft 输入非法（subject 与 source 不符、字段缺失、类型错误）——写前拒绝
FeedbackContentConflict   # 数据库已有同一身份、但 replay 内容不同（现有行冲突）——保留旧行
```
- 分别测试：新写入非法 → FeedbackValidationError（零落盘）；既有行内容冲突 → FeedbackContentConflict。

### 4.3 category NFC 一致（round-144 §四.3）

- subject_key 生成与同源校验使用**同一 NFC 函数**：`subject_key = NFC(category_id)`（case-sensitive、
  无 trim）；同源校验对 source product 的 `category_id` 先做 NFC 再与传入 subject_key 比较，并以 NFC
  结果落键——数据库可能存分解字符，不直接与原始值相等。
- GV-B 已用 NFC 合并验证（`分类A\u0301` → `分类Á`）。

### 4.4 C2 依赖闭合（round-144 §四.4）

- 五类范围已恢复（§二.1）→ C2 generic repository 支持五类；SKU D5（§六）闭合后 subject_key 完整。
- 待 C1 范围 + SKU D5 结束后授权 C2（本轮完成契约，授权由 CDX 按门裁决）。

---

## 五、C3 闭合：M1/M2/M3 真实入口与 receipt

### 5.1 M1（round-144 §五.1）

- **本批交付命名：projection（只读投影 API）**，不计作 M1 消费闭环（round-144 §五.1 允许）。
  - 入口：`backend/domain/report/projection.py` 提供 `subject_roi_projection(conn, feedback_type,
    subject_type, subject_key, window_start, window_end, attribution_mode, aggregation_version)` →
    返回 §二.3 SQL 结果（只读，无副作用）。
  - 稳定结果键 = 查询参数元组 `(feedback_type, subject_type, subject_key, window_start, window_end,
    attribution_mode, aggregation_version)`（重跑同参数同结果，纯函数）。
  - **不计 M1 决策闭环**：选品评分落 products 侧的目标对象/落库入口仍标「未确认」待裁决
    （若 M1 需持久化评分，走 schema 评审加 products 评分列/独立评分表——本批不落）。

### 5.2 M2（round-144 §五.2 修正）

- **跨库映射修正**：app.assets 的 `content_sha256` 唯一性为 `UNIQUE (tenant_id, content_sha256)
  WHERE deleted_at IS NULL`——查询必须带 `tenant_id` 且 `deleted_at IS NULL`。
- **M2 现状**：`asset_items` 只有 `md5 varchar(32)`，无 content_sha256；`asset_evaluations.evidence_json`
  是普通 Text、无事件键唯一约束；receive_evaluation 每次都新增审计行。
- **可执行方案（二选一，本契约默认选项 2）**：
  1. M2 migration：为 `asset_items` 增 `content_sha256` + `asset_evaluations` 增事件 idempotency_key
     唯一约束（M2 是独立本地库，不触 P0-1 migration；走 M2 受控 schema 扩展评审）；
  2. **默认：跨库稳定标识 = `md5`（M2 已有唯一列）**——C3 侧先从 app.assets 派生
     `md5 = sha256(content_bytes)[:32]`？**不可行（无内容字节）**——故默认回退选项 1，
     M2 migration 增加 `content_sha256`（= app.assets.content_sha256）与
     `asset_evaluations.event_idempotency_key` 唯一约束，作为 M2 受控扩展。
- durable receipt：`(asset_id, evaluation, event_idempotency_key)` 唯一 → 重复消费查回同 receipt
  （不新增台账行）；`{ok:false}` 由 adapter 明确分类 skip（asset 未映射/同值已存在）或 fail（DB 错误）。

### 5.3 M2 分档边界（round-144 §五.3，U5 冻结）

| material_score（观测 ROI scale6） | evaluation |
|---|---|
| < 0 或 NaN（防御，输入非法） | `invalid_input`（skip，不调 receive） |
| 0.000000 ≤ x < 1.000000 | exploring |
| 1.000000 ≤ x < 2.000000 | potential |
| x ≥ 2.000000 | efficient |
- 边界点精确结果：`0 → exploring`、`0.999999 → exploring`、`1.000000 → potential`、
  `1.999999 → potential`、`2.000000 → efficient`（round-144 §五.3 边界冻结）。

### 5.4 M3（round-144 §五.4）

- 五类恢复（§二.1）后：sku_margin/shop_strategy 事件本批**产出**；其 M3 消费（SKU 毛利/店铺策略落库、
  决策入口）仍标「未确认」待 P0-3.5/M3 契约核对——与“五类输出恢复”不冲突（输出本批产，消费适配
  待 M3 契约）。

---

## 六、SKU migration 修正（round-144 §六，仅追加）

**方案 A（修正为仅追加）**：

```text
1. 新 head revision（追加，不重写历史）：
   ALTER TABLE app.shop_listing_skus ADD COLUMN public_id uuid NOT NULL DEFAULT gen_random_uuid();
   CREATE UNIQUE INDEX uq_shop_listing_skus_public_id ON app.shop_listing_skus (public_id);
   -- 或 UNIQUE (tenant_id, public_id)？见下方唯一性裁决
2. 历史 migration（31tbl000001）与 gen_t3_migration.py 生成结果保持原哈希，不重写基线；
   干净升级（空库→head）只执行新 head revision 的 ADD COLUMN，不重复 DDL。
3. 同步：更新 head catalog expected（t3_expected.py / assert_t3_schema / T9 exact-set）；
   T3/T9 mutation drill 增补 public_id 相关负例。
4. 回滚：新 revision downgrade = DROP INDEX + DROP COLUMN；与 generator 逆序。
5. 旧行回填：DEFAULT gen_random_uuid() 就地回填，无空值。
```

**public_id 唯一性裁决（round-144 §六.2）**：
- 与其他 public_id（tenants/products/assets/shops…）一致采用**单列 `UNIQUE (public_id)`**（全局 UUID
  身份）；subject_key = public_id（省略 tenant 前缀）；跨租户 UUID 冲突概率可忽略且符合全局外部稳定身份
  语义；审计解析按 public_id 全局查回。
- 若未来需要租户内可见性独立约束，可加 `(tenant_id, public_id)` 索引（非唯一约束），不改变 subject_key
  语义。

---

## 七、验收 DAG 更新（实现授权后，四门分别授权）

```text
C1-a  VersionSelector + classify_arrival（§一）
      验收：GV1~GV5 固定向量 + 三域枚举 + arrival；乱序输入确定性；DecisionBasis 可解析
C1-b/c 观测 ROI + 五类聚合（§二/§三）
      验收：五类 formula exact-set；canonical granularity fallback/suppression 反例；完整作用域 SQL；
           Decimal 四向量；sample/category_min_products=1；TypedOutcome；aggr_v1 payload/hash
C2  FeedbackRepository ledger（§四）
      验收：fb 三黄金键固定 digest；ValidationError/ContentConflict 分层；NFC 一致；audit 同事务；
           replay 含 idempotency 复算；双唯一键并发
C3  M1 projection + M2 消费（§五）
      验收：M1 只读投影稳定结果键；M2 content_sha256 映射 + receipt 唯一键；分档五边界；skip/fail 分类
```

migration 触发点：SKU public_id（§六）在 C2/C3 实现前单独裁决执行（仅追加 head revision）；
aggr_v1 manifest 为常量文件，不触发 migration。

---

## 八、待裁决清单更新（U1~U8 终版）

| # | 事项 | 状态 |
|---|---|---|
| U1 | sample_count≥1 + category_min_products=1 | **冻结（§3.2/manifest）** |
| U2 | aggregation_version=aggr_v1 manifest | **冻结（§3.4）** |
| U3 | zero_spend_skipped TypedOutcome | **冻结（§3.3）** |
| U4 | M1=projection 只读；M2=content_sha256 跨库映射 | **冻结（§5.1/5.2）** |
| U5 | M2 分档五边界 | **冻结（§5.3）** |
| U6 | M3 sku/shop 消费适配 | 未确认（P0-3.5/M3 契约） |
| U7 | category_id 受控词表 | 未确认（opaque NFC/case-sensitive 原样，§4.3） |
| U8 | M1 选品评分落库目标 | 未确认（projection 本批；落库走 schema 评审） |

---

## 九、交接

请 Codex 复核本闭合回修六项：C1-a（合法可解析五向量 + 三域枚举 + classify_arrival 入口 + GV5 修正）、
C1-b/c（五类恢复 + canonical granularity/fallback/suppression + 完整作用域 SQL + manifest/sample/
TypedOutcome 固定值）、C2（fb 三固定 digest + ValidationError/ContentConflict 分层 + NFC 一致 + 依赖闭合）、
C3（M1 projection 命名 + M2 content_sha256 migration 方案 + 分档五边界 + M3 消费待契约）、SKU 仅追加
migration（head revision + 单列 UNIQUE(public_id)）。闭合后按 C1-a/C1-b-c/C2/C3 四门分别授权实现；
批次 3 保持锁定。P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或
全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-146-->