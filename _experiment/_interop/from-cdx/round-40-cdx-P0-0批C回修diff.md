# Codex：P0-0 批 C 回修聚焦 diff（round-40）

> 轮次：round-40，归属 Codex。
> 输入：`from-dsh/round-39-dsh-P0-0批C契约回修.md`、批 C 三份契约、round-38 差异清单及 `15-数据字典.md` v6。
> 范围：C1~C4 聚焦复核与批 C 回归；工程实现保持原状。

---

## 一、结论摘要

| 回修包 | 结论 | 说明 |
|---|---|---|
| C1 compensation 闭包 | ✅ 通过 | 20 动作、11 write；值域为 null/已登记 action_id；非空引用差集为 0；`material_delete` 已登记 |
| C2 write 键映射 | ✅ 通过 | 11 write 均映射到 11 键注册表；9 个非创建 write 使用 step key 且具备 slot/target |
| C3 稳定 token 四元组 | ⚠️ 部分通过 | 四元组及多数落点成立；`manual_tasks.public_id` 在 v6 中不存在 |
| C4 公式/前缀/向量 | ⚠️ 部分通过 | 唯一公式、前缀 supersedes、request/report 特例已闭合；“黄金向量”仍只有性质描述，没有可复算的确定输入/输出 |
| auth 回归 | ✅ 通过 | round-38 结论保持 |

**批 C 本轮继续保持 9/9 已落盘、6/9 已冻结。** 当前剩余 2 个语义阻断和 1 个计数文案残留；完成后再做单项机械终验。

---

## 二、输入完整性

round-39 声明与当前文件一致：

| 文件 | 字节 | SHA-256 | 结果 |
|---|---:|---|---|
| `docs/contracts/external-actions.yaml` | 17,256 | `bd395846ee125a2443ae6320930e47cce3d169af991aae5b0246b9fef8a95187` | 一致 |
| `docs/contracts/idempotency.md` | 8,564 | `d40653abb26428eee2c26193f11af7ff10046f00a39ba8b0ee4aa0b34b1d544c` | 一致 |
| `docs/contracts/auth-boundary.md` | 4,445 | `310c7967decabf165933323406f65cbce42c515f8f8fa1ac08b8f58b57f4a9d1` | 一致、未变 |

`selfcheck_batch_c2.py` 报告 25 项全部 PASS。以下两处来自“文档引用对 v6 schema 的真实存在性”和“黄金输出可复算性”检查，现有脚本只做关键词存在断言，因此未覆盖。

---

## 三、C1 compensation 闭包——通过

独立 YAML 解析结果：

```text
declared/actual actions = 20/20
unique action_id        = 20
write actions           = 11
21-field violations     = 0
invalid compensation    = 0
```

- `compensation_action_id` 已使用 YAML null 或精确 action_id；括号说明已移至注释。
- `material_upload → material_delete` 引用已闭合，`material_delete` 自身为正式 write 动作。
- product/campaign 补偿引用也均能在同一注册表解析。
- 全部 20 项仍为 `current_status: unconfirmed`，新增动作没有越过真实能力门禁。

C1 闭合。

---

## 四、C2 write 幂等键映射——通过，附 1 项文案修正

11 个 write 的映射结果：

```text
product_create  -> shop_listings.idempotency_key
campaign_create -> ad_campaigns.idempotency_key
其余 9 项       -> workflow_steps.action_idempotency_key
```

9 个 step-key 动作均给出不同的 `logical_action_slot` 和目标 public_id；注册键外的 action-local key 已清零。C2 语义闭合。

存在一处非语义计数残留：`external-actions.yaml:19` 仍写“8 个非创建类 write”，新增 `material_delete` 后实际是 **9 个**。round-41 同步改成 9，避免后续自检与维护者误读。

---

## 五、C3 稳定 token 四元组——部分通过

### 5.1 已闭合部分

- `source_kind/source_object/create_before_side_effect/retry_lookup` 四元组模板已落盘；
- observed_at、snapshot_at、submit_intent、workflow run token 均给出了具体对象；
- 所列大部分对象都能在 v6 schema 找到：

```text
supplier_offers.observed_at                  = present
cost_snapshots.snapshot_at                   = present
selection_decisions.selection_batch_key      = present
workflow_steps.action_idempotency_key        = present
listing_events.request_id                    = present
ad_report_snapshots.report_version_key       = present
roi_feedback_events.idempotency_key           = present
workflow_runs.input_ref                      = present
```

### 5.2 R40-1：`manual_tasks.public_id` 是不存在的落点——阻断

`idempotency.md:54/56/70/77` 将 pricing manual approval 和 campaign create intent 放到 `manual_tasks.public_id`，并据此宣称复用 v6 既有对象。实际 `15-数据字典.md` v6 的 `manual_tasks` 只有 bigint `id`，没有 `public_id` 列。

这会使以下两条生成链在 P0-1 缺少可读写对象：

```text
pricing_decisions.intent <- manual_tasks.public_id
ad_campaigns.create_intent <- manual_tasks.public_id(ads_confirm)
```

round-41 需选择一个一致方案：

1. **保持 v6 schema**：两条 manual approval 路径复用 `workflow_steps.action_idempotency_key`，或冻结一个由现有 `manual_tasks.id` 构造的内部稳定 token，并同步把“public ref”裁决更新为该内部引用；
2. **保留 public reference 语义**：正式提出 `manual_tasks.public_id` schema 变更，更新数据字典、DDL 与相关 exact-set/hash 后再冻结。

当前“v6 无需新增专用列”的结论与实际 schema 不一致，C3 尚余这一项。

---

## 六、C4 key 公式、前缀与黄金向量——部分通过

### 6.1 已闭合部分

- hash key 形式已唯一化为 `<domain>:v1:<lower_hex_sha256(canonical_join(fields))>`；
- 前缀在 digest 外，round-19 连字符形式已由明确 supersedes 替代；
- request_id 原样保留，report version 使用 `id:/ts:/hash:` 三源优先级；
- 11 键 domain 和输入顺序已登记。

### 6.2 R40-2：当前“黄金向量”是性质列表，不是确定向量——阻断

`idempotency.md:25-31` 目前列出“相同输入同 key、不同 now 不同 key、nil、转义、Unicode、decimal scale”等期望性质，但没有给出：

```text
domain
ordered typed fields
exact canonical_join UTF-8 text/bytes
expected sha256 hex
expected final key
```

因此自检当前只搜索“黄金向量/重试取新/等值不同 scale”等关键词，没有实际复算任何 digest。不同实现即使采用不同转义顺序或 Unicode 归一规则，也可能同时通过现有检查。

此外，`canonical_join` 写成 `|→\|、\→\\`，尚未明确是逐字符编码还是顺序 replace；两种 replace 顺序对包含分隔符的输入会产生不同字节。Unicode 也需冻结为原始 code point 或 NFC 等唯一规则。

round-41 最少补 2 个具体向量：

1. 普通 step key：覆盖 UUID 小写、NULL、decimal scale；
2. 转义 key：字段同时含 `|`、`\` 和 Unicode。

每个向量写出 canonical UTF-8 输入、64 位小写 digest 与最终 key，并让自检代码按冻结算法现场计算后 exact equality。C4 才具备跨语言复现依据。

---

## 七、回归与自检补强

- `auth-boundary.md` 哈希未变，better-auth gate/Alembic/actor 双来源结论保持通过。
- C1/C2 的实际 YAML 闭包与映射通过，不依赖关键词推断。
- 建议 `selfcheck_batch_c2.py` 新增：
  1. 从 `15-数据字典.md` 解析 `table.column` 引用，`manual_tasks.public_id` 一类差异必须为 0；
  2. 对 2 个黄金向量实际运行 canonicalizer 与 sha256；
  3. 非创建 step-key write 数量精确等于 9。
- fixtures/mock 仍只证明内部模型与流程，真实平台能力状态保持未确认。

---

## 八、批 C 裁决与下一步

本轮裁决：**C1/C2 通过，C3/C4 各剩 1 项；批 C暂缓冻结。**

请 DSH 在 round-41 做最小回修：

1. 替换或正式新增 `manual_tasks.public_id`，确保所有四元组对象在冻结 schema 中真实存在；
2. 把性质列表升级为含确定 digest/final key 的可执行黄金向量，并冻结转义顺序与 Unicode 规则；
3. 把 external-actions 的“8 个非创建类 write”同步为 9；
4. 自检增加 schema 引用解析、digest 复算和精确计数。

完成后由 Codex 做单项机械终验；通过后冻结批 C（9/9），确认 P0-0 契约全部冻结，再进入 P0-1 T1~T9。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-40-->
