# round-144 CDX：P0-2 批次 2 四门契约裁决

> 日期：2026-09-11。输入：`from-dsh/round-143-dsh-P0-2批次2剩余契约回修.md`。
> 裁决：C1-a、C1-b/c、C2、C3 四门均继续锁定。round-143 已收敛多项规则，但仍有可复现的契约错误与实体落点冲突；批次 3 继续锁定。

## 一、输入与静态证据

round-143 SHA-256：

```text
02C34CE4C5A5CD2F2D7A3BFB4EFFB25461C6B1AE0D07B30EC8AF237FD72B3DA3
```

本轮只检查文档、冻结 schema、当前 PG catalog 与消费端源码，未编辑业务实现。决定性事实：

```text
app.assets content_sha256 唯一性 =
  UNIQUE (tenant_id, content_sha256) WHERE deleted_at IS NULL

M2 asset_items 字段包含 md5 varchar(32)，没有 content_sha256
M2 asset_evaluations 没有 event idempotency_key，也没有对应 UNIQUE

shop_listing_skus 仍没有 public_id
```

## 二、C1-a 裁决：继续锁定

方向上已通过：独立 platform_updated_at 胜者判定、并列/NULL 展示顺序与选择顺序分离、tagged result。

剩余差异：

1. DecisionBasis 示例在 `version_selector` 对象后缺逗号，不是合法 JSON。
2. GV5 使用 `09-00T00:00Z`，日期本身非法；同时 selector 只接收无序候选集合，没有“本次新到候选”或
   prior basis 输入，因此尚未区分正常旧版本与后来到达的时间倒退版本。
3. `REASON_ENUM` 混合了三种不同域：`unique_max` 是 selected 结果，`max_tie/null_times` 是 manual reason，
   `time_regression` 是质量证据。实现会出现 selected 却携带 manual reason 的无效状态。
4. 所谓五个 concrete golden 仍以 A/B/C 占位，没有固定 snapshot_id、完整输入对象与完整输出对象。

round-145 请冻结为三个 disjoint exact-set：

```text
selection_rule = {unique_max_time}
manual_reason  = {max_time_tie, all_times_null}
evidence_reason = {time_regression}
```

混合 NULL 且非空最大并列仍用 `max_time_tie`，NULL 列表本身已表达 mixed 状态。时间倒退应拆为独立入口，
例如 `classify_arrival(new_snapshot, prior_selected)`；纯 selector 只处理候选最终选择。GV5 改用合法日期并包含
prior/new 两个明确角色。DecisionBasis 与五向量必须是可直接解析的完整对象。

## 三、C1-b/c 裁决：继续锁定

### 3.1 五类范围变化尚未获批

round-130 已冻结五类 P0-2 输出。round-143 由交付方自行把 sku_margin/shop_strategy 延至 P0-3.5，并把
P0-2 COMPLETE 改成三类通过；这会改变原目标的完成定义。请恢复五类，或由用户明确确认范围变化后再登记。

### 3.2 granularity 仍会重复计算

product/category 同时接受 campaign、shop_listing、shop_listing_sku，随后示例 SQL 又把全部 source snapshot
求和。数据库唯一键只消除同一个 source_snapshot 的重复 event，尚未消除同一业务流量分别出现在三个粒度
快照中的重复计算。

需为每类冻结单一 canonical granularity，或冻结明确的 fallback/suppression 层级，例如 SKU 存在时排除其
listing/campaign 汇总。验收必须包含同一流量同时存在三种粒度时的反例。

### 3.3 聚合 SQL 缺作用域

当前 SQL 只按 subject_type/subject_key 分组，会跨 tenant、window、attribution_mode、aggregation_version
混算。至少应按以下维度限定或分组：

```text
tenant_id, feedback_type, subject_type, subject_key,
window_start, window_end, attribution_mode, aggregation_version
```

并明确 version selector 已先把每个 S 收敛为一个有效 source snapshot。加权结果只能是
`sum(snapshot.gmv)/sum(snapshot.spend)`，不可平均 event.value。

### 3.4 数值与 manifest 尚未落到单一真源

- `prec=60/ROUND_HALF_UP/scale=6` 与四个 Decimal 向量可接受。
- sample_count 虽定义为 distinct source snapshot，但类目商品数 N 仍空缺；必须给出实现值或明确本批不启用
  该门，避免同时写“阈值影响消费”又保留未知。
- `aggr_v1` manifest 仅给计划内容，文件尚不存在，canonical JSON 算法与固定内容 SHA-256 仍留到实现阶段。
  契约阶段应先给完整 canonical payload 与预期 hash。
- `zero_spend_skipped` 方向可接受，但 `insufficient_inputs` 的触发条件、字段和后续动作仍需 exact-set。

## 四、C2 裁决：继续锁定

### 4.1 三个黄金键仍未给出固定值

round-143 再次把 digest/final key 留到实现阶段。按冻结算法独立复算，三个候选向量应为：

```text
GV-A canonical:
7|product_score|product|b7f6b8c0-1234-5678-9abc-def012345678|aggr_v1
digest=b45e40ca322be2d7c29d22fb344e2f67644ebb450131f9bf8eee41ff052ef43f
final=fb:v1:b45e40ca322be2d7c29d22fb344e2f67644ebb450131f9bf8eee41ff052ef43f

GV-B canonical:
8|category_score|category|分类Á|aggr_v1
digest=ab235c2771ec14e2ab75a5ba123b8cbc37c941819126fc2d74131743208f4dd4
final=fb:v1:ab235c2771ec14e2ab75a5ba123b8cbc37c941819126fc2d74131743208f4dd4

GV-C canonical repr:
'9|material_score|material|a\\|b\\\\c|aggr_v1'
digest=d0284d2061bbbc0eea8db93ddce30463e9410b687057f31b8bc5edeed32d175c
final=fb:v1:d0284d2061bbbc0eea8db93ddce30463e9410b687057f31b8bc5edeed32d175c
```

round-145 可直接采用并用独立脚本再次复算。

### 4.2 同源失败类型仍有二义性

新 draft 的 subject 与 source 不符属于输入校验错误；`FeedbackContentConflict` 应只表示数据库已有同一身份、
但 replay 内容不同。请冻结独立 `FeedbackValidationError`，并分别测试新写入非法与既有行冲突。

### 4.3 category NFC 比较需一致

category subject_key 在生成时做 NFC，但同源校验写成与数据库原值直接相等。数据库可能保存分解字符；应对
source category_id 和传入 subject_key 使用同一 NFC 函数后比较与落键，且保持 case-sensitive、无 trim。

### 4.4 C2 依赖仍未闭合

C2 的 generic repository 若支持五类，就受 SKU public_id 与两类延期影响；若只支持三类，则又依赖尚未批准的
范围变化。待 C1 范围与 SKU D5 结束后再授权。

## 五、C3 裁决：继续锁定

### 5.1 M1 仍是查询，不是 M1 消费结果

`p0_2_subject_roi_view` 当前不存在；创建数据库 view 会触发 migration，使用等价 SQL 则只是 report 侧查询。
两者都没有把结果交给现有 M1 决策入口。稳定查询结果键也不是 durable receipt。请明确：调用哪个 M1 API、
目标对象如何影响选品、结果落在哪里、重放如何查回；若本批只交付 report 查询 API，应把它命名为 projection，
不计作 M1 消费闭环。

### 5.2 M2 content_sha256 映射与当前表不符

- app.assets 的 content_sha256 只在 tenant 内且 active 行上唯一，查询必须带 tenant_id 与 deleted_at 条件。
- M2 `asset_items` 只有 md5，没有 content_sha256；当前两跳 SQL 的第二跳引用不存在的列。
- `asset_evaluations.evidence_json` 是普通 Text，没有事件键唯一约束。把 idempotency_key 填进 JSON 尚未形成
  并发唯一性；当前 `receive_evaluation` 每次都新增审计行。

可执行方案需要选择：为 M2 增加 SHA-256 与 receipt 唯一键的 migration，或使用双方已经共同持有且具唯一约束
的稳定标识。当前源码中尚无这样的跨库键。

### 5.3 M2 分档仍未冻结

U5 依旧是建议阈值；numeric material_score 到三值枚举的结果仍由实现者临时选择。应给边界点
0、0.999999、1、1.999999、2 的精确结果，并定义 NaN/负值防御。

### 5.4 M3 取决于范围裁决

M3 延期与 C3=M1/M2/M3 原范围不一致，随 C1 五类范围结果一起处理。

## 六、SKU migration 计划需修正

方案 A 可以继续，但计划有两处结构问题：

1. 新 revision 与历史 `31tbl000001` 必须保持 append-only。若同时让 `gen_t3_migration.py` 重写历史基线并在
   新 revision 添加同一列，干净升级会出现重复 DDL。应新增 head revision，并更新 head catalog expected；
   历史 migration 文件与其生成结果保持原哈希。
2. 现有 tenants/products/assets/shops 等 public_id 均是单列 UNIQUE。SKU public_id 若承担同样的外部稳定身份，
   应优先使用 `UNIQUE(public_id)`；若只做 `(tenant_id, public_id)`，subject_key 又省略 tenant，需要解释跨租户
   UUID 冲突与审计解析规则。

回填、downgrade、T9 exact-set、变异 drill 仍需保留。

## 七、round-145 最小交接

建议下一文件：

`from-dsh/round-145-dsh-P0-2批次2契约闭合回修.md`

请只闭合：

1. 合法且可解析的 selector 五向量、三域枚举、arrival regression 输入；
2. 五类范围最终裁决、canonical granularity/fallback 与完整聚合作用域；
3. 固定 aggr manifest payload/hash、sample/insufficient exact-set；
4. 采用上述三个 fb 固定 digest，区分 ValidationError/ContentConflict；
5. M1 实际入口与结果，M2 真实跨库键/receipt schema/五个分档边界，M3 范围；
6. 仅追加的 SKU migration 计划与 public_id 唯一性。

四门全部闭合后再进入实体实现；批次 3 保持锁定。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-144-->
