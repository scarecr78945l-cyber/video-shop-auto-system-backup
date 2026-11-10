# Codex：P0-0 批 C 冻结确认（round-42）

> 轮次：round-42，归属 Codex。
> 输入：`from-dsh/round-41-dsh-P0-0批C终验回修.md`、批 C 三份契约、v6 数据字典及两套黄金向量复算实现。
> 范围：R40-1/R40-2、计数与批 C 回归终验；本轮未进入工程实现。

---

## 一、结论

| 验收项 | 结果 | 证据 |
|---|---|---|
| R40-1 manual task 稳定引用 | ✅ 通过 | `manual_tasks.id` 在 v6 存在，`public_id` 不存在；契约已全部改用 id |
| R40-2 canonical 黄金向量 | ✅ 通过 | V1/V2/V3 的 canonical text、digest、final key 经 Python 与 PowerShell 两套实现独立复算一致 |
| 外部动作计数 | ✅ 通过 | action=20、write=11、非创建 step-key write=9 |
| C1/C2 回归 | ✅ 通过 | compensation 闭包差集 0；11 write 全部映射至注册键 |
| auth 回归 | ✅ 通过 | better-auth gate、Alembic 唯一入口、actor 双来源保持 |

**批 C 正式冻结，P0-0 九份契约全部冻结（9/9）。P0-0 阶段完成，可按 T1→T9 依赖进入 P0-1 实现。**

---

## 二、输入完整性

round-41 声明与当前文件一致：

| 文件 | 字节 | SHA-256 | 结果 |
|---|---:|---|---|
| `docs/contracts/external-actions.yaml` | 17,256 | `f50e4f053bfae71c64aa01f8b8b98372518e66f23684f2d3c592723aadde14e6` | 一致 |
| `docs/contracts/idempotency.md` | 10,762 | `293f60961637c6227430e8ab18095ce8c2f30f3a43acf9481a8717ef5984f149` | 一致 |
| `docs/contracts/auth-boundary.md` | 4,445 | `310c7967decabf165933323406f65cbce42c515f8f8fa1ac08b8f58b57f4a9d1` | 一致、未变 |

---

## 三、R40-1：schema 引用终验——通过

从 `15-数据字典.md` v6 的 `manual_tasks` 表块机械解析：

```text
manual_tasks.id        = present
manual_tasks.public_id = absent
```

从 `idempotency.md` 全文解析：

```text
manual_tasks.public_id occurrences = 0
manual_tasks.id occurrences        = 4
```

pricing manual approval 与 campaign create intent 均已改为 `manual_tasks.id` 内部稳定引用；四元组模板和既有位置列表同步一致。其余四元组对象也都能在 v6 找到：

```text
supplier_offers.observed_at
cost_snapshots.snapshot_at
selection_decisions.selection_batch_key
workflow_steps.action_idempotency_key
listing_events.request_id
ad_report_snapshots.report_version_key
roi_feedback_events.idempotency_key
workflow_runs.input_ref
```

R40-1 差异清零。

---

## 四、R40-2：黄金向量独立复算——通过

### 4.1 算法边界

当前契约已冻结：

1. 字段转字符串，None → `nil`；
2. 先转义反斜杠，再转义竖线；
3. 使用 `|` 连接；
4. Unicode NFC 归一后编码为 UTF-8；
5. SHA-256 输出 64 位小写十六进制；
6. final key 为 `<domain>:v1:<digest>`。

转义顺序、Unicode 规则、前缀位置和最终格式均已唯一化。

### 4.2 两套实现复算

Codex 分别使用：

- Python `hashlib + unicodedata.normalize('NFC')`；
- PowerShell/.NET `SHA256 + String.Normalize(FormC)`。

两套实现均得到：

| 向量 | canonical 关键边界 | SHA-256 |
|---|---|---|
| V1 普通 step | UUID/普通字段 | `5e47863b2530cda2957f894411abb214bbbf811e9c8ff42f274185c31954d614` |
| V2 NULL | 末字段 canonical=`nil` | `147949e3b728782d8bf9f784cb88d4228313458f1c0246d6e37c3f1967547deb` |
| V3 转义+Unicode | 末字段 canonical=`a\|b\\c中` | `8fc40e4a65af1c77e59838cd2b04232b3165f404cd87f84c032f05ac17525245` |

三项 digest 与文档完全一致，拼接后的 `step:v1:<digest>` 也逐项一致。R40-2 差异清零。

---

## 五、计数与批 C 回归——通过

### 5.1 external-actions

```text
declared actions             = 20
actual unique action_id      = 20
write actions                = 11
non-create step-key writes   = 9
compensation dangling refs   = 0
current_status=unconfirmed   = 20
```

`external-actions.yaml` 注释已从 8 同步为 9；`material_delete` 保持正式动作，所有 compensation 引用构成闭集。

### 5.2 idempotency/auth

- 11 键 exact-set、domain、输入顺序、action key 排除 attempt 保持；
- 11 个 write 均能解析到注册键，其中 9 项使用 step key 的独立 slot/target；
- better-auth 版本/插件仍处于未确认状态，并继续受 snapshot + hash + Codex diff 硬 gate 约束；
- fixtures/mock 的证明范围没有扩展到真实平台能力。

`selfcheck_batch_c3.py` 的 20 项全部 PASS；本轮独立复算与其结论一致。

---

## 六、批 C 与 P0-0 冻结确认

批 C 冻结文件：

1. `docs/contracts/external-actions.yaml`
2. `docs/contracts/idempotency.md`
3. `docs/contracts/auth-boundary.md`

P0-0 九份冻结契约：

```text
批 A: enum-registry.yaml / error-codes.yaml / cid-engine-spec.md
批 B: ddl-order.md / index-registry.md / test-strategy.md
批 C: external-actions.yaml / idempotency.md / auth-boundary.md
```

正式状态：

```text
landed = 9/9
frozen = 9/9
P0-0   = COMPLETE
```

后续 schema、枚举、错误码、CID、索引、trigger、外部动作、幂等或身份边界发生变化时，均需新决议与 diff；当前哈希作为 P0-1 输入基线。

---

## 七、P0-1 交接

请 DSH 以九份冻结契约为唯一输入，按既定 T1~T9 DAG 启动 P0-1。首包仅处理 T1 migration 基础设施：Alembic/PG driver、revision 骨架、`app` schema/search_path、空库 upgrade/downgrade 门禁与可复现实测证据；better-auth auth revision 继续等待其专属硬 gate。

建议下一份交接文件：`from-dsh/round-43-dsh-P0-1-T1迁移基础设施.md`。后续每包继续保持 DSH Owner、Codex Reviewer，并附输入哈希、执行命令、实际结果和回滚证据。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-42-->
