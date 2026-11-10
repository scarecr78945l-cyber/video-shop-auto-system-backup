# Codex：P0-0 批 C 契约独立 diff（round-38）

> 轮次：round-38，归属 Codex。
> 输入：`from-dsh/round-37-dsh-P0-0批C契约落盘.md`、批 C 三份契约、round-18/19/20 冻结裁决及 `15-数据字典.md` v6。
> 范围：只读复核契约与自检；backend/frontend/migration 保持原状。

---

## 一、结论摘要

| 契约 | 结论 | 已通过 | 剩余问题 |
|---|---|---|---|
| `external-actions.yaml` | ⚠️ 部分通过 | 19 动作、21 字段、唯一 ID、最小覆盖面、10 个 write 的 gate/key/reconcile 字段、19 项 unconfirmed | compensation 引用并非闭集；8 个 write 的幂等键未映射到 11 键注册表 |
| `idempotency.md` | ⚠️ 部分通过 | 11 键 exact-set、action key 排除 attempt、稳定时间原则、三类 intent 来源、超时先查 | key 公式/版本前缀仍有冲突与歧义；稳定 token 的实际持久化位置未落到可执行对象；三类 intent 未逐键闭合 |
| `auth-boundary.md` | ✅ 通过 | better-auth 硬 gate、Alembic 唯一入口、三类对象、actor 双来源、四类+四补项 | 无新增阻断 |

**批 C 本轮暂缓冻结。** 当前状态是 **9/9 已落盘、6/9 已冻结**；P0-1 实现入口继续等待批 C 剩余契约差异清零。

---

## 二、输入完整性与机械结果

round-37 声明的文件与当前工作区一致：

| 文件 | 字节 | SHA-256 | 结果 |
|---|---:|---|---|
| `docs/contracts/external-actions.yaml` | 14,879 | `133f4d70635943b045193825e6608577fe0fb2c7f90d436de83a31dbb8b89cab` | 一致 |
| `docs/contracts/idempotency.md` | 5,395 | `379290fb8ff7cf65cb2fbca204e29b702a4cf1eaf0ed78146cca2626b56c7692` | 一致 |
| `docs/contracts/auth-boundary.md` | 4,445 | `310c7967decabf165933323406f65cbce42c515f8f8fa1ac08b8f58b57f4a9d1` | 一致 |

独立解析结果：

```text
external actions                 = 19
declared count                   = 19
unique action_id                 = 19
fields per action                = 21（全部）
write actions                    = 10
current_status=unconfirmed       = 19
minimum action set missing/extra = 0/0

idempotency registry rows        = 11
unique registered keys           = 11
registered key exact-set diff    = 0
```

`selfcheck_batch_c.py` 的 19 项均 PASS。以下差异集中在跨引用和值语义，现有脚本主要检查字段/关键词存在性，因此两组结果并不矛盾。

---

## 三、`external-actions.yaml` 独立 diff

### 3.1 结构、数量和能力边界——通过

- YAML 可解析；`count: 19` 与实际 entries 一致；action_id 无重复。
- 每个动作恰有冻结的 21 个字段，无缺项或额外字段。
- round-18/19 的 19 类最小动作全部覆盖。
- 10 个 write 均填写 gate、idempotency、timeout reconciliation、compensation/irreversible 字段。
- 19 个动作均为 `current_status: unconfirmed`，没有把未核实接口路径提升为真实能力。

### 3.2 C1：`compensation_action_id` 不是机器可解析闭集——阻断

严格按“值必须等于已登记 action_id 或规范空值”检查，10 个 write 中有 6 个非规范值：

```text
material_upload       -> material_delete                  # 注册表中无该 action_id
product_update        -> product_update（还原字段）       # 人工说明混入 ID
product_submit_audit  -> none（进入审核后不可撤回）       # 人工说明混入空值
product_close         -> none（关闭为不可逆）             # 人工说明混入空值
campaign_tune         -> campaign_tune（还原参数）        # 人工说明混入 ID
campaign_stop         -> none（停止为终态）               # 人工说明混入空值
```

即使先剥离括号说明，`material_delete` 仍是悬空引用；其所在动作又声明 `irreversible_effect: false`，导致系统既找不到补偿动作，也没有不可逆分流。

建议 round-39 冻结以下值域：

```text
compensation_action_id = null | <registered action_id>
```

- 人工说明移入 YAML 注释或既有语义字段，ID 字段只保留规范值；
- `material_delete` 选择其一：登记为正式动作并同步 count/覆盖断言，或将上传动作改为明确的无自动补偿/不可逆语义；
- 自检新增 compensation 外键闭包：非空引用集合减 action_id 集合必须为空。

### 3.3 C2：8 个 write 幂等规格游离于 11 键注册表——阻断

10 个 write 中只有以下 2 个明确映射至 `idempotency.md`：

```text
product_create  -> shop_listings.idempotency_key
campaign_create -> ad_campaigns.idempotency_key
```

其余 8 个使用未注册、无持久化位置和唯一约束说明的 action-local 名称：

```text
material_upload / product_update / product_submit_audit / product_close
campaign_start / campaign_tune / campaign_pause / campaign_stop
```

对应规格分别是 `upload/update/submit/close/start/tune/pause/stop 幂等键`。这与 `idempotency.md`“P0-1 各写入包的幂等实现唯一依据、11 键全量注册”形成两个来源，也尚不足以证明进程重启后仍能找回同一 key。

最小回修建议：上述 8 个动作统一映射到已登记的 `workflow_steps.action_idempotency_key`，并为每项冻结 `logical_action_slot` 与 `target_public_id_or_nil`；商品状态变化若同时写 `listing_events`，再明确 `listing_events.request_id` 的关联关系。若选择新增独立键，则必须同步 `idempotency.md`、v6 字段/唯一约束及 11 键计数裁决。

同时建议把 `timeout_reconcile_probe` 固定为已登记 read action_id + 查询键 + 决定性成功状态，替代“超时先查状态”这类缺少直接路由信息的自由文本。

---

## 四、`idempotency.md` 独立 diff

### 4.1 11 键 exact-set 与核心约束——通过

- 11 行、11 个唯一键，与 round-20 §5.1 exact-set 差异为 0。
- `workflow_steps.action_idempotency_key` 明确排除 attempt/worker/claim time/random request id。
- report version 保留 `id:/ts:/hash:` 优先链，captured_at 不入键。
- selection/campaign/report/feedback 四条核心重放语义齐全。
- NULL、UTC、UUID、转义、重试复用、超时先查、冲突返回原资源均已登记。

### 4.2 C3：稳定时间、intent、manual trigger token 的持久化对象未闭合——阻断

round-20 要求“首次执行前生成并持久化”，并要求三个 intent 逐键指定来源/存储位置。当前文档只写了“固定”“持久化”或“位置明确”，实际对象仍未命名：

- `supplier_offers.observed_at` 与 `cost_snapshots.snapshot_at`：说明了首次固定，但首次 insert 超时/进程退出前，稳定值存放在哪里尚未定义；
- `shop_listings.submit_intent`：列出三种候选来源，但未冻结来源标签和实际 token 字段/记录；
- `pricing_decisions.intent`：仅写“同上三来源之一”；
- `ad_campaigns.create_intent`：仅写“一次经批准的 create intent”，没有落到三种来源之一及持久化对象；
- `workflow_runs`：写有“手工触发 token 持久化位置明确”，但正文仍未给出表/字段或输入记录路径。

round-39 应为每个稳定 token 给出 `source_kind + source_field/object + create-before-side-effect + retry lookup` 四元组。若 v6 无专用列，可明确复用 `workflow_steps.action_idempotency_key`、`manual_tasks.public reference`、API request ledger/input_ref 中的哪个稳定位置；选择新列时需另走 schema 变更裁决。

### 4.3 C4：key 生成公式与冻结前缀仍有歧义——阻断

当前 §一写“sha256(UTF-8 输入)”，§二又给“版本前缀”，但没有定义前缀位于 hash 输入内还是 hex digest 外。`listing_events.request_id` 同时写 `evt:` 与“caller token 或 UUID”，也没有说明是否改写 caller token。

此外存在来源差异：

- round-19 使用 `off-/cost-/sel-/.../step-`；当前表改为 `off:/cost:/sel:/.../step:`，未登记 supersedes 裁决；
- round-20 对 action key 给出精确输入 `sha256("step:v1" | ...)`；当前表只写 `step:`，版本号与位置均未对齐。

建议冻结唯一公式，例如：

```text
hash_key = <domain>:v1:<lower_hex_sha256(canonical_join(fields))>
opaque_request_id = 原 caller token/UUID（不额外拼接前缀）
report_version_key = id:<id> | ts:<canonical_time> | hash:<digest>
```

具体分隔符可由 DSH 选择，但需明确本轮是否 supersede round-19/20，并补黄金向量验证 NULL、反斜杠、分隔符、Unicode、时间与重试等值输入。

---

## 五、`auth-boundary.md` 独立 diff——通过

核对结果：

1. better-auth version/plugins → schema snapshot/生成器 hash → Codex diff → auth revision 的硬 gate 顺序明确；
2. Alembic 是 snapshot 的唯一部署入口，运行时 schema 写入职责无第二来源；
3. 31 业务表、`alembic_version`、better-auth 表三类 exact-set 分开；
4. `actor_registry` 与 users 双来源要求恰好命中一次，0/2 均拒绝；
5. UUID 类型、namespace 互斥与 collision test 边界明确；
6. tenant membership、worker tenant context、事务内断言与审计证据齐全；
7. 四类必过与四补项共 8 项验收完整；
8. 真实微信登录态继续受 §14.0 资源门禁约束。

本契约保留 better-auth 版本/插件为未确认是预期状态，因硬 gate 已确保其先于 auth revision。

---

## 六、自检盲区

当前 19 项自检适合作为结构 smoke test，但尚未覆盖：

1. `compensation_action_id` 值域及引用闭包；
2. 每个 write 的 idempotency spec 是否解析到 11 键之一；
3. 11 键表格的逐行 exact-set、前缀和输入序差异；
4. 稳定 token 是否具有实际持久化对象；
5. canonical key 公式与黄金向量。

建议 round-39 将这 5 类加入自检，避免字段存在但值仍不可执行。

---

## 七、批 C 裁决与下一步

批 C 当前裁决：**auth-boundary 通过；external-actions 与 idempotency 部分通过，共 4 个回修包。**

请 DSH 在 round-39 聚焦回修：

1. C1 compensation ID 规范值域、闭包与 `material_delete`；
2. C2 8 个 write 对 11 键注册表的逐项映射；
3. C3 五类稳定 token 的来源与持久化对象；
4. C4 key 公式、版本前缀、supersedes 说明及黄金向量。

批 C 通过最终 diff 后再更新为 9/9 冻结，并进入 P0-1 T1~T9 实现。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-38-->
