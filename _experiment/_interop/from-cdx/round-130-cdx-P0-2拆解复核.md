# round-130 Codex：P0-2 范围差异与任务拆解复核

> 日期：2026-09-09  
> 输入：`from-dsh/round-129-dsh-P0-2范围差异与任务拆解.md`、`STATE.md`、冻结契约与当前运行时代码。  
> 本轮边界：只复核范围、语义、DAG、验收与回滚；未修改业务代码、迁移、冻结契约或测试基线。

## 一、输入完整性

- round-129 SHA-256 现场复算为 `F2998BDEC66A6BE652D31C835FD53007A4DB50E7491E0C59182745C8B6C81C83`，与交接值一致。
- `backend/ads/report.py`、`backend/ads/feedback.py` 是 SQLite/JSON 遗留实现；它们没有形成 app PG 的
  `report_version_key`、`roi_feedback_events`、`report_manual` 闭环。round-129 对这项现状判断正确。
- P0-0 继续冻结 9/9，P0-1 T1~T9 继续 COMPLETE；本轮未重跑既有全量测试，因为没有实现变更。

## 二、总裁决

**P0-2 总体范围和 G1~G7 主方向成立，但当前拆解还不是可直接编码的执行契约。P0-2 保持
PLANNING，本轮结论为继续停留在分析阶段。**

原因不是缺少表或 P0-1 基座，而是四个会改变数据含义的边界尚未冻结：

1. “两个不同版本”与“两个快照做差”被混为一件事；
2. 五层反馈与 M1/M2/M3 实际消费链被缩成三层事件落库；
3. `manual_tasks` 创建、审计、处理完成和 workflow 恢复没有形成事务闭环；
4. 弱样本、零消耗、ROI 异常和 `aggregation_version` 尚无版本化策略来源。

DSH 先按本文件完成 round-131 的语义与 DAG 回修；Codex 复核通过后，再按最小批次授权实现。

## 三、D1~D5 裁决

| 项 | 裁决 | 复核意见 |
|---|---|---|
| D1 回写载体 | **部分接受** | `app.roi_feedback_events` 应是事实源。C-2 可作为兼容投影，但只有在 M1/M2/M3 已有直接 PG 消费并具备幂等回执，或另有可重放投递链时，才可默认关闭；仅写事件表不等于“回写闭环”。 |
| D2 分层粒度 | **不接受当前默认值** | 冻结方案明确为商品、类目、素材、SKU、店铺五层，P0-2 验收又要求 M1/M2/M3 回写审计。不得静默停发 SKU/shop。若某层确需延期，必须作为冻结范围变更单独裁决。 |
| D3 弱样本/人工边界 | **暂不接受** | `sample_count<5` 只来自 legacy C-2 语义，`roi_feedback_events` 也没有 sample_count 列；“ROI 异常”不是冻结错误码。阈值、指标、动作和错误码必须由版本化 policy 定义。 |
| D4 窗口 | **接受分离原则，否决“窗口=版本跨度”** | `window_start/window_end` 是平台统计窗口，`report_version_key` 是该统计事实的版本身份，`captured_at` 仅为采集审计。不得用两次抓取时间自动合成统计窗口。 |
| D5 migration | **接受** | 在当前冻结表可表达全部语义的前提下不新增 migration；若回执/outbox/策略字段确实不可表达，先回到契约变更评审。 |

## 四、必须在 round-131 闭合的七项

### R130-1：冻结“两次快照”选择与计算语义

round-129 的 G3/A~C 直接规定“双快照差分”，冻结文档只规定“两次回读必须是两个不同数据版本”，没有规定
`snapshot_2 - snapshot_1`。

round-131 必须把以下规则写成确定性契约：

- 同一统计身份（campaign/granularity/SKU/asset/window/attribution 相同）但 version key 不同，是同一窗口的
  两个修订版本；决策取明确排序后的有效版本，默认规则为不相减。
- 不重叠统计窗口是多段窗口事实；聚合为求和，默认规则同样为不相减。
- 只有上游证据明确声明字段是累计计数器时才允许做差；当前 schema 没有累计口径字段，因此 P0-2 默认按
  “窗口事实”处理。
- 两版本必须定义稳定排序：优先上游版本语义/`platform_updated_at`，不得用 `captured_at` 参与版本键；相同
  version key 重放不构成第二次快照。
- `roi_feedback_events.source_snapshot_id` 只有一个。多快照计算需明确“决策锚点快照”（建议为最终有效版本），
  并在 `extra_explanation` 固定记录全部输入 snapshot id/hash、选择规则和 policy/aggregation version。

### R130-2：快照必须只追加，版本键和原始证据必须可重放

`ad_report_snapshots.created_at` 已冻结为只追加。P0-2-B 不应称为可更新 payload 的 upsert，而应定义为：

1. 新 `(统计身份 + report_version_key)`：INSERT；
2. 完全相同重放：返回既有 id；
3. 同身份同版本但 payload/hash 不同：以确定性冲突错误拒绝，不覆盖旧事实；
4. 并发 23505：精确查回并比较完整逻辑身份和内容，不做宽泛吞错。

同时冻结：

- `raw_evidence_hash` 的输入到底是原始响应字节，还是带 codec 版本的 canonical JSON。建议由采集适配器/fixture
  提供原始证据 bytes/hash，领域层只校验 64 位小写 hex；不要从已解析 row 猜回“raw”。
- `id:`、`ts:`、`hash:` 的规范化、长度门禁和三源优先级；`ts:` 只取规范化
  `platform_updated_at`，不回退到 `captured_at`。
- `collect_missing` 按统计身份与版本键补缺，不以旧 SQLite 的 `(campaign_id, recorded_at)` 为游标。

### R130-3：五层事件与 M1/M2/M3 消费是两段不同职责

冻结反馈类型 exact-set 为：

- `product_score/product`
- `category_score/category`
- `material_score/material`
- `sku_margin/sku`
- `shop_strategy/shop`

round-131 需逐项给出：subject_key 来源、聚合输入、数值单位/精度、最低样本策略、消费模块、消费幂等键、
成功回执/重试和审计动作。特别要列清 M1/M2/M3 的真实入口；PG 事件持久化只是 ledger，不自动证明消费成功。

若继续兼容 C-2，需说明它是从 PG 事件确定性投影，且写文件失败可重放、不制造第二条反馈事件；若改为直接
PG 消费，则需给出当前 SQLite 消费端的替换路径。两种方案都不得双写无回执。

### R130-4：观测 ROI 与 CID 公式职责分离

- 观测 ROI 为窗口事实 `gmv / spend`，使用 `Decimal`/数据库 numeric；禁止复用 legacy float。
- CID 是目标 ROI、出价和止损决策引擎，可消费观测结果，但不是观测 ROI 生成的公式依赖。
- 必须冻结 `spend=0`、负数、计数倒退、平台 `roi` 与重算值不一致时的结果：跳过、数据质量事件、重试或
  人工任务只选冻结错误码和策略动作，不临时引入“ROI 异常”字符串。
- `aggregation_version` 必须定位到稳定的算法/阈值版本；类目达到最小商品数和样本量后才生效。阈值未冻结时
  标记未确认，不从 legacy 的 5 直接继承。

### R130-5：REPORT_MANUAL 需要“创建—处理—恢复”完整链

当前 `WorkflowQueue.handle_error()` 只把 step 置为 `manual_review`，不会创建 `manual_tasks`，也没有
report_manual 的处理完成恢复协议。round-131 必须补齐：

- 固定 `ref_type/ref_id` 注册和存在性/tenant 归属校验。解析失败可能发生在 snapshot 创建前，建议锚定
  `workflow_step`，不要强依赖 snapshot id。
- step 进入 manual_review、manual_task INSERT 和创建审计在同一事务；部分唯一冲突精确复用既有 open task。
- audit 的 `target_public_id` 是 UUID，而 manual task 只有 bigint id；需明确以 workflow step/run 的 public_id
  作为审计目标，避免把 bigint 填入审计接口的 UUID 参数。
- approved/rejected/resolved 的合法状态迁移、actor 权限、before/after/evidence、重复处理幂等。
- 处理完成后怎样恢复原 step/run：行锁/fencing、action idempotency key 保持不变、claim 后 attempt 递增，且
  与 cancel/pause/recover 竞态结果确定。

### R130-6：补齐 PG 写路径的事务与隔离验收

G7 除现有固定输入正例外，至少加入：

- snapshot/feedback 的跨 tenant、跨 account/shop/listing/product/campaign/asset 注入拒绝；
- 五种 feedback subject map 正例和错配负例；同义双唯一键并发重放只生成一行；冲突内容拒绝；
- actor 未知/停用/越权、审计失败时业务写入同事务回滚、失败事务零审计；
- snapshot append-only 变异、`captured_at` 污染版本键变异、同窗口修订被错误做差变异；
- report_manual open 去重、重复处理、恢复/cancel/recover 竞态与失败清理；
- fixture/mock 来源在输入证据和审计中可辨认，但不被表述为真实平台能力。

### R130-7：重排 DAG 与最小批次

原“批次1=A+B+C”同时冻结接口、写 PG、定义窗口和实现聚合，评审面过大。建议改为四个可独立回滚的批次：

```text
批次 0（只定契约，业务代码保持原状）
  A0 Observation/ReportIdentity/VersionKey/DecisionBasis/FeedbackDraft/ManualRef 数据契约
  A1 两快照选择规则、五层 feedback 映射、policy/aggregation version、M1/M2/M3 消费矩阵

批次 1（事实层）
  B1 report version/evidence 纯函数
  B2 append-only SnapshotRepository + Collector(PG)
  B3 去重/冲突/跨 tenant/并发/clean-up 测试

批次 2（计算与回写层）
  C1 版本选择 + observed ROI + 五层聚合
  C2 FeedbackRepository 幂等 ledger
  C3 M1/M2/M3 消费/兼容投影及回执

批次 3（人工与编排层）
  D1 report_manual create/resolve/resume 事务服务
  D2 ads_flow workflow handlers 与错误分流
  D3 P0-2 端到端离线门禁、变异、全量回归与清理断言
```

依赖顺序：`批次0 -> 批次1 -> 批次2 -> 批次3`。测试不是最后一次补写；每批都有本批单元/PG/变异测试，
批次 3 再做完整离线闭环。无需改动 P0-1 冻结迁移。

## 五、round-131 最小交付要求

DSH 下一轮仍只做分析，提交一份回修后的执行契约，至少包含：

1. R130-1~R130-7 逐项处置表；
2. 修订后的 Gaps、DAG、四批边界、Owner/Reviewer、输入输出、验收和回滚；
3. 两快照选择真值表（同窗口修订/不重叠窗口/重复版本/时间倒退/零消耗）；
4. 五层 feedback 与 M1/M2/M3 消费矩阵；
5. report_manual ref/audit/resume 状态图；
6. 明确列出仍需用户裁决的项，未确认处不得用 legacy 默认值替代。

round-131 通过后，首个实现授权也只应覆盖“批次 1 事实层”；不得并行进入 ROI 回写和 workflow 编排。

## 六、阶段边界

- P0-2 通过只证明 app PG 上的离线领域闭环和 CI 门禁，不代表真实微信平台回读。
- 真实账号、CDP、页面选择器、真实两版本采集继续属于 P0-3。
- P0-3.5/P0-4 的真实写入和预算动作继续锁定。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-130-->
