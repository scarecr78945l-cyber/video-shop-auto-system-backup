# idempotency.md — P0-0 批 C 契约：幂等键注册表

> 来源：round-19 §四（11 键全量注册）+ round-20 §五（action key 排除 attempt、稳定时间/intent）+ round-38 §4（C3/C4 回修）。
> 用途：P0-1 各写入包（T1~T9）的幂等实现唯一依据。

---

## 一、唯一 key 公式与版本前缀（round-39 C4 冻结）

```text
hash_key = <domain>:v1:<lower_hex_sha256(canonical_join(fields))>
```

- **`<domain>`**：本表各键的短前缀（`off`/`cost`/`sel`/`lst`/`prc`/`cmp`/`fb`/`run`/`step`）；`listing_events.request_id` 与 `report_version_key` 见下。
- **`v1`**：公式版本标记，**位于 hash 输入之外、hex digest 之前**（即前缀 `off:v1:`、`step:v1:`）。
- **canonical_join(fields)**：字段按注册表顺序，UTF-8，用 `|` 连接；字段值内 `|`→`\|`、`\`→`\\`；NULL→`nil`；时间用 UTC ISO-8601；UUID 小写。
- **supersedes（round-39 登记）**：round-19 曾用 `off-`/`cost-` 等连字符前缀；**本轮统一为 `<domain>:v1:` 冒号形式，supersede 旧连字符写法**。P0-1 实现只认冒号 v1 形式。

**特殊键（round-39 C4 明确）**：
```text
listing_events.request_id = 原 caller token/UUID（不额外拼接前缀，不改写 caller token）
report_version_key       = id:<platform_version_id> | ts:<canonical_time> | hash:<raw_evidence_hash>（三源优先级）
```

**canonical_join 算法与转义/Unicode 规则（round-41 冻结，跨实现必须一致）**：
```text
1. 字段转 str；None → "nil"
2. 转义顺序固定：先 replace("\\","\\\\")（反斜杠），再 replace("|","\\|")（竖线）   ← 顺序不可调换
3. 字段以 "|" 连接（join 分隔符与字段内转义竖线区分）
4. Unicode：输入先按 NFC 归一化，再 UTF-8 编码
5. sha256 → hex 小写
6. final = f"{domain}:v1:{digest}"
```

**黄金向量（round-41 升级：含输入 fields / canonical bytes / expected digest / final key，P0-1 自检必须现场复算等值）**：

```text
V1 普通 step key（domain=step）
  输入 fields（顺序）:
    00000000-0000-0000-0000-000000000001, 00000000-0000-0000-0000-000000000002,
    listing_submit, product_submit_audit, 00000000-0000-0000-0000-000000000003
  canonical UTF-8 文本（repr）:
    '00000000-0000-0000-0000-000000000001|00000000-0000-0000-0000-000000000002|listing_submit|product_submit_audit|00000000-0000-0000-0000-000000000003'
  sha256 hex: 5e47863b2530cda2957f894411abb214bbbf811e9c8ff42f274185c31954d614
  final key : step:v1:5e47863b2530cda2957f894411abb214bbbf811e9c8ff42f274185c31954d614

V2 NULL 字段（domain=step）
  输入 fields（顺序）:
    00000000-0000-0000-0000-000000000001, 00000000-0000-0000-0000-000000000002,
    campaign_start, campaign_start, None
  canonical UTF-8 文本（repr）:
    '00000000-0000-0000-0000-000000000001|00000000-0000-0000-0000-000000000002|campaign_start|campaign_start|nil'
  sha256 hex: 147949e3b728782d8bf9f784cb88d4228313458f1c0246d6e37c3f1967547deb
  final key : step:v1:147949e3b728782d8bf9f784cb88d4228313458f1c0246d6e37c3f1967547deb

V3 转义+Unicode（domain=step）
  输入 fields（顺序）:
    00000000-0000-0000-0000-000000000001, 00000000-0000-0000-0000-000000000002,
    material_upload, material_upload, "a|b\c中"（实际字符串：竖线、反斜杠、Unicode）
  canonical UTF-8 文本（repr）:
    '00000000-0000-0000-0000-000000000001|00000000-0000-0000-0000-000000000002|material_upload|material_upload|a\|b\\c中'
  sha256 hex: 8fc40e4a65af1c77e59838cd2b04232b3165f404cd87f84c032f05ac17525245
  final key : step:v1:8fc40e4a65af1c77e59838cd2b04232b3165f404cd87f84c032f05ac17525245
```

> 复算命令：`python _experiment/_interop/evidence/golden_vectors.py`（与自检脚本同算法）。V3 第 5 字段输入为 `a|b\c中`（一个竖线、一个反斜杠、一个中文字），转义顺序=先反斜杠后竖线，Unicode NFC 归一后 UTF-8。

---

## 二、通用规则（全部键适用）

- **哈希**：`sha256`（UTF-8 输入），hex 小写。
- **NULL**：`"nil"`，不省略。
- **时间**：UTC ISO-8601；仅使用**首次执行前固定的稳定版本时间**，重试不得重新取 `now()`。
- **UUID**：小写规范形式。
- **重试复用**：同一逻辑动作跨技术重试必须复用同一 key。
- **超时先查**：平台写入超时后，先按本地 key + 平台证据查询已有结果，**不换 key 重建**。
- **冲突返回原资源**：key 已存在时返回原写入结果/资源，不静默覆盖。

---

## 三、11 键全量注册

| # | 键 | domain | 输入字段（canonical_join 顺序） | 稳定 token 持久化（round-39 C3 四元组） |
|---|---|---|---|---|
| 1 | `supplier_offers.idempotency_key` | `off` | tenant_public_id, supplier_id, offer_id, observed_at(首次固定) | source=上游 observation/version token；object=`supplier_offers.observed_at`（首次采集前写入）；create-before-side-effect=采集行先落库；retry=按 `off:v1:` key 查已入库 offer |
| 2 | `cost_snapshots.idempotency_key` | `cost` | tenant_public_id, decision_object_type, decision_object_id, policy_version_id, snapshot_at(首次固定) | source=逻辑 decision intent；object=`cost_snapshots.snapshot_at`（首次计算前写入）；create-before-side-effect=决策行先落库；retry=按 `cost:v1:` key 查快照 |
| 3 | `selection_decisions.selection_batch_key` | `sel` | source, source_account_id, scan_window_start, scan_window_end, policy_version_id, batch_round | source=批次参数；object=`selection_decisions.selection_batch_key` 列本身（批次发起时生成）；create-before-side-effect=批次键先于候选落库；retry=同批次重放复用 |
| 4 | `shop_listings.idempotency_key` | `lst` | tenant_public_id, shop_id, product_id, submit_intent | source_kind=workflow logical action slot；object=`workflow_steps.action_idempotency_key`（slot=`listing_submit`，target=shop_listing 候选 public_id）；create-before-side-effect=workflow_step 先于平台创建；retry=按 slot 对应 step key 查回 |
| 5 | `pricing_decisions.idempotency_key` | `prc` | tenant_public_id, shop_listing_sku_id, policy_version_id, decision_type, intent | source_kind=workflow logical action slot 或 manual approval internal ref；object=`workflow_steps.action_idempotency_key`（slot=`pricing_apply`）或 `manual_tasks.id`（审批行内部引用，round-41 修正：v6 manual_tasks 无 public_id 列）；create-before-side-effect=step/manual 先落库；retry=按原 key 查回 intent |
| 6 | `listing_events.request_id` | （原样） | caller token 或 UUID（不拼接前缀） | source=API caller；object=`listing_events.request_id` 列（请求进入时写入）；create-before-side-effect=事件行先于平台调用；retry=重试方复用同一 request_id |
| 7 | `ad_campaigns.idempotency_key` | `cmp` | tenant_public_id, shop_listing_id, create_intent | source_kind=manual approval internal ref；object=`manual_tasks.id`（`ads_confirm` 审批行，round-41 修正：v6 无 public_id，用 id 作内部稳定引用）；create-before-side-effect=审批行先于 campaign 创建；retry=按审批 ref + 平台证据查已有 campaign；**不含可变 budget/ROI** |
| 8 | `ad_report_snapshots.report_version_key` | `id:/ts:/hash:` | 平台版本 ID → normalized platform_updated_at → raw_evidence_hash | source=平台版本；object=`ad_report_snapshots.report_version_key` 列（canonical 生成）；create-before-side-effect=抓取前生成；retry=重复抓取复用；**captured_at 永不入版本键** |
| 9 | `roi_feedback_events.idempotency_key` | `fb` | source_snapshot_id, feedback_type, subject_type, subject_key(规范化), aggregation_version | source=回写事件；object=`roi_feedback_events.idempotency_key` 列；create-before-side-effect=回写前生成；retry=与第二唯一键同义复用 |
| 10 | `workflow_runs.idempotency_key` | `run` | trigger_type, trigger_public_id, schedule_window, policy_version_id | source=触发源；object=`workflow_runs.idempotency_key` 列（触发时生成）；create-before-side-effect=run 行先落库；retry=手工触发 token 持久化于 `workflow_runs.input_ref`（round-39 C3：明确落点） |
| 11 | `workflow_steps.action_idempotency_key` | `step` | tenant_public_id, workflow_run.public_id, step_type, logical_action_slot, target_public_id_or_nil | source=动作身份；object=`workflow_steps.action_idempotency_key` 列（step 创建时生成）；create-before-side-effect=step 先于外部副作用；retry=按 step key 查回；**不含 attempt/worker/claim 时间/随机 request id** |

---

## 四、稳定 token 持久化四元组（round-39 C3，通用模板）

每个稳定 token（首次时间 / submit_intent / pricing intent / campaign create_intent / 手工触发 token）必须落为：

```text
source_kind              = workflow logical action slot | manual approval internal ref | API caller token | 上游 observation/version token
source_object            = 具体表.字段（workflow_steps.action_idempotency_key / manual_tasks.id / listing_events.request_id /
                           workflow_runs.input_ref / 数据行首字段）
create_before_side_effect = 该 token 所在行必须先于平台外部副作用落库
retry_lookup             = 按对应 key 列查回原 token，不重建
```

- 五类稳定 token 的具体落点已在 §三表「稳定 token 持久化」列逐键指定；
- v6 无需新增专用列：统一复用 `workflow_steps.action_idempotency_key`、`manual_tasks.id`（round-41 修正：v6 manual_tasks 无 public_id，用 id 作内部稳定引用）、`listing_events.request_id`、`workflow_runs.input_ref` 四个既有稳定位置；
- 若某键需要独立新列，须另走 schema 变更裁决（不经静默）。

---

## 五、四条核心链验收（round-20 §5.2，P0-1 测试基准）

- **selection**：同批次重放不新增（selection_batch_key，UTC/转义冻结）；
- **campaign**：创建前 `(tenant_id, idempotency_key)`、创建后平台 ID 部分唯一；重试/超时先查本地 key + 平台证据，不换 key 重建；
- **report**：重复抓取不新增、真实版本变化可新增（report_version_key canonical 三源，captured_at 不入键）；
- **feedback**：同 source_snapshot + feedback_type + subject_type + subject_key + aggregation_version 不重复回写（idempotency_key + 第二唯一键同义）。

---

## 六、变更规则

- 新增/调整键、前缀、输入序、哈希：须更新本表 + 对应 v6 字段 + P0-1 migration，并经 Codex diff；
- 前缀/公式变更须登记 supersedes（见 §一）；
- 禁止静默改 key 输入序/哈希/前缀（会破坏既有重试与审计一致性）。
