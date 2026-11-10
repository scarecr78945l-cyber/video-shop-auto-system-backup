# round-129 DSH：P0-2 范围差异与任务拆解（仅分析，不实现）

> 日期：2026-09-08。输入：`from-cdx/round-128-cdx-P0-1-T9单项终验.md` §七、STATE、冻结契约
> （ddl-order / idempotency / test-strategy / error-codes / cid-engine-spec）、P0-1 代码与迁移证据。
> 状态：**P0-1 T1~T9 全部 COMPLETE**；本轮仅产出 P0-2 范围差异与任务 DAG，**不修改业务代码、迁移或契约**。
> 边界：P0-2 只做离线领域闭环（固定输入下快照去重/窗口/重试/人工确认/回写审计全过）；依赖真实账号、
> CDP、页面选择器、真实两次快照的事项一律留在 P0-3/P0-3.5/P0-4 资源门禁。

## 一、冻结的 P0-2 范围（round-03/05 定稿 + 契约冻结）

P0-2 = **回读领域闭环**（离线逻辑证据，非真实平台能力）：

| 子项 | 冻结定义 | 契约/字典锚点 |
|---|---|---|
| 两次快照模型 | 两次回读必须两个不同数据版本；`ad_report_snapshots` 唯一键含
  `(campaign_id, granularity, shop_listing_sku_id, asset_binding_id, window_start, window_end,
  attribution_mode, report_version_key)`（UNIQUE NULLS NOT DISTINCT） | ddl-order §五/§六；
  t3_expected.py:153；31tbl000001 |
| 解析版本 | `report_version_key = id:<platform_version_id> \| ts:<canonical_time> \|
  hash:<raw_evidence_hash>`（三源优先级）；`captured_at` 永不入版本键 | idempotency.md §二.8；
  ad_report_snapshots.report_version_key varchar(128) NOT NULL |
| ROI 计算 | CID 公式引擎已冻结（M 广告前利润/N 盈亏ROI/O 目标ROI/P 预估出价/V 扣回传最高出价/
  X 扣回传最高ROI出价）；ROI = 总gmv/总spend（分 int 口径） | cid-engine-spec.md；
  backend/domain/cid.py（P0-1 T5） |
| 回写幂等 | `roi_feedback_events.idempotency_key = fb:<source_snapshot_id>:<feedback_type>:
  <subject_type>:<subject_key(规范化)>:<aggregation_version>`；唯一键二：
  `(source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version)`；
  retry 与第二唯一键同义复用 | idempotency.md §二.9/§三.feedback；
  t3_expected.py:310-311 |
| REPORT_MANUAL 人工队列 | `manual_tasks.task_type ∈ {…, report_manual, …}`；部分唯一
  `px_tasks_open`（status pending/in_progress 仅一个 open 任务）；polymorphic
  `ref_type/ref_id` 仅应用层断言+审计（无 DB trigger） | 60enum000000:68；
  31tbl000001:150；ddl-order §五 manual_tasks |
| 流程/队列协作 | P0-2 管道以 workflow run/step 表达；WorkflowQueue 提供
  claim（FOR UPDATE SKIP LOCKED）/gate_retry（backoff 熔断）/manual_review/
  handle_error（retryable→gate_retry / manual_takeover→manual_review / terminal→failed） | test-strategy §四；
  backend/domain/workflow/queue.py（P0-1 T8） |

## 二、P0-1 已具备的可复用能力（证据路径）

| # | 能力 | 代码/契约/测试证据 | 可复用程度 |
|---|---|---|---|
| R1 | Postgres app schema 全部 P0-2 表与约束 | `project/migrations/versions/31tbl000001…`；`assert_t9_catalog.py`（31 表 exact-set PASS）；`auth000002` 终态 | 直接复用（冻结） |
| R2 | `ad_report_snapshots` 唯一键（含 report_version_key）与 7 FK | t3_expected.py:153；31tbl000001（7 组合 FK） | 直接复用（表结构） |
| R3 | `roi_feedback_events` 幂等唯一键 ×2 + 8 FK + 维度一致性 trigger | t3_expected.py:310-311；17trg000001 `trg_feedback_dimension_consistency`（ZT006） | 直接复用（约束 + DB 校验） |
| R4 | `manual_tasks` 队列（task_type=report_manual 枚举 + px_tasks_open + ix_tasks_status + trg_manual_policy_ref） | 60enum000000:68；31tbl000001:150；17trg000001:27 | 直接复用（表 + 部分唯一 + 策略校验） |
| R5 | WorkflowQueue 流程/队列原语 | backend/domain/workflow/queue.py（claim/gate_retry/manual_review/handle_error/幂等键黄金向量/五码预算） | 直接复用（P0-2 管道编排底座） |
| R6 | CID 公式引擎（ROI 相关计算） | backend/domain/cid.py；`assert_cid_engine.py`（T5-CID-ASSERT: PASS） | 直接复用（ROI 计算输入） |
| R7 | secret_store（凭证抽象）、auth/audit（ActorResolver/审计写入） | backend/infra/secret_store.py；backend/infra/auth/actor.py；backend/domain/audit.py | 直接复用（P0-2 写路径审计） |
| R8 | 错误码矩阵（PAGE_CHANGED/manual_takeover/backoff） | queue.py ERROR_ENTRIES（PAGE_CHANGED → manual_review；RATE_LIMIT 180s 熔断…） | 直接复用（失败分流字典） |
| R9 | 金额/时间/枚举口径（分 int、UTC、英文枚举） | test-strategy / data-audit DA-001；backend/ads/* 既有纯函数 | **参考**（见 G1，需移植到 PG 路径） |
| R10 | C-2 交换文件契约 + M1/M2 消费端 | idempotency.md；backend/ads/feedback.py + sourcing/ad_backfill.py（SQLite 侧） | 参考（P0-2 是否沿用文件载体待裁决） |

## 三、P0-2 尚缺能力（Gap 清单，逐项证据）

| # | 缺口 | 现状证据 | P0-2 需要新建 |
|---|---|---|---|
| G1 | **Postgres 路径快照收集器**：页面行 dict → canonical `report_version_key`（id/ts/hash 三源）→ 维度键 upsert | `backend/ads/report.py` 仅 SQLite（m5-ads.db，uq_snapshot_campaign_time 旧键）；**app schema 无对应 PG 实现**（grep report_version_key 在 backend 无命中） | `backend/domain/report/` PG 收集器：三源版本键生成 + 维度窗口键 upsert + collect_missing 断点 |
| G2 | **解析版本/原始证据哈希**：raw_evidence_hash 计算、platform_version_id 提取、canonical_time 归一化 | 契约 idempotency.md §二.8 已冻结，**无实现** | 版本键生成纯函数 + 单测（含三源优先级与 captured_at 排除） |
| G3 | **两次快照 ROI 计算器**：两快照差分 → 分层聚合（product/category/material/SKU/shop）→ ROI 事件 | CID 引擎有公式；legacy feedback.aggregate_by_category 是 SQLite 纯函数文件载体，未接 PG | `backend/domain/report/roi.py`：双快照输入 → 分层 ROI 事件行（聚合版本化 aggregation_version） |
| G4 | **回写幂等实现**：roi_feedback_events upsert（idempotency_key + 第二唯一键同义复用；DIMENSION_MISMATCH trigger 合规） | 表+trigger 已冻结；无写路径 | `backend/domain/report/writeback.py`：幂等 upsert + 23505 复用 + 审计（ActorResolver + audit） |
| G5 | **REPORT_MANUAL 人工队列**：解析失败/页面变更/版本缺口 → manual_tasks(task_type=report_manual) 创建 | manual_tasks 表/枚举/部分唯一已冻结；无业务创建逻辑 | 队列创建服务：px_tasks_open 唯一约束下仅 1 open；ref 绑定证据（ref_type/ref_id + 审计） |
| G6 | **流程/队列协作（P0-2 管道）**：collect→roi→writeback 编排为 workflow run/steps，gate_retry/manual_review 分流 | WorkflowQueue 原语齐备（T8）；无 P0-2 管道定义 | P0-2 管道定义 + step 处理器（worker）+ run 生命周期接入队列 |
| G7 | **离线验收测试集**：固定输入下快照去重/窗口/重试/人工确认/回写审计全过 | P0-1 测试覆盖队列/迁移/定义；无 P0-2 领域验收 | P0-2 验收 pytest：fixtures 文件内自建 + 临时 PG 库（复用 t9 演练模式） |

> 明确：**backend/ads/report.py / feedback.py（SQLite）不是 P0-2 完成度**——它们是旧系统 m5-ads.db 的
> 遗留实现，不写 app PG schema，且 report_version_key / roi_feedback_events 幂等 / report_manual 队列
> 均未实现。P0-2 的验收以 app PG schema 的离线逻辑证据为准。

## 四、P0-2 任务 DAG

```text
P0-2-A 版本键与原始证据（G2）
   ├─ 输入：冻结契约 idempotency §二.8、快照样例
   ├─ 输出：report_version_key 生成纯函数 + raw_evidence_hash + 单测
   ├─ 验收：三源优先级（id>ts>hash）、captured_at 排除、canonical_time UTC、黄金样例等值
   ├─ 回滚：纯函数无副作用，删除文件即可
   └─ 依赖：无（可最先）

P0-2-B Postgres 快照收集器（G1）
   ├─ 输入：P0-2-A 版本键、页面行 dict（fixture）、ad_report_snapshots 表
   ├─ 输出：SnapshotCollector(PG) run_once/collect_missing → 维度键 upsert
   ├─ 验收：维度唯一键（8 列 NULLS NOT DISTINCT）幂等；断点补快照；解析失败隔离记 errors
   ├─ 回滚：仅新增文件/迁移（无表变更），删除即可
   └─ 依赖：P0-2-A

P0-2-C 两次快照 ROI 计算器（G3）
   ├─ 输入：P0-2-B 快照、CID 公式、分层粒度配置
   ├─ 输出：roi.py 双快照差分 → 分层 ROI 事件行（aggregation_version 版本化）
   ├─ 验收：固定输入差分正确；分层聚合（product/category/material/SKU/shop）；弱样本策略
   ├─ 回滚：纯计算，删除即可
   └─ 依赖：P0-2-B

P0-2-D 回写幂等实现（G4）
   ├─ 输入：P0-2-C ROI 事件、roi_feedback_events 表（idempotency_key + 第二唯一键 + ZT006 trigger）
   ├─ 输出：writeback.py 幂等 upsert + 23505 复用 + 审计（ActorResolver）
   ├─ 验收：同源同键不重复回写；retry 复用；DIMENSION_MISMATCH 负例 RC 拦截；审计留痕
   ├─ 回滚：新增文件无表变更，删除即可
   └─ 依赖：P0-2-C

P0-2-E REPORT_MANUAL 人工队列（G5）
   ├─ 输入：解析失败/PAGE_CHANGED/版本缺口信号、manual_tasks 表
   ├─ 输出：report_manual 任务创建服务（px_tasks_open 唯一约束下仅 1 open；ref 绑定 + 审计）
   ├─ 验收：失败即建任务；同 ref 已 open 不重复；完成后可再建；审计留痕
   ├─ 回滚：新增文件，删除即可
   └─ 依赖：P0-2-A（失败信号来自收集/解析）

P0-2-F P0-2 管道流程编排（G6）
   ├─ 输入：P0-2-B/C/D/E 处理器、WorkflowQueue（T8）
   ├─ 输出：P0-2 管道 run/step 定义 + worker 处理器 + 错误分流接线
   ├─ 验收：collect→roi→writeback 串行；PAGE_CHANGED→manual_review；
   │        RATE_LIMIT→gate_retry（180s）；五码预算；并发 claim 唯一
   ├─ 回滚：管道定义是新增，队列表复用（无表变更）
   └─ 依赖：P0-2-B/C/D/E

P0-2-G P0-2 离线验收测试集（G7）
   ├─ 输入：P0-2-A~F 全部交付物
   ├─ 输出：P0-2 验收 pytest（fixtures 文件内自建 + 临时 PG 库，复用 t9 演练模式）
   ├─ 验收：固定输入下快照去重/窗口/重试/人工确认/回写审计全过；185 回归不破坏
   ├─ 回滚：测试文件可独立删除
   └─ 依赖：P0-2-A~F

P0-2 里程碑裁决：P0-2-A~G 全过 → P0-2 COMPLETE（离线逻辑证据）→ 解锁 P0-3 真实只读回读
```

## 五、Owner/Reviewer、输入/输出、验收、回滚、失败分流

统一约定（沿用 P0-1 纪律）：

- **Owner/Reviewer**：DSH 实现（Owner），Codex 独立复核（Reviewer），以 `_interop` 轮次换手；
  每包交付物带 SHA-256 + 标准回归（185/61/tsc/T5 CLI/T9 CI）。
- **输入输出**：见 DAG 各节点；所有跨包接口先冻结（版本键 dict、快照行 dict、ROI 事件 dict、
  任务创建参数），后续包按冻结接口对接，禁止跨包直接依赖内部实现。
- **验收**：每包 pytest 全绿 + 正反例探针（变异/负例 RC=1）+ 与既有 185 回归零破坏；
  关键点固化为变异（如 report_version_key 漏 captured_at 排除、ROI 事件重放、report_manual 重复 open）。
- **回滚**：P0-2 全部为新增文件 + 复用既有表（**不新增 migration**，除非发现契约缺口——那先回 Codex
  冻结修订再动）；单包回滚 = 删除该包文件；管道关闭 = 停止 run 创建，队列现有数据可清理。
- **失败分流**：复用 queue.ERROR_ENTRIES——`PAGE_CHANGED`→manual_review（建 report_manual 任务）、
  `RATE_LIMIT`→gate_retry 180s、`TIMEOUT`→60s、`NO_MATCH`→120s、`PLATFORM_REJECT`→manual_review、
  `UNEXPECTED`→60s retry、terminal→failed；五码预算耗尽→failed 终态（不再回收）。

## 六、P0-3 门禁事项（不混入 P0-2）

以下事项**不进入 P0-2 离线验收**，继续由 P0-3/P0-3.5/P0-4 资源门禁控制：

- 真实微信小店账号/店铺/投放报表连接与登录态（CDP 适配器、账号 profile、页面选择器/探活）；
- 真实平台两次不同版本快照抓取与留证（P0-3 硬验收：对既存投放取得两次真实快照）；
- 真实上架/投放写操作与人工确认（P0-3.5 M4 契约核对 → P0-4 最小真实写入闭环）；
- 真实报表更新节奏测量（回读间隔配置需实测后定，P0-3 阶段进行，P0-2 不预设）。

P0-2 使用 fixtures/固定输入验证**逻辑**（去重/窗口/重试/人工确认/回写审计），并在审计中标记
`source=mock/fixture`，不把 fixtures 当真实能力。

## 七、需用户裁决/补充的资源（附默认技术建议）

| # | 事项 | 默认技术建议（无用户裁决则采用） |
|---|---|---|
| D1 | P0-2 回写载体：沿用 C-2 JSON 文件交换（legacy）还是直写 app PG | **直写 app PG**（roi_feedback_events 已在冻结 schema；文件载体仅作 M1/M2 跨模块通知的可选出口，默认关闭） |
| D2 | ROI 分层回写粒度（product/category/material/SKU/shop）一期启用哪些 | 一期 product + category（M1 选品消费）+ material（M2 素材评估）；SKU/shop 维度保留事件结构但默认不产出行 |
| D3 | 弱样本阈值与人工确认边界（ROI 事件 sample_count 下限；report_manual 强审条件） | 沿用 v0.5 语义：sample_count<5 仍输出由消费端过滤；report_manual 仅当解析失败/PAGE_CHANGED/版本缺口/ROI 异常时才建 |
| D4 | 两次快照「窗口」定义（window_start/end 与决策窗口） | window = 平台版本跨度（ts 归一化后），决策窗口与抓取周期分离（P0-3 实测后调） |
| D5 | P0-2 是否新增 migration | 默认**不新增**（复用冻结表）；若发现表/枚举缺口，先回 Codex 修订契约再动 |

## 八、最小开发批次建议

按依赖顺序分三批（每批交付后 Codex 复核再进下一批）：

1. **批次 1（领域纯逻辑，无队列）**：P0-2-A 版本键 + P0-2-B 快照收集器 + P0-2-C ROI 计算器
   （纯函数 + PG upsert + 单测，不接 workflow）；
2. **批次 2（写路径与人工队列）**：P0-2-D 回写幂等 + P0-2-E REPORT_MANUAL 队列（接审计；
   DIMENSION_MISMATCH 负例、report_manual 唯一 open 负例固化）；
3. **批次 3（编排与验收）**：P0-2-F 管道流程编排（WorkflowQueue 接线）+ P0-2-G 离线验收测试集
   （快照去重/窗口/重试/人工确认/回写审计全过 + 185 回归零破坏）。

## 九、交接

请 Codex 复核本拆解（尤其：G1~G7 缺口是否完备、DAG 依赖是否正确、最小批次是否合理、D1/D2 默认建议
是否可接受），确认后再决定是否进入 P0-2 实现；P0-2 实现不开始前，本文件即分析交付物。
P0-2 完成边界：仅表示本地内部回读领域逻辑与 CI 门禁通过，不表示真实微信平台能力或全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-130-->