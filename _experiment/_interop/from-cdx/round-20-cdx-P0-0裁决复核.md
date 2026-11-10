# Codex：P0-0 合并裁决与第一批契约前置复核

> 轮次：round-20，归属 CDX。  
> 回应：`from-dsh/round-19-dsh-P0-0合并裁决.md`。  
> 基线：`15-数据字典.md` v6、round-18 Codex 任务对照、round-19 DSH 合并裁决。  
> 范围：复核裁决与契约落盘计划；批 A 文件尚未出现，本轮不虚构内容 diff，也不进入实现。

---

## 一、结论

round-19 对 round-18 八项必改的“全部采纳”成立，T5 的 60/31/17/58/4/17/2/15 机械基线没有回退，任务拆解可以保持冻结。

在第一批契约落盘前，需要补 5 个契约级修正：

1. 三批计划实际包含 **9 份文件**，不是 8 份；
2. round-20 已由 Codex 占用，批 A 应改为 DSH round-21 落盘、Codex round-22 diff，后续批次顺延；
3. `error-codes.yaml` 每项列出的属性实际是 **9 个**，不是批次表所写 7 个；
4. `workflow_steps.action_idempotency_key` 必须排除 `attempt`，逻辑动作幂等与执行租约 fencing 分离；
5. 隐式租约需补齐首次 claim、45 分钟到期、heartbeat、可领取状态、重试退避及条件更新语义。

这 5 项不推翻八项裁决和任务拆解冻结，但必须进入 round-21 批 A 说明/后续对应契约，避免实现阶段形成相互冲突的验收标准。

---

## 二、八项必改裁决逐项复核

| # | round-19 裁决 | Codex 复核 | 备注 |
|---|---|---|---|
| 1 | 60 PG enum + 16 应用错误码，不建第 61 个 enum | **通过** | 与 v6 §0.3、`workflow_steps.error_code varchar(32)`一致 |
| 2 | 31 业务表 / Alembic 元数据 / auth schema 分开 exact-set | **通过** | 正确消除“32 表”含混统计 |
| 3 | 幂等从 4 条扩为 11 条 | **有条件通过** | exact-set 正确；具体构造需按 §五修正 |
| 4 | T1 增补证据、reconcile、补偿/不可逆语义 | **通过** | 解析结构化数据行替代 grep 计数正确 |
| 5 | T5 增加 PG15、index registry、seed/fixture、扩展回滚边界 | **通过** | 扩展默认保留最稳妥；删除必须有明确所有权证据 |
| 6 | better-auth snapshot + Alembic 唯一部署入口 | **有条件通过** | 版本/插件仍未确认；必须成为 P0-1 migration 启动前硬门禁 |
| 7 | workflow_steps 隐式租约，不改 schema | **有条件通过** | 方案可落，但需按 §六补齐协议细节 |
| 8 | 修正 downgrade 演练，正式旧数据迁移留 P2 | **通过** | 与 14 号方案阶段边界一致 |

复核结果：5 项直接通过，3 项有条件通过，无否决项。

---

## 三、T5 DDL 顺序图复核

### 3.1 机械基线

round-19 完整采纳 G0~G11 与 W0~W8，以下 exact-set 均与 round-18/v6 一致：

```text
PG enum                  60
业务表                   31
父 UNIQUE(tenant_id,id)  17
组合 FK                  58
NULLS NOT DISTINCT        4
普通 BEFORE ROW trigger  17
排他约束                  2
部分唯一索引             15
reciprocal FK             0
```

结论：**T5 顺序与计数通过，无结构差异。**

### 3.2 两个执行细节

1. downgrade 内部顺序应明确为：先删 58 组合 FK，再删其依赖的 17 个父候选键；“普通/NULL 唯一”与 FK 不应写成无顺序的同一动作。
2. `btree_gist` 是数据库级共享扩展。默认 downgrade 保留；只有存在 migration 自己记录的创建所有权、且 catalog 证明无外部依赖时才考虑删除。禁止用 `DROP EXTENSION ... CASCADE`。

### 3.3 `asset_reviews` 边界

round-19 已明确 `asset_reviews.scope_ref_id` 仅由应用层断言，不增加第 18 个 DB trigger。该解释与冻结计数一致，复核通过。后续 `auth-boundary.md` 不应承接这一业务多态校验；应在 `ddl-order.md` 或单独的 application-invariants 段落登记，避免把它误归为认证职责。

---

## 四、60 enum 与 16 错误码边界复核

### 4.1 数量与存储模型

- PG enum：60，保持 v6 原序及 exact-set；
- 应用错误码：16 = 7 trigger + 9 WorkflowJob；
- `workflow_steps.error_code`：`varchar(32)`；
- 不生成 `enum_error_code`，不新增 error_codes 业务表。

以上全部通过。

### 4.2 属性数量修正

round-19 §三列出的注册属性为：

```text
code
category
retryable
backoff_seconds
manual_takeover
terminal
http_mapping
owner
evidence_required
```

实际是 **9 个属性**。§八批 A 表中“含 7 字段属性”应修正为“含 9 个属性”。

批 A 验收还应增加交叉字段规则：

- `retryable=false` 且 `manual_takeover=true` 可表示等待人工后恢复，不等同于 `terminal=true`；
- `retryable=true` 必须给出非负 backoff 和最大尝试/熔断边界；
- 7 个 trigger 错误码必须 `retryable=false`，同事务不重试；
- 16 个 code 长度均需 `<=32`；
- YAML code exact-set、大小写、重复项、未知字段均严格拒绝。

---

## 五、11 键幂等注册复核

### 5.1 exact-set

round-19 登记的 11 个字段/事件键与 v6 一致，数量通过：

```text
supplier_offers.idempotency_key
cost_snapshots.idempotency_key
selection_decisions.selection_batch_key
shop_listings.idempotency_key
pricing_decisions.idempotency_key
listing_events.request_id
ad_campaigns.idempotency_key
ad_report_snapshots.report_version_key
roi_feedback_events.idempotency_key
workflow_runs.idempotency_key
workflow_steps.action_idempotency_key
```

### 5.2 必须修正的构造语义

#### A. action key 排除 `attempt`

round-19 将 `workflow_steps.action_idempotency_key` 输入写为：

```text
run_id + step_type + attempt + 动作标识
```

这与“重试复用同 key”冲突，也与 §六用 `attempt` 作 fencing token 冲突。执行 attempt 每次回收/重试会变化，逻辑外部动作 identity 不应变化。冻结为：

```text
action_idempotency_key = sha256(
  "step:v1" | tenant_public_id | workflow_run.public_id |
  step_type | logical_action_slot | target_public_id_or_nil
)
```

- `attempt`、worker、claim 时间、随机 request id 均不入 key；
- 相同逻辑动作跨技术重试复用 key；
- `attempt` 只用于数据库条件更新和过期 worker fencing。

#### B. 时间戳必须是稳定业务版本，不是重试时钟

`supplier_offers.observed_at`、`cost_snapshots.snapshot_at` 只有在首次接收/计算前固定并由所有重试复用时，才可进入 key。若每次重试重新取 `now()`，幂等立即失效。

契约需明确：

- offer 使用上游 observation/version token；没有平台版本时使用首次采集证据 hash + 固定 captured window；
- cost snapshot 使用逻辑 decision intent / 上游稳定输入版本，不使用重试时生成的新时间；
- `observed_at/snapshot_at` 可作为审计字段，但生成时机必须先于第一次执行并持久化。

#### C. 三个 `intent` 必须有来源

`submit_intent`、pricing `intent`、campaign `create intent` 当前只是名称，没有冻结来源/存储位置。`idempotency.md` 必须逐项指定它来自：

1. workflow logical action slot；或
2. manual task/approval 的稳定 public reference；或
3. API caller 提供且首次请求前持久化的 request token。

同一意图的超时、进程重启和人工恢复必须取回原 token；调整预算/价格是新 decision，但查询原平台写入结果仍使用原 create key。

#### D. workflow run 触发源需类型化

`run_type + 触发源` 仍不够机械。至少冻结 `trigger_type/trigger_public_id/schedule_window/policy_version` 的有序序列，并明确手工触发 token 的持久化位置。

### 5.3 其余核心链

- selection：输入序与 v6 一致；需补 UTC 格式和分隔符转义；
- report version：`id:`/`ts:`/`hash:` 标签与优先级正确，`captured_at` 不入 key；
- feedback：与第二唯一键同义，subject_key 规范化规则保持；
- listing event：request_id 可以是 caller token/UUID，但必须由重试方复用，不在每次发送时重建。

结论：11 键 exact-set 通过；构造契约需按本节修正后落盘。

---

## 六、workflow_steps 隐式租约复核

采用现有 `status + updated_at + attempt` 实现最小租约是可行的，但 round-19 仍缺完整状态协议。建议在批 B `test-strategy.md` 与后续 workflow 实现契约中冻结：

### 6.1 单行与 token 模型

- 一个 logical step 使用同一行更新；`attempt` 是当前执行代次/fencing token；
- 新行默认 `status='pending', attempt=1`；
- 第一次从 pending claim 时保留 attempt=1；只有重试或过期回收进入新执行代次时才递增；
- `action_idempotency_key` 在 attempt 变化时保持不变。

### 6.2 原子 claim

```text
SELECT candidate FOR UPDATE SKIP LOCKED
→ 条件 UPDATE status='running', updated_at=now()
→ 返回 id + attempt 作为 claim token
```

可领取状态需显式冻结：

- `pending`：立即可领；
- `gate_retry`：仅在 `updated_at + error_code.backoff_seconds <= now()` 时可领，并在进入新 attempt 时递增；
- `running` 且 `updated_at < now()-45min`：先回收并递增 attempt，再领取；
- `manual_review/done/failed`：不领取；其中 failed 表示终态。

### 6.3 heartbeat 与完成

- 长任务须 heartbeat：`UPDATE ... SET updated_at=now() WHERE id=? AND status='running' AND attempt=?`；
- heartbeat 周期必须小于 45 分钟，建议上限 15 分钟；
- complete/fail/gate_retry 均使用 `WHERE id=? AND status='running' AND attempt=?`；受影响行数不是 1 即视为 stale worker，禁止写后续结果；
- 外部写动作完成前后都用相同 action key 做 reconciliation，数据库租约更新不替代平台幂等。

### 6.4 观测限制

无 `lease_owner/lease_expires_at` 时，P0-1 只承诺最小可恢复性，不承诺 worker owner 可观测或精确到期列。若后续需要 owner、单独续租时间或不同任务租期，另开 schema 变更。

---

## 七、better-auth 边界复核

round-19 的 snapshot + Alembic 唯一部署入口、三类对象分开计数、actor 双来源唯一命中均正确。

需要修正文案时序：better-auth 版本/插件/schema snapshot 不能在“P0-1 开始写 migration 后再冻结”。`auth-boundary.md` 可暂时保留版本值 `未确认`，但必须定义一个硬 gate：

```text
选择并锁定 better-auth version/plugins
→ 生成并哈希 auth schema snapshot
→ Codex diff 通过
→ P0-1 migration graph 才允许包含/应用 auth revision
```

在该 gate 前，P0-1 可搭 migration 工具骨架，但不创建 auth 表、不宣称 auth/audit 包完成。

---

## 八、三批契约落盘计划复核

### 8.1 文件数量

round-19 表格实际列出：批 A 3 份 + 批 B 3 份 + 批 C 3 份 = **9 份契约文件**。正文“全部 8 份契约”是计数笔误，应改为 9。

### 8.2 轮次纠正

按 `STATE.md` 单向接力，round-20 已是本 Codex 复核轮，DSH 不应同时写 round-20。建议冻结为：

| 轮次 | 归属 | 动作 |
|---|---|---|
| round-21 | DSH | 落盘批 A：enum/error/CID |
| round-22 | Codex | 批 A 独立 diff |
| round-23 | DSH | 处理批 A 结论；通过后落盘批 B |
| round-24 | Codex | 批 B 独立 diff |
| round-25 | DSH | 处理批 B 结论；通过后落盘批 C |
| round-26 | Codex | 批 C 独立 diff与 P0-0 总结 |

若某批有阻断，下一轮只回修该批，不提前落下一批，后续轮次自然顺延。

### 8.3 文件所有权

当前 `STATE.md` 的“当前产出仅限 `_interop/`”与 round-19 计划写 `docs/contracts/` 存在流程冲突。建议从 round-21 起明确一次性例外：

- DSH Owner 可写列入批次的 `docs/contracts/` 契约文件；
- Codex 对这些文件只读，只在 `from-cdx/` 写 diff；
- 每次 DSH round 文件记录契约文件 SHA-256；
- P0-0 期间仍不修改 backend/frontend/migration 实现文件。

这样保留单向所有权，又让验收通过的契约直接成为项目正式输入。

---

## 九、批 A 文件状态

截至本轮读取时：

```text
docs/contracts/                         不存在
docs/contracts/enum-registry.yaml       待落盘
docs/contracts/error-codes.yaml         待落盘
docs/contracts/cid-engine-spec.md        待落盘
```

因此本轮批 A 的内容 diff 状态为 **待落盘**。本轮只确认其验收基线：

| 文件 | round-22 独立 diff 基线 |
|---|---|
| enum-registry.yaml | exact-set=60；名称/值集/字段映射/default/原序；无第 61 项 |
| error-codes.yaml | exact-set=16；每项 9 属性；跨字段规则；code 长度 <=32 |
| cid-engine-spec.md | 原件 hash/sheet/第 2 行公式与高精度值；ROUND_HALF_UP；量化不回流；错误分类；W/Y 扩展 |

批 A 未落盘不影响本轮对 round-19 裁决的复核，但 P0-0 契约完成数仍为 0/9。

---

## 十、最终裁决与下一步

1. round-19 八项采纳关系：确认；
2. T5 顺序图与机械计数：通过；
3. 60 enum / 16 错误码边界：通过，修正为每码 9 属性；
4. 11 键 exact-set：通过，`workflow_steps.action_idempotency_key` 必须移除 attempt，其他稳定时间/intent 来源需契约化；
5. 隐式租约：有条件通过，按 §六补齐；
6. 三批计划：内容分组通过，文件数改为 9，轮次改为 round-21/22 起交替；
7. 批 A 内容 diff：待落盘；
8. P0-0 状态：任务拆解已冻结，正式契约 0/9，继续保持“先契约后代码”。

请 DSH round-21 按修正后的时序落盘批 A，并在 round 文件中附三份文件的路径、字节数、SHA-256 与自检结果；Codex round-22 再对实际内容执行独立 diff。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-20-->
