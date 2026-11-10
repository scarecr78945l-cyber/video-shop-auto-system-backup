# round-128 CDX：P0-1 T9 单项终验

> 日期：2026-09-08。输入：round-127、STATE、两份变更文件和当前运行时代码。
> **裁决：R126-1 已闭合，T9 COMPLETE；P0-1 T1~T9 全部 COMPLETE。**
> 本轮仅新增 CDX 报告并更新 STATE；DSH 文件、迁移、业务实现和契约保持原状。下一轮只做 P0-2 范围与差异拆解，不直接开始实现。

## 一、交付物核对

round-127 两份变更文件 SHA-256 与交付表一致；三个保留文件未变化：

```text
assert_t9_catalog.py          4F9E019ACD7B7A40E2C9447DEA17FF65F5E018AC72A11762DB9BDCB5D3D14003
t9_auth_exact_set_drill.py    F7211A1BA7E72A7CB54A7E9B564B1DD1A48C708202E34481B3617C6FFBD63F6C
auth_expected.py              65C5AA4624278A27DE2E70C0819712EC4FDE48C4A501DFC1DC0F9ED81A255B7B
test_workflow_queue.py        7F0FB72B11CECDDD7AA7FCFABE34D1A23E5FB361D383253AF58FAEE8AB4772E0
t9-sample-manifest.md         82F6C2362D25EF43F82205558822416E0AB9C48D94E15E2A29340CAD7667D27C
```

变更范围符合交接声明：仅 `project/scripts/assert_t9_catalog.py` 与 `project/scripts/t9_auth_exact_set_drill.py` 变化；未改 migration、auth/backend 业务实现或契约。

## 二、R126-1 独立终验

`assert_t9_catalog.py` 的 FK 对象键现为：

```python
auth_fks[(child_table, constraint_name)] = (
    child_columns,
    parent_table,
    parent_columns,
    delete_action,
)
```

expected 同样构造成 `(child_table, constraint_name)` 映射，并执行：

1. expected 键逐项查缺失及定义差异；
2. actual 键逐项拒绝额外对象；
3. child columns、parent table、parent columns、delete action 全等；
4. catalog 查询增加确定性 `ORDER BY x.relname, con.conname`。

因此 PostgreSQL 允许的跨 relation 同名约束不再被字典覆盖，也不再被名称集合折叠。

独立重放 round-126 原探针：

```text
BASELINE_RC=0
COLLIDING_FKS=[('account', 'session_user_id_fkey'), ('session', 'session_user_id_fkey')]
COLLIDING_NAME_EXTRA_FK_RC=1
AUTH_FK_GATE_LINES=[... ('account', 'session_user_id_fkey') ... 'extra' ...]
RESTORE_RC=0
TEMP_DB_DROPPED=fkcollision_c4d430df63
```

实际 2 个同名 FK 并存，额外的 `auth.account.session_user_id_fkey` 被明确报告为 extra。R126-1 确定性漏报关闭。

## 三、六项 auth 变异终验

独立临时库完整重放 `t9_auth_exact_set_drill.py`：

```text
[STEP0] baseline RC=0
EXTRA_COLUMN                 RC=1 -> restore RC=0
EXTRA_UNIQUE_INDEX           RC=1 -> restore RC=0
PARTIAL_UNIQUE_INDEX         RC=1 -> restore RC=0
EXTRA_FOREIGN_KEY            RC=1 -> restore RC=0
FK_ACTION_SET_NULL           RC=1 -> restore RC=0
FK_CROSS_TABLE_SAME_NAME     7 FK / 2 same-name; RC=1 -> restore RC=0
T9_AUTH_EXACT_SET_DRILL=PASS
```

临时库由 finally 删除。列、PK、UNIQUE、FK 的当前 auth exact-set 闭包满足 round-122~127 的冻结验收范围。

## 四、标准验证

| 项目 | round-128 独立结果 |
|---|---|
| 交付文件 SHA-256 | 与 round-127 一致 |
| auth exact-set drill | **6/6 RC=1**，逐项恢复 RC=0，PASS |
| round-126 同名 FK 探针 | 从历史 RC=0 修正为 **RC=1**，恢复 RC=0 |
| 七文件全量回归 | **185 passed in 141.97s** |
| workflow 单独回归 | **61 passed in 4.53s** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | job1~job6 PASS，`T9_CI_LAYERS=PASS`，临时库已删除 |

六阶段结果是本地脚本重放，不表述为远端 GitHub Actions 已运行。

## 五、数据库终态

```text
revision=auth000002
app_tables=31
auth_tables=7
enums=60
triggers=17
workflow_rows=0/0
auth_rows=0/0/0
tenants=0
temp_databases=0
```

## 六、阶段裁决

### 6.1 完成状态

- P0-0：9/9 冻结契约保持 COMPLETE。
- P0-1：T1~T9 全部 COMPLETE。
- T9：迁移 upgrade/downgrade/re-upgrade、catalog 定义闭包、行为回归、失败清理、样本 fixture 边界及本地六阶段 CI 在当前冻结范围内通过。

### 6.2 完成边界

P0-1 COMPLETE 只证明本地内部模型、迁移、auth/audit 基座、secret store、CID、流程队列和本地 CI 门禁通过。它不证明：

- 真实微信账号、店铺或投放平台连接已就绪；
- 真实平台报表已取得两次不同版本快照；
- 商品上架或投放写操作已执行；
- 全系统达到生产上线状态。

上述真实能力仍由 P0-3、P0-3.5、P0-4 的资源与 live gate 独立控制。

## 七、交给 DSH 的 round-129：只做 P0-2 分析拆解

请产出 `_experiment/_interop/from-dsh/round-129-dsh-P0-2范围差异与任务拆解.md`，本轮只分析，不修改业务代码、迁移或契约：

1. 对照已冻结 P0-2 范围：两次快照模型、解析版本、ROI 计算、回写幂等、`REPORT_MANUAL` 人工队列、流程/队列协作。
2. 盘点 P0-1 已具备的可复用能力与 P0-2 尚缺能力，逐项给出代码/契约/测试证据路径，禁止把 fixtures 当成真实平台能力。
3. 输出 P0-2 任务 DAG、Owner/Reviewer、输入/输出、验收、回滚、失败分流及最小开发批次。
4. 把依赖真实账号、CDP、页面选择器、真实两次快照的事项继续放在 P0-3 资源门禁，不混入 P0-2 离线验收。
5. 列出需要用户裁决或补充的资源，但先提供默认技术建议；round-129 仅供 Codex 复核后再决定是否开始 P0-2 实现。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-128-->
