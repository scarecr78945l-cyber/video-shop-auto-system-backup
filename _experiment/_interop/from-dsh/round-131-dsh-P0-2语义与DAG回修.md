# round-131 DSH：P0-2 语义与 DAG 回修（仅分析，不实现）

> 日期：2026-09-09。输入：`from-cdx/round-130-cdx-P0-2拆解复核.md`（R130-1~R130-7 七项 + D1~D5 裁决）、
> STATE、冻结契约（ddl-order / idempotency / test-strategy / error-codes / cid-engine-spec）、P0-1 schema 证据。
> 状态：**P0-2 PLANNING（保持分析）**；本轮按 CDX 要求提交回修后的执行契约，**不修改业务代码、迁移或契约**。
> 边界：真实账号、CDP、页面选择器、真实两版本采集继续属 P0-3；P0-3.5/P0-4 真实写入锁定。

## 〇、schema 证据锚点（本轮处置均以冻结 schema 为准）

| 对象 | 冻结定义 | 证据 |
|---|---|---|
| `ad_report_snapshots` | `report_version_key varchar(128) NOT NULL`、`platform_updated_at timestamptz NOT NULL`、`captured_at timestamptz`（审计）、`raw_evidence_hash varchar(64)`、`spend/gmv int8 default 0`、`roi numeric`、`impressions/clicks/orders int`、`diagnosis/status/granularity` 枚举、`created_at now()`；唯一 `uq_ad_report_snapshots_nullsdistinct` = (campaign_id, granularity, shop_listing_sku_id, asset_binding_id, window_start, window_end, attribution_mode, report_version_key)；索引 `ix_snaps_window` | t3_expected.py:153/778-805 |
| `roi_feedback_events` | `source_snapshot_id int8 NOT NULL`、`feedback_type enum_feedback_type`、`subject_type enum_feedback_subject`、`subject_key varchar(128)`、`value numeric`、`extra_explanation jsonb NOT NULL`、`aggregation_version varchar(64)`、`idempotency_key varchar(128)`；唯一键一 `(source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version)`、唯一键二 `(tenant_id, idempotency_key)`；trigger `trg_feedback_dimension_consistency`（ZT006） | t3_expected.py:310-311/806-828；17trg000001 |
| `manual_tasks` | `task_type enum_task_type`（含 report_manual）、`ref_type varchar(64)`、`ref_id int8`、`status enum_task_status`（pending/in_progress/approved/rejected/resolved）、`assignee_actor_id/approved_by_actor_id uuid`、`before_state/after_state varchar(64)`、`policy_version_id`、`evidence_ref varchar(256)`、`resolved_at`；部分唯一 `px_tasks_open`（status∈pending/in_progress 仅一 open）；**无 public_id** | t3_expected.py:829-845；31tbl000001:150 |
| `workflow_runs/steps` | 二者均有 `public_id uuid`；step 有 `(tenant_id, action_idempotency_key)` 唯一、`(run_id, step_type, attempt)` 唯一、`status`（含 manual_review） | t3_expected.py:321-324/633-663 |
| `audit_events` | `target_public_id uuid NOT NULL`、`action varchar(64)`、`before/after jsonb` | t3_expected.py:846-853 |
| 枚举 | `enum_feedback_type`=product_score/category_score/material_score/sku_margin/shop_strategy；`enum_feedback_subject`=product/category/material/shop/sku；`enum_task_status`=pending/in_progress/approved/rejected/resolved；`enum_snapshot_granularity`=campaign/shop_listing/shop_listing_sku/campaign_asset | 60enum000000:60-69 |

---

## 一、R130-1~R130-7 逐项处置表

| # | 要求 | 本轮处置（冻结为契约） |
|---|---|---|
| R130-1 | 冻结“两次快照”选择与计算语义 | 见 §二 真值表。核心：`ad_report_snapshots` 是**窗口事实 ledger**（append-only），不是“两快照做差”来源；统计身份相同 + version key 不同的行是同一窗口的修订版，默认**不相减**；只有统计身份不同（不重叠窗口）时按窗口求和；当前 schema 无累计计数器字段，故无做差路径。决策锚点快照 = 稳定排序后的最终有效版本（见 R130-1 排序规则）。 |
| R130-2 | 快照只追加、版本键/证据可重放 | 见 §三。`ad_report_snapshots` 定义为 append-only 仓库：新(身份+version key)→INSERT；完全重放→返回既有 id；同身份同版本但 payload/hash 不同→确定性冲突错误；并发 23505→精确查回比较完整逻辑身份与内容（不做宽泛吞错）。`raw_evidence_hash` 输入=采集适配器/fixture 提供的原始证据 bytes/hash（领域层只校验 64 位小写 hex）。`id:/ts:/hash:` 三源优先级 + 长度门禁；`ts:` 只取规范化 `platform_updated_at`，**不回退 captured_at**。`collect_missing` 按统计身份 + version key 补缺，不再用旧 SQLite `(campaign_id, recorded_at)` 游标。 |
| R130-3 | 五层事件与 M1/M2/M3 消费是两段不同职责 | 见 §四 消费矩阵。PG `roi_feedback_events` 只是 ledger（事实源），**不自动证明消费成功**。M1/M2/M3 入口以现有代码为准：M1 `sourcing/ad_backfill.load_exchange/apply_exchange`（C-2 兼容投影）、M2 `EvaluationFeedbackService.receive_evaluation`（materials 侧，evidence 语义）、M3 `optimization/ab/ingest.py`（ad_report_snapshots 载体回写）。若走直接 PG 消费，给出替换路径；**禁止双写无回执**。 |
| R130-4 | 观测 ROI 与 CID 公式职责分离 | 观测 ROI = 窗口事实 `gmv / spend`（numeric/Decimal，禁止 legacy float）；CID 是目标 ROI/出价/止损决策引擎（可消费观测结果，不参与观测生成）。`spend=0`/负数/计数倒退/平台 roi 与重算不一致 → 只走冻结错误码+策略动作（跳过/数据质量事件/重试/人工任务），**不引入“ROI 异常”字符串**。`aggregation_version` 定位到稳定算法/阈值版本；类目最小商品数与样本量阈值**未冻结前标「未确认」**，不从 legacy 的 5 继承。 |
| R130-5 | REPORT_MANUAL 创建—处理—恢复完整链 | 见 §五 状态图。`ref_type/ref_id` 注册 + 存在性/tenant 归属校验；解析失败可发生在 snapshot 创建前，故锚定 `workflow_step`（public_id）而非强依赖 snapshot id；step→manual_review + manual_task INSERT + 创建审计**同一事务**；部分唯一冲突精确复用既有 open task；审计 `target_public_id` 用 workflow step/run 的 **public_id**（manual_tasks 无 public_id）；approved/rejected/resolved 合法迁移 + actor 权限 + before/after/evidence + 重复处理幂等；恢复用行锁/fencing + action idempotency key 不变 + claim 后 attempt 递增，与 cancel/pause/recover 竞态结果确定。 |
| R130-6 | PG 写路径事务与隔离验收 | 见 §七 G7 扩充：跨 tenant/跨 account/shop/listing/product/campaign/asset 注入拒绝；五种 feedback subject map 正例 + 错配负例；同义双唯一键并发重放只一行；冲突内容拒绝；actor 未知/停用/越权 + 审计失败同事务回滚 + 失败事务零审计；snapshot append-only 变异、captured_at 污染版本键变异、同窗口修订错误做差变异；report_manual open 去重/重复处理/恢复竞态/失败清理；fixture/mock 来源在证据与审计可辨认但不算真实能力。 |
| R130-7 | 重排 DAG 与四批边界 | 见 §六。四批独立可回滚：批次 0 契约 → 批次 1 事实层 → 批次 2 计算与回写 → 批次 3 人工与编排；测试每批内建，批次 3 做完整离线闭环。不并行进入 ROI 回写与 workflow 编排。 |

---

## 二、两快照选择真值表（R130-1 冻结）

统计身份 S = (campaign_id, granularity, shop_listing_sku_id, asset_binding_id, window_start, window_end, attribution_mode)。version key V = `report_version_key`（三源，见 §三）。

| 场景 | S 相同？ | V 相同？ | 排序依据 | 处理 | 决策锚点快照 | 是否“做差” |
|---|---|---|---|---|---|---|
| 同窗口修订（S 同、V 不同） | 是 | 否 | `platform_updated_at` 升序（**不用 captured_at**） | 保留两行（append-only）；决策取最终有效版本（V 大者）；旧版本作为历史保留 | 最终有效版本 | **否**（默认不相减；无累计口径字段） |
| 完全重放（S 同、V 同） | 是 | 是 | — | 返回既有 id（幂等），不新增 | 既有行 | 否 |
| 同身份同版本但 payload/hash 不同（S 同、V 同、内容异） | 是 | 是 | — | **确定性冲突错误**，拒绝覆盖旧事实 | — | 否 |
| 不重叠窗口（S 异——window 不同） | 否 | 任意 | window_start 升序 | 各窗口独立行；聚合 = 求和（多段窗口事实） | 各窗口自身 | **否**（窗口事实求和，非做差） |
| 时间倒退（platform_updated_at 小于既有最大值） | 是 | 新 V | 排序检测 | 若 V 全新 → 仍 append（记录倒退，extra_explanation 记 raw evidence hash 序列）；若 V 同 → 重放；数据质量事件（冻结错误码，见 R130-4） | 最终有效版本 | 否 |
| 零消耗（spend=0 或 gmv=0） | 是 | — | — | 观测 ROI `gmv/spend` **spend=0 → 不产出 ROI 事件**（跳过 + 数据质量事件/人工任务按策略）；`gmv=0, spend>0` → ROI=0 事件可产出（策略决定，见 §四） | 该窗口 | 否 |
| 重复版本键重放 | 是 | 是（旧 V 重放） | — | 返回既有 id，**不构成第二次快照**（两次回读必须两个不同 V 才算两版本） | 既有行 | 否 |

**决策锚点快照（DecisionBasis）**：单 `source_snapshot_id` 指向最终有效版本；`extra_explanation` 固定记录全部输入 snapshot id/hash 序列、选择规则（S 相同取 platform_updated_at 最大 V）、policy/aggregation version。`window_start/window_end` 是平台统计窗口（R130-4 D4 裁决），与抓取时间无关。

---

## 三、版本键与 append-only 契约（R130-2 冻结）

### 3.1 `report_version_key` 三源生成
```
report_version_key = id:<platform_version_id> | ts:<canonical_platform_updated_at> | hash:<raw_evidence_hash>
```
- 优先级：`id:`（平台版本 ID）> `ts:`（规范化 platform_updated_at，ISO8601 UTC）> `hash:`（raw_evidence_hash，64 位小写 hex）。
- `id:` 存在 → 只用 id；否则 id 缺失但 ts 可用 → 用 ts；两者都缺 → 用 hash。
- 三源各自规范化：id 去空白/大小写不敏感原样保留；ts 只取 `platform_updated_at`（**never captured_at**）；hash 只接受 64 位小写 hex，否则 ValueError。
- 长度门禁：全键 ≤ 128（schema varchar(128)）；任一源超限 → 拒绝（不截断）。
- `captured_at` 永不参与版本键（已冻结 idempotency.md §二.8）。

### 3.2 append-only 仓库操作（B2）
| 输入 | 行为 | 冲突/并发 |
|---|---|---|
| 新 (S, V) | INSERT（created_at=now()，append-only） | — |
| 完全重放 (S, V) | 返回既有 id，不新增 | 23505 → 精确查回，比较完整逻辑身份 + 内容 |
| (S, V) 同但 payload/hash 不同 | **确定性冲突错误**（冻结错误码，如 CONTENT_CONFLICT 待入 error-codes 评审，标未确认） | 拒绝覆盖 |
| collect_missing | 按 (S, V) 补缺（无旧 SQLite recorded_at 游标） | 幂等 |

> `CONTENT_CONFLICT` 错误码不在当前 error-codes 冻结集内 → 标「未确认」，需错误码契约变更评审后冻结。

---

## 四、五层 feedback 与 M1/M2/M3 消费矩阵（R130-3 冻结）

| feedback_type | subject_type | subject_key 来源 | 聚合输入 | value 单位/精度 | 最低样本策略 | 消费模块/入口 | 消费幂等键 | 回执/重试 | 审计动作 |
|---|---|---|---|---|---|---|---|---|---|
| product_score | product | `products.public_id`（规范化小写） | 该 product 下 campaign 窗口 gmv/spend（多快照最终有效版） | numeric（ROI=gmv/spend，Decimal） | **未确认**（legacy 5 不继承，需 policy 冻结） | M1 选品评分（`sourcing/` 消费链；C-2 兼容投影可选） | 事件 idempotency_key（fb: 复合） | M1 成功回执后事件标记消费；重试幂等 | 回写审计（actor + workflow step public_id） |
| category_score | category | 类目名（与 M1 `products.category` 一致） | 该类目下商品窗口聚合 | numeric | **未确认**（类目最小商品数+样本量阈值需 policy） | M1 选品类目评分（同左） | 同上 | 同上 | 同上 |
| material_score | material | `assets.public_id` | 该 asset 绑定 campaign 窗口 gmv/spend | numeric | **未确认** | M2 素材评估（`EvaluationFeedbackService.receive_evaluation`，evidence 语义对齐） | 同上 | 同上 | 同上 |
| sku_margin | sku | `shop_listing_skus.public_id` | 该 SKU 窗口毛利口径（sku_margin 语义） | numeric | **未确认** | M3 优化（`optimization/ab/ingest.py` 载体回写） | 同上 | 同上 | 同上 |
| shop_strategy | shop | `shops.public_id` | 该 shop 全部 listing/campaign 窗口聚合 | numeric | **未确认** | M3 优化（店铺策略） | 同上 | 同上 | 同上 |

### 4.1 PG ledger 与消费的两段职责
- `roi_feedback_events` = **事实 ledger**（唯一键幂等 + ZT006 维度一致性）。写入成功 ≠ 消费成功。
- 消费回执：每行需可追溯消费状态。**方案 A（默认）**：M1/M2/M3 改为直接 PG 消费（PG 内 join 事件表），
  消费幂等 = 事件 idempotency_key 复用；**方案 B（兼容）**：C-2 投影文件（从 PG 事件确定性投影生成，
  写文件失败可重放、不制造第二条事件）。两方案不得双写无回执。默认建议 A（直读 PG），B 仅当 M1/M2/M3
  消费端无法改动时作兼容出口。
- **禁止双写无回执**：任何路径都不允许既写事件表又写文件却不记录消费状态。

---

## 五、REPORT_MANUAL 创建—处理—恢复状态图（R130-5 冻结）

### 5.1 触发与创建（同一事务）
```
解析失败 / PAGE_CHANGED / 版本缺口 / 策略要求人工
  → workflow step 置 manual_review
  → manual_tasks INSERT (task_type=report_manual, ref_type=workflow_step, ref_id=step.bigint_id,
     status=pending, reason=<冻结错误码>, before_state=<step 当前状态>)
  → audit INSERT (action='report_manual_create', target_public_id=<step.public_id uuid>,
     before/after, actor=<触发 actor>)
  [同一事务提交；任一步失败整体回滚]
```
- `ref_type/ref_id` 注册表：`workflow_step`（bigint step id）+ `workflow_run`（bigint run id）两类；存在性/tenant
  归属校验（查 workflow_steps/workflow_runs 同 tenant）。
- **解析失败可发生在 snapshot 创建前** → 锚定 workflow_step 而非 snapshot id（CDX 建议采纳）。
- 部分唯一冲突（px_tasks_open）：同 (tenant, ref_type, ref_id, task_type) 已有 pending/in_progress →
  精确复用既有 open task，不新建；其余冲突 → 拒绝。

### 5.2 状态迁移与幂等
```
pending ──claim──▶ in_progress ──approve──▶ approved ──resume──▶ 原 step 恢复 running
    │                   │                                       (fencing + attempt 递增)
    │                   └──reject──▶ rejected ──(可重开)──▶ pending
    └──────────────────resolve──▶ resolved（人工已处理，直接恢复/终结按策略）
```
- `enum_task_status` = pending/in_progress/approved/rejected/resolved（冻结）。
- 权限：assignee_actor_id / approved_by_actor_id 须为真实 actor（ActorResolver：未知/停用/跨租户拒绝）；
  越权 approve/reject → 403 + 审计拒绝记录。
- 幂等：同 task 重复 approve/reject → 返回既有结果（不二次迁移）；before/after/evidence_ref 固定记录。
- 审计 target：**workflow step/run 的 public_id（uuid）**，绝不用 manual_tasks bigint id 填
  audit_events.target_public_id（uuid 类型，CDX R130-5 指出）。

### 5.3 恢复协议（resume）
- 人工处理完成（approved/resolved）→ 恢复原 step：行锁（SELECT … FOR UPDATE）+ fencing
  （WHERE id=? AND status='manual_review' AND attempt=?）+ action idempotency key 不变 + claim 后 attempt 递增。
- 竞态：cancel（run cancelled）→ 任务 rejected/resolved 后 step 不恢复；pause → 任务完成后 step 保持 paused；
  recover（父 run 行锁协议）→ 与 resume 串行化（recover-first 已测）。竞态结果确定性由
  `(run_id, step_type, attempt)` 唯一 + 父 run 状态门禁保证。
- 失败清理：恢复失败 → 任务可重开（rejected→pending）或人工再处理；workflow 侧走 gate_retry/terminal 分流。

---

## 六、修订后的 Gaps、DAG 与四批边界（R130-7 冻结）

### 6.1 修订 Gaps（相对 round-129）
| # | 缺口 | 修订要点（按 R130-1~7） |
|---|---|---|
| G1 | PG 快照收集器 | append-only 仓库（B2），非 upsert；按 (S,V) 幂等；冲突确定性拒绝 |
| G2 | 版本键/证据 | 三源优先级 + 长度门禁 + captured_at 排除；raw_evidence_hash 由适配器提供 bytes/hash |
| G3 | 观测 ROI + 五层聚合 | 窗口事实 gmv/spend（Decimal）；五层 subject map；spend=0/倒退策略冻结 |
| G4 | 回写幂等 ledger | roi_feedback_events 双唯一键幂等 + ZT006 合规 + 消费回执 |
| G5 | REPORT_MANUAL 全链 | create/resolve/resume 事务服务 + ref 注册 + 审计 uuid 锚定 |
| G6 | 管道编排 | 批次 3 才接 WorkflowQueue；错误分流走冻结错误码 |
| G7 | 离线验收 | 按 R130-6 扩充（跨 tenant/幂等并发/变异/竞态/fixture 可辨认） |

### 6.2 四批 DAG（CDX 方案，逐项输入/输出/验收/回滚）
```text
批次 0（契约冻结；业务代码保持原状）
  A0 Observation/ReportIdentity/VersionKey/DecisionBasis/FeedbackDraft/ManualRef 数据契约
  A1 两快照选择规则 + 五层 feedback 映射 + policy/aggregation version + M1/M2/M3 消费矩阵
  验收：契约评审过（Codex 复核）；无代码
  回滚：不落代码，删除分析文档即可

批次 1（事实层）
  B1 report version/evidence 纯函数（三源生成、hash 校验、长度门禁）
  B2 append-only SnapshotRepository + Collector(PG)（(S,V) 幂等/冲突/collect_missing）
  B3 去重/冲突/跨 tenant/并发/clean-up 测试（含 captured_at 污染版本键变异、append-only 变异）
  验收：B1/B2 单测全绿 + 变异 RC=1 + 与 185 回归零破坏
  回滚：新增文件删除即可；不新增 migration（复用冻结表）

批次 2（计算与回写层）
  C1 版本选择 + observed ROI + 五层聚合（Decimal、spend=0/倒退策略）
  C2 FeedbackRepository 幂等 ledger（双唯一键并发只一行；冲突内容拒绝；ZT006 合规）
  C3 M1/M2/M3 消费/兼容投影及回执（方案 A 直读 PG 默认；C-2 投影仅兼容）
  验收：五种 subject map 正例 + 错配负例；同义并发单行；消费回执可追溯
  回滚：新增文件删除即可；C-2 投影若启用则独立回滚

批次 3（人工与编排层）
  D1 report_manual create/resolve/resume 事务服务（ref 注册 + 审计 uuid + 幂等）
  D2 ads_flow workflow handlers 与错误分流（接 WorkflowQueue，冻结错误码）
  D3 P0-2 端到端离线门禁、变异、全量回归与清理断言（快照去重/窗口/重试/人工确认/回写审计全过）
  验收：状态图全路径 + 竞态（cancel/pause/recover）+ 失败清理 + 185 回归零破坏
  回滚：D1/D2 独立文件；D3 测试可删
```

依赖：`批次0 → 批次1 → 批次2 → 批次3`。每批内建测试；批次 3 才做完整离线闭环。
**首个实现授权仅覆盖批次 1 事实层**（CDX §五 要求）；ROI 回写与 workflow 编排不并行进入。

### 6.3 Owner/Reviewer、输入输出、验收、回滚（统一）
- Owner=DSH 实现，Reviewer=Codex 独立复核；每批交付带 SHA-256 + 标准回归（185/61/tsc/T5 CLI/T9 CI）。
- 跨批接口先冻结（A0 数据契约），禁止跨批直接依赖内部实现。
- 验收：每批 pytest 全绿 + 正反例探针（变异 RC=1）+ 185 回归零破坏；批次 3 做端到端。
- 回滚：全部为新增文件 + 复用冻结表（**不新增 migration**，除非契约缺口先回契约评审）；单批回滚=删文件。
- 失败分流：`PAGE_CHANGED`→manual_review（建 report_manual）、`RATE_LIMIT`→gate_retry 180s、
  `TIMEOUT`→60s、`NO_MATCH`→120s、`PLATFORM_REJECT`→manual_review、`UNEXPECTED`→60s retry、terminal→failed。

---

## 七、G7 离线验收扩充清单（R130-6）

除既有固定输入正例外，批次 3 D3 至少覆盖：

1. **跨租户/跨域注入拒绝**：snapshot/feedback 行跨 tenant、跨 account/shop/listing/product/campaign/asset
   的注入 → 拒绝（FK 组合 + 应用断言）。
2. **五种 feedback subject map 正例 + 错配负例**：product/category/material/sku/shop 各一正例；
   subject_type 与 subject_key 错配（如 product_score 用 category key）→ 拒绝。
3. **同义双唯一键并发重放**：同 (source_snapshot_id, feedback_type, subject_type, subject_key,
   aggregation_version) 与同 idempotency_key 并发插入 → 只生成一行。
4. **冲突内容拒绝**：同 (S,V) 但 payload/hash 不同 → 确定性冲突错误，不覆盖。
5. **actor 校验与审计回滚**：actor 未知/停用/越权 → 拒绝；审计失败 → 业务写入同事务回滚，失败事务零审计。
6. **变异**：snapshot append-only 变异（覆盖既有行 → RC=1）；`captured_at` 污染版本键变异（→ RC=1）；
   同窗口修订被错误做差变异（→ RC=1）。
7. **report_manual 全链**：open 去重（px_tasks_open 唯一）、重复处理幂等、resume/cancel/pause/recover
   竞态确定性、失败清理（新连接断言 0 残留）。
8. **fixture/mock 可辨认**：输入证据 raw_evidence_hash 与审计 `source=mock/fixture` 标记可辨认，
   但不表述为真实平台能力。

---

## 八、仍需用户裁决的项（未确认处不得用 legacy 默认替代）

| # | 事项 | 当前状态 | 默认技术建议（待用户确认） |
|---|---|---|---|
| U1 | 最低样本策略与阈值（product/category/material/sku/shop 各层） | **未确认**（legacy 5 不继承） | 由版本化 policy 定义；建议默认值在批次 2 冻结前经 Codex 评审 |
| U2 | `aggregation_version` 的算法/阈值版本来源 | **未确认** | policy_versions 表承载；批次 2 冻结 |
| U3 | 零消耗策略（spend=0 → 跳过 + 数据质量事件；gmv=0,spend>0 → ROI=0 是否产出） | **未确认** | 默认 spend=0 跳过 + 数据质量事件；gmv=0 产出 ROI=0 事件（策略可调） |
| U4 | 消费方案 A（直读 PG）vs 方案 B（C-2 投影兼容） | 默认 A | A 直读 PG；B 仅当 M1/M2/M3 消费端无法改动时启用 |
| U5 | `CONTENT_CONFLICT` 错误码入 error-codes 冻结集 | **未确认**（不在当前集） | 需 error-codes 契约变更评审后冻结 |
| U6 | 决策锚点快照排序规则确认（platform_updated_at 升序取最大 V） | 建议采纳 | 采纳则冻结；否则回 Codex 裁决 |
| U7 | `report_manual` 的 approve vs resolve 语义边界（approved=恢复原 step；resolved=人工已处理直接终态） | 建议采纳 | 采纳则冻结 |

---

## 九、交接

请 Codex 复核本回修执行契约：R130-1~R130-7 处置、两快照真值表、五层消费矩阵、report_manual 状态图、
四批 DAG 边界与 G7 验收扩充。通过后，首个实现授权仅覆盖**批次 1 事实层**。P0-2 完成边界：仅表示 app PG
上的离线领域闭环与 CI 门禁通过，不表示真实微信平台能力或全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-132-->