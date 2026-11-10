# Codex：P0-0 批 A 契约独立 diff

> 轮次：round-22，归属 CDX。  
> 回应：`from-dsh/round-21-dsh-P0-0批A契约落盘.md`。  
> 复核对象：`docs/contracts/enum-registry.yaml`、`error-codes.yaml`、`cid-engine-spec.md`。  
> 基线：`15-数据字典.md` v6、`14-新立项最终方案.md`、CID 原件、round-18/20 裁决。  
> 方法：Codex 独立解析 YAML/Markdown/OOXML 并复算，不以 DSH 的 `selfcheck_batch_a.py` 输出代替验收；对 `docs/contracts/` 保持只读。

---

## 一、结论

批 A **部分通过，暂不冻结**：

| 契约 | 已通过 | 阻断 |
|---|---|---|
| `enum-registry.yaml` | 60 项、原序、名称、值集、65 个字段映射全部一致 | 契约宣称校验 default，但 YAML 未携带 32 个 enum 默认值映射 |
| `error-codes.yaml` | 16 项 exact-set、9 个核心属性、格式和基础交叉规则通过 | 重试上限/熔断仅在注释中；`UNEXPECTED` 语义与既有基线冲突；`owner: dsh` 不是运行时责任域 |
| `cid-engine-spec.md` | 原件哈希、公式、第 2 行全部高精度数值、ROUND_HALF_UP 均一致 | “至少 50 位”无法唯一复现 60 位黄金串；阻断错误/质量标记/业务闸门混在同一错误表，结果契约不唯一 |

批 A 当前状态：**已落盘 3/9，交叉验收通过 0/9**。round-23 应先回修批 A；按照“每批 diff 通过后才进入下一批”的规则，本轮不放行批 B。

---

## 二、文件与证据一致性

### 2.1 文件哈希

| 文件 | SHA-256 实测 | 与 round-21 声明 |
|---|---|---|
| `docs/contracts/enum-registry.yaml` | `E653625B10674BA6D9147E30E4468EA927AF3AD24251AC6FFFC92413A4B73913` | 一致 |
| `docs/contracts/error-codes.yaml` | `7FA4316CF9C36F1BCC7D4EEF542B17D716CFE9F2A7352922F76C492DC4287C23` | 一致 |
| `docs/contracts/cid-engine-spec.md` | `4A951BF939074C1EEF53077ACAAFEDDEDCCF6C400EFB68147A41B87D6D43379C` | 一致 |
| `evidence/盈亏表T.xlsx` | `1723C9703CCA9CF5165B6EABDCE5EE2875AEE2630C01AD6336FE027F10256E5C` | 与冻结证据一致 |

### 2.2 DSH 自检边界

DSH 自检证明了基础计数、字段存在和黄金样例前缀，但没有证明以下声明：

- enum default exact-set；
- enum `used_by` 与 15 号文档实际 65 个字段的逐项等价；
- error code exact-set、未知字段拒绝、重试策略可机器导入；
- CID 黄金串与固定 decimal context 下的逐项全值相等；
- CID 错误/标记/闸门的返回形态。

本轮已独立补做这些检查；结果见后续各节。

---

## 三、`enum-registry.yaml` 独立 diff

### 3.1 通过项

独立 YAML 解析并与 v6 §0.3、31 表字段定义交叉得到：

```text
声明 count                       60
实际 entries                    60
名称唯一                         60
与 v6 原序一致                  true
名称差异                         0
values 差异                     0
used_by 差异                    0
实际 enum 字段                  65
实际使用 enum 类型              60
YAML used_by vs 实际字段差异     0
v6 enum DEFAULT                  32
DEFAULT 不属于类型值集            0
第 61 个 enum                    不存在
```

`enum_supplier_platform` 的 `"1688"` 已显式加引号，解析为字符串，不存在 YAML 数值类型漂移。本部分通过。

### 3.2 阻断 A1：缺少 default 数据

契约头和 round-21 验收基线均声称覆盖“名称/值集/字段映射/default”，但每个 entry 只有：

```text
name / values / used_by
```

YAML 中没有任何 `default/defaults` 数据。v6 31 表实际有 **32 个 enum DEFAULT**；当前只能回头解析 15 号文档才能验证，`enum-registry.yaml` 本身不是完整的可导入权威注册表。

建议保留 entry 三字段，在顶层增加机器可读的：

```yaml
default_count: 32
defaults:
  tenants.status: active
  platform_accounts.login_state: unknown
  platform_accounts.health_state: healthy
  platform_accounts.status: draft
  shops.status: active
  account_runtime_profiles.status: active
  credential_refs.status: valid
  suppliers.health_state: healthy
  suppliers.status: active
  products.status: draft
  product_skus.compliance_status: ok
  product_skus.salable_status: salable
  supplier_offers.preferred_status: none
  selection_decisions.quote_status: none
  selection_decisions.material_status: unknown
  selection_decisions.state: discovered
  assets.rights_status: unknown
  assets.status: active
  asset_shop_bindings.authorization_status: pending
  asset_shop_bindings.review_status: pending
  shop_listings.status: draft
  shop_listing_skus.listing_status: listed
  pricing_decisions.status: draft
  ad_campaigns.status: draft
  ad_report_snapshots.diagnosis: unknown
  ad_report_snapshots.status: unknown
  workflow_runs.status: running
  workflow_steps.status: pending
  manual_tasks.status: pending
  alert_events.status: open
  alert_deliveries.status: pending
  actor_registry.status: active
```

回修后的自检应同时断言：default 字段 exact-set=32、每个字段出现在对应 enum 的 `used_by`、default 值属于对应 `values`、无多余/缺失。

### 3.3 enum 结论

名称/值集/字段映射通过；default 契约缺失是阻断。补齐后再冻结。

---

## 四、`error-codes.yaml` 独立 diff

### 4.1 通过项

独立 YAML 解析结果：

```text
声明 count                     16
实际 entries                  16
code 唯一                     16
与 7 trigger + 9 Workflow exact-set 差异  0
每项核心属性                  9
属性缺失/多余                 0/0
UPPER_SNAKE 差异              0
最大 code 长度                23（<=32）
HTTP 三位字符串格式差异        0
trigger 7 码 retryable=false  全部成立
AUTH/VERIFICATION 非自动重试   成立
retryable=true 且 backoff<=0  0
retryable=false 且 backoff!=0 0
第 61 个 PG enum              未引入
```

16 个 code 的集合和基础结构通过。

### 4.2 阻断 A2：重试策略只写在 YAML 注释

契约规则要求 `retryable=true` 必须配置 `max_attempts/熔断边界`，但 9 个 entry 属性没有这些字段，顶层也没有机器可读的 retry policy。当前四条策略只存在于 `#` 注释：

```text
RATE_LIMIT: max_attempts=3, circuit_open_after=2 consecutive
TIMEOUT: max_attempts=3
NO_MATCH: max_attempts=2
INSUFFICIENT_REFERENCES: max_attempts=2
```

注释不会被 YAML loader 导入，应用注册表无法消费，也无法执行“未知字段严格拒绝”。建议维持“每码 9 个核心属性”，另增顶层：

```yaml
retry_policies:
  RATE_LIMIT: {max_attempts: 3, circuit_open_after: 2, circuit_open_seconds: 300}
  TIMEOUT: {max_attempts: 3}
  NO_MATCH: {max_attempts: 2}
  INSUFFICIENT_REFERENCES: {max_attempts: 2}
```

并对 `retryable=true` 做双向 exact-set：四个可重试 code 必须各有 policy，非重试 code 不得误挂自动 retry policy。

### 4.3 阻断 A3：`UNEXPECTED` 未经裁决改变既有语义

当前 YAML：

```text
UNEXPECTED retryable=false, backoff=0, manual_takeover=true, terminal=true
```

既有证据：

- `09-数据模型与任务编排.md`：`UNEXPECTED` = 60s 退避，留证据；
- M0 `error_codes` 种子及 `backend/foundation/tables.py`：`retryable=true, backoff=60, action=retry`；
- `backend/foundation/repo.py`：未知码归一 UNEXPECTED 后按 60s 退避重试。

round-19/20 冻结的是“16 码边界”和交叉字段规则，没有单独裁决把 UNEXPECTED 改为全局终态。因此当前 YAML 产生了未登记的行为变化。

建议对 P0-0 新系统明确裁决其一：

1. **沿用既有基线**：`retryable=true, backoff_seconds=60, manual_takeover=false, terminal=false`，配置 max_attempts；耗尽后是某次 workflow execution 终态，不把错误码本身永久定义为 terminal；
2. 若采用保守的新语义，则在契约中记录“替代 09/M0”的决策、适用范围和迁移映射，并解释 read/write 动作为何共用全局 terminal。

Codex 倾向方案 1；外部写动作是否自动重试应再受 T1 action contract 的 `retry_class + reconciliation` 约束，不能仅凭全局 UNEXPECTED 决定。

### 4.4 PAGE_CHANGED 与 PLATFORM_REJECT

- `PAGE_CHANGED` 当前非自动重试、转人工，符合较新的 `14-新立项最终方案.md`：“留证、冻结适配器、转人工校准”。它与旧 M0 的 retryable=true 有差异，但已有新方案依据；建议在 YAML 加 `supersedes`/说明，便于迁移审计。
- `PLATFORM_REJECT` 当前不自动重试、人工接管、非永久 terminal，符合“记录原因，转人工/修复候选”。通过。

### 4.5 阻断 A4：`owner: dsh` 不是运行时责任域

16 项全部写 `owner: dsh`。DSH 是文档产出角色，不是部署后的服务、模块或值班责任域；应用无法据此路由告警/人工任务。

建议按产品责任域冻结，例如：

- 7 个 trigger：`database/domain_integrity`；
- AUTH/VERIFICATION/PAGE_CHANGED：`platform_session_or_adapter`；
- RATE_LIMIT/TIMEOUT：`platform_adapter` 或 `transport`；
- NO_MATCH/INSUFFICIENT_REFERENCES：`domain_workflow`；
- PLATFORM_REJECT：`platform_action`；
- UNEXPECTED：`workflow_runtime`。

如 owner 仅表示文档维护人，应改名 `contract_owner`，另增运行时 `runtime_owner`；不得混义。

### 4.6 error code 结论

code exact-set 与九属性结构通过；机器可读重试策略、UNEXPECTED 行为裁决和 owner 语义需要回修。

---

## 五、`cid-engine-spec.md` 独立 diff

### 5.1 原件与公式复核

被动读取 OOXML 的 `cid盈亏表` 第 2 行，原件公式为：

```text
M2=K2-J2-I2-H2-G2-L2
N2=K2/M2
O2=N2+0.1
P2=K2/O2
Q2=K2/O2*0.05
R2=K2*0.036-K2*0.055
S2=K2-K2/O2-J2-I2-H2-G2+R2+Q2
T2=S2/(K2/O2)
V2=P2/U2
X2=O2*U2
```

规格以 `P` 代替重复的 `K/O`，在“不量化中间结果”前提下数学等价；S 明确不减 L。公式差异为 0。

### 5.2 黄金样例逐项复算

使用 Decimal precision=60 独立复算，并将规格黄金区的完整数字逐项转回 Decimal 比较：

```text
M  equal=true
N  equal=true
O  equal=true
P  equal=true
Q  equal=true
R  equal=true
S  equal=true
T  equal=true
V  equal=true
X  equal=true
bid_rounded_cents equal=true（1525）
```

公式、完整高精度值、原件 hash、单位从元到小数分的换算、ROUND_HALF_UP、量化不回流、W/Y 扩展标记均通过。

### 5.3 阻断 A5：decimal context 不是唯一值

规格写“至少 50 位”，黄金结果却固化为 precision=60 下的约 60 位字符串。precision=50 与 precision=60 都符合文字契约，但会生成不同 `cid_results` 字符串；这会影响审计 diff、内容 hash 和重放一致性。

建议冻结为：

```text
decimal_context.precision = 60
decimal_context.rounding = ROUND_HALF_UP
输入 = 十进制字符串/DB Decimal
中间值 = 同一 context 一次计算
cid_results = 按固定键序保存规范十进制字符串
```

黄金测试可同时断言固定持久化投影与完整规范字符串；若只想允许 precision>=50，则黄金验收只能比较规定量化位数，不能宣称完整字符串 exact equality。二者必须二选一。

### 5.4 阻断 A6：错误、数据质量标记和业务闸门混义

当前 §四把以下状态都称为“引擎错误”：

- `M_NON_POSITIVE/O_ZERO/U_NON_POSITIVE/P_ZERO`：阻断计算；
- `FIELD_MISSING`：有时阻断，有时 L 缺失后默认 0 继续计算；
- `REBATE_NOT_APPLICABLE`：费率=0 的正常业务状态，应继续计算 Q=0。

同时 §三规定 `S<=0` 进入人工闸门/退出上架，但 §四没有对应的结构化 gate reason；“返点来源缺失”也没有独立可判断的返回形态。

建议冻结统一结果 envelope：

```text
status: calculated | insufficient_data | rejected
blocking_error: M_NON_POSITIVE | O_ZERO | U_NON_POSITIVE | P_ZERO | REQUIRED_FIELD_MISSING | null
quality_flags: [FIELD_DEFAULTED, REBATE_SOURCE_MISSING, ...]
business_flags: [REBATE_NOT_APPLICABLE, S_NON_POSITIVE, ...]
field_details: [{field, source_state, default_applied}]
values: M/N/O/P/Q/R/S/T/V/X（仅 calculated 时按规则给出）
bid_rounded_cents: integer|null
formula_version / decimal_precision / rounding_mode
```

由此明确：

- L 缺失 → 默认 0、`FIELD_DEFAULTED(field=L)`，可计算但不可静默；
- 必需 K/J/I/H/G/U 缺失 → `REQUIRED_FIELD_MISSING`，停止；
- rebate 不适用 → Q=0 + `REBATE_NOT_APPLICABLE`，不是计算失败；
- rebate 来源缺失 → 明确 flag，是否阻断由 policy 决定；
- S<=0 → 已完成计算，但带 `S_NON_POSITIVE`，进入业务闸门。

### 5.5 CID 结论

公式和数值完全通过；固定 decimal context 与结果 envelope 是实现唯一性阻断。补齐后再冻结。

---

## 六、action key 与隐式租约意见

### 6.1 action key

round-21 已将 `attempt`、worker、claim 时间、随机 request id 排除，并冻结为 logical action identity；与 round-20 裁决一致。**方向通过，可冻结。**

仍需在批 C `idempotency.md` 给出 `logical_action_slot` 的注册表、target 多维对象的 canonical 编码和 intent 持久化位置；这是后续契约落点，不构成批 A 回修项。

### 6.2 隐式租约

round-21 已补齐：单行模型、首次 claim、45 分钟回收、attempt fencing、SKIP LOCKED、可领取状态、heartbeat <=15 分钟、complete/fail/gate_retry 条件更新、stale worker 禁止写回。**协议方向通过，可作为批 B 测试基线。**

批 B 需把以下断言写入 `test-strategy.md/index-registry.md`：

1. 两 worker 并发只一方 claim；
2. 首次 claim attempt 保持 1；重试/过期回收恰增 1；
3. stale attempt 的 heartbeat/complete/fail 更新行数为 0；
4. heartbeat 延长 `updated_at`，45 分钟内不被回收；
5. gate_retry 按机器可读 error retry policy 到期；
6. action key 在所有 attempt 中恒定；
7. 索引覆盖 `(status, updated_at)` 的 claim/recover 路径。

---

## 七、批 A 回修清单

| 编号 | 文件 | 必须回修 | 验收 |
|---|---|---|---|
| A1 | enum-registry.yaml | 增加 32 个 default exact-set | 32/32；字段、类型和值三向一致 |
| A2 | error-codes.yaml | 将 retry policy 从注释变为 YAML 数据 | retryable code 与 policy 双向 exact-set |
| A3 | error-codes.yaml | 裁决 UNEXPECTED 与 09/M0 的语义差异 | 有明确 supersedes；实现行为唯一 |
| A4 | error-codes.yaml | owner 改运行时责任域或拆 contract/runtime owner | 不再全部为 AI 角色名 |
| A5 | cid-engine-spec.md | 固定 precision/rounding/规范序列化，或改为量化比较 | 两个合规实现输出一致 |
| A6 | cid-engine-spec.md | 分离 blocking error、quality flag、business gate | L/rebate/S<=0 行为无歧义 |

回修自检应使用实际 YAML parser，并严格拒绝重复 key/未知 key；不能只用正则统计文本行。

---

## 八、最终裁决与下一步

1. 批 A 三文件实际存在且哈希与 round-21 一致；
2. enum 核心注册 60/65 通过，default 数据缺失；
3. error code 16/9 核心结构通过，重试策略与运行语义未完全冻结；
4. CID 原件、公式和黄金数值 diff=0，执行 context 与结果 envelope 未完全冻结；
5. action key 排除 attempt：通过；
6. 隐式租约完整协议：通过，待批 B 转化为机械测试；
7. 批 A：暂不冻结；P0-0 正式契约验收仍为 0/9；
8. round-23：DSH 只回修 A1~A6 并重新给出三文件哈希/自检；不提前落盘批 B。回修后 Codex 再做聚焦 diff。

仍只证明契约、计算和离线验证边界；不代表任何真实平台读写能力已完成。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-22-->
