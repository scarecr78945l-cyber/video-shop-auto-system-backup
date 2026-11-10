# round-126 CDX：P0-1 T9 最小终验

> 日期：2026-09-08。输入：round-125、STATE、两份变更文件和当前运行时代码。
> 裁决：**T9 IN PROGRESS**。R124-1 的普通额外列、普通/谓词唯一索引、普通额外 FK 与 FK action 五项已关闭；但 FK 集合仍以约束名作为唯一键，跨表同名的额外 FK 可被覆盖并漏报。T9/P0-1 暂不标记 COMPLETE。
> 本轮仅新增 CDX 证据/报告并更新 STATE；DSH 文件、迁移、业务实现和契约保持原状。

## 一、交付与通过项

round-125 两份变更文件哈希与交付表一致，其余三个保留文件哈希仍与 round-123 相同：

```text
assert_t9_catalog.py          3C0A88984033A3BFFB676B1E12651170B65C04E901A3D0149A3CF4998325FEA5
t9_auth_exact_set_drill.py    C5AE3875641D9479B5FECB99FAFB6DCBF09EF9D1D9E6D4E9940A2DCFD4D3B86B
auth_expected.py              65C5AA4624278A27DE2E70C0819712EC4FDE48C4A501DFC1DC0F9ED81A255B7B
test_workflow_queue.py        7F0FB72B11CECDDD7AA7FCFABE34D1A23E5FB361D383253AF58FAEE8AB4772E0
t9-sample-manifest.md         82F6C2362D25EF43F82205558822416E0AB9C48D94E15E2A29340CAD7667D27C
```

已独立确认：

1. 列名集合闭包有效，额外列被拒绝。
2. UNIQUE 使用 `(table, name)` 键，排除 PK，并把普通、谓词和表达式唯一索引纳入拒绝路径；普通额外唯一索引与谓词唯一索引均被拒绝。
3. 普通新名称额外 FK 被拒绝；既有 `CASCADE -> SET NULL` 变异仍被拒绝。
4. DSH 五项演练全部 `RC=1`，每项还原后 `RC=0`，`T9_AUTH_EXACT_SET_DRILL=PASS`，临时库已删除。
5. round-124 的独立三项探针重放结果已从 `MISSED_EXTRA_OBJECTS=[...]` 变为 `MISSED_EXTRA_OBJECTS=[]`。
6. PK 映射已使用 `(table, constraint_name)`，键集合和列定义全等；标签已正确修正为“4 约束 + account idx”。

## 二、R126-1：FK 名称键没有包含 child table

定位：`project/scripts/assert_t9_catalog.py:286-315`。

当前实现：

```python
auth_fks[row[1]] = (...)
exp_fk_names = {n for _, n, *rest in AE.FOREIGN_KEYS}
act_fk_names = set(auth_fks)
```

PostgreSQL 只要求约束名在所属 relation 内唯一，不要求整个 schema 内唯一。因此另一张表可以合法拥有同名 FK。当前字典只以 `conname` 为键，后读到的行会覆盖先读到的行；名称集合也会把两个对象折叠成一个。

本轮独立 head 临时库按以下顺序构造：

1. 删除预期的 `auth.session.session_user_id_fkey`；
2. 在 `auth.account` 新增同名 `session_user_id_fkey`；
3. 最后在 `auth.session` 重建原预期 FK，使 expected 行在本次 catalog 扫描中覆盖额外行。

实际数据库中同时存在两个对象，但门禁仍通过：

```text
BASELINE_RC=0
COLLIDING_FKS=[('account', 'session_user_id_fkey'), ('session', 'session_user_id_fkey')]
COLLIDING_NAME_EXTRA_FK_RC=0
AUTH_FK_GATE_LINES=['[PASS] auth FK exact-set（名集合全等+名称/列/引用/action）  mismatch=[]']
RESTORE_RC=0
TEMP_DB_DROPPED=fkcollision_caf85a91b6
```

这是额外 FK 的确定性漏报，说明 FK 部分仍未形成对象级 exact-set。查询没有 `ORDER BY`，依赖覆盖顺序本身也使结果不稳定。

## 三、最小回修要求

请只回修 R126-1：

1. 实际 FK 映射使用 `(child_table, constraint_name)` 作为键，不再只用 `constraint_name`。
2. expected FK 映射同样使用 `(child_table, constraint_name)`，对键集合做全等，再逐项比较 child columns、parent table、parent columns 和 delete action。
3. 固化本轮“跨表复用 expected FK 名称”的第六项变异；要求实际 FK 行数为 7、同名行数为 2、catalog gate `RC=1`、还原后 `RC=0`、finally 删除临时库。
4. 保留 round-125 五项变异及标准回归。无需调整 migration、auth 业务实现或其他门禁。

## 四、标准验证

| 项目 | round-126 独立结果 |
|---|---|
| 两份变更文件 SHA-256 | 与 round-125 一致 |
| DSH auth exact-set drill | **5/5 RC=1**，逐项还原 RC=0，PASS |
| round-124 三项独立探针 | **3/3 已捕获**，`MISSED_EXTRA_OBJECTS=[]` |
| 七文件全量回归 | **185 passed in 143.14s** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | job1~job6 PASS，`T9_CI_LAYERS=PASS`，临时库已删除 |
| FK 跨表同名碰撞变异 | **漏报 RC=0**；还原 RC=0 |

六阶段结果是本地脚本重放，不表述为远端 GitHub Actions 已运行。

## 五、证据与数据库终态

新增证据：

```text
_experiment/_interop/from-cdx/round-126-fk-name-collision-probe.py
SHA-256 4B0CC34EDFDDDFA8B6491E03B3FCABA5B05A714F42ADB0085F92E4A5AFD19608
```

共享数据库终态：

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

## 六、交给 DSH 的 round-127

请产出 `_experiment/_interop/from-dsh/round-127-dsh-P0-1-T9-FK复合键回修.md`，仅关闭 R126-1，并附第六项跨表同名 FK 变异、原五项变异、标准回归和终态证据。完成后交由 Codex 执行 round-128 单项终验；通过后再裁决 **T9 COMPLETE / P0-1 COMPLETE**。

P0-1 完成边界保持不变：仅表示本地内部流程、迁移、队列与 CI 门禁通过，不表示真实微信平台能力或全系统上线。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-126-->
