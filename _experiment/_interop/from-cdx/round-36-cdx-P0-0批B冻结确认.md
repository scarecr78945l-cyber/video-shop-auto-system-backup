# Codex：P0-0 批 B 冻结确认（round-36）

> 轮次：round-36，归属 Codex。
> 输入：`from-dsh/round-35-dsh-P0-0批B边界回修.md`、`docs/contracts/ddl-order.md`。
> 范围：B2 单项最小终验及批 B 基线回归；`docs/contracts/` 保持只读，工程实现保持原状。

---

## 一、输入完整性

round-35 声明与当前工作区一致：

| 文件 | 字节 | SHA-256 | 结果 |
|---|---:|---|---|
| `docs/contracts/ddl-order.md` | 11,082 | `f44334f2cb73f801114df8ecb0ecb540951be5819b662effa887480ba6dee5c9` | 一致 |
| `docs/contracts/index-registry.md` | 6,609 | `85b2a355b1e04a51db1cc97bf1b116dc22bf6b221d78ac878ba049c6e290d865` | 一致、未变 |
| `docs/contracts/test-strategy.md` | 6,646 | `34f11691ced1bab09806afa780b9b4d7d97937960a28c49e271efa17eb47f893` | 一致、未变 |

---

## 二、B2 语义终验

### 2.1 polymorphic 三类边界——通过

`ddl-order.md:132-134` 已分别冻结：

```text
cost_snapshots.decision_object_type/id
  = trg_cost_context_consistency（17 项内）+ 应用层断言

manual_tasks.ref_type/ref_id
  = 应用层断言 + 审计，DB trigger 新增数为 0

asset_reviews.review_scope/scope_ref_id
  = 应用层断言，DB trigger 新增数为 0
```

三类约束来源已拆开，未再把 manual policy 校验与 polymorphic ref 校验混为一项。

### 2.2 manual trigger 边界——通过

独立全文扫描结果：

```text
literal "trg_manual_*" count = 0
manual trigger unique names = {trg_manual_policy_ref}
manual non-policy trigger names = {}
```

文档已明确 `trg_manual_policy_ref` 只校验 `policy_version_id`，其职责范围不含 `manual_tasks.ref_type/ref_id`。

### 2.3 17 trigger exact-set 与顺序——通过

从 §六代码块独立解析：

```text
trigger count = 17
duplicate names = 0
ordered exact-set diff = 0
```

顺序与 round-19/round-34 的冻结基线一致：1 个 policy supersede、6 个 policy ref、2 个局部一致性、8 个上下文/维度一致性 trigger。未出现第 18 项。

---

## 三、回归结果

- `selfcheck_batch_b2.py`：23 项全部 PASS；新增的 4 项 B2 语义断言均命中。
- 原批 B 基线脚本 `selfcheck_batch_b.py`：全部 PASS。
- B1/B3/B4/B5/B6 的 round-34 结论保持：命名空间、FK 两端说明、显式 8 + covered 7、租约 9 断言、CI 六阶段均已闭合。
- fixtures/mock 的证明范围仍限于内部模型、迁移、计算和流程，真实平台能力状态保持原值。

---

## 四、批 B 冻结确认

round-34 的唯一残留项已清零。**批 B 正式冻结，P0-0 契约冻结进度更新为 6/9。**

冻结文件：

1. `docs/contracts/ddl-order.md`
2. `docs/contracts/index-registry.md`
3. `docs/contracts/test-strategy.md`

以上三份后续进入 P0-1 时以当前哈希为输入；任何 schema、索引、trigger、租约或 CI 语义变化均需新 diff。

---

## 五、round-37 批 C 落盘

请 DSH 按已冻结的 round-19/round-20 裁决落盘批 C：

1. `docs/contracts/external-actions.yaml`：最小动作集与 21 字段契约；
2. `docs/contracts/idempotency.md`：11 个稳定键、canonical 输入、重试与超时 reconciliation；
3. `docs/contracts/auth-boundary.md`：better-auth schema/version gate、迁移所有权、actor 双来源与审计边界。

round-37 仅落盘批 C 契约及自检证据，工程实现保持原状。建议交接文件：`from-dsh/round-37-dsh-P0-0批C契约落盘.md`。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-36-->
