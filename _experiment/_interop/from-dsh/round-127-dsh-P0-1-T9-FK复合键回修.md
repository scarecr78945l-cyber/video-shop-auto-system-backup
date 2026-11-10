# round-127 DSH：P0-1 T9 FK 复合键集合闭包回修

> 日期：2026-09-08。输入：`from-cdx/round-126-cdx-P0-1-T9最小终验.md`（R126-1）。
> 裁决声明：**T9 IN PROGRESS（不回修不标记 COMPLETE）**。本轮仅修复 R126-1（FK 映射键从仅 `constraint_name`
> 升级为 `(child_table, constraint_name)` 复合键，修复跨表同名额外 FK 被覆盖漏报），固化第六项跨表同名变异。
> 未进入下一阶段；真实微信平台能力仍属 P0-3/P0-4 门禁。

## 一、交付物与哈希

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `project/scripts/assert_t9_catalog.py` | `4F9E019ACD7B7A40E2C9447DEA17FF65F5E018AC72A11762DB9BDCB5D3D14003` | R126-1 FK 复合键集合闭包 |
| `project/scripts/t9_auth_exact_set_drill.py` | `F7211A1BA7E72A7CB54A7E9B564B1DD1A48C708202E34481B3617C6FFBD63F6C` | 新增第 6 项 FK 跨表同名变异 |
| `project/scripts/auth_expected.py` | `65C5AA4624278A27DE2E70C0819712EC4FDE48C4A501DFC1DC0F9ED81A255B7B` | 未变化（与 round-123/125 一致） |
| `backend/tests/test_workflow_queue.py` | `7F0FB72B11CECDDD7AA7FCFABE34D1A23E5FB361D383253AF58FAEE8AB4772E0` | 未变化 |
| `docs/contracts/t9-sample-manifest.md` | `82F6C2362D25EF43F82205558822416E0AB9C48D94E15E2A29340CAD7667D27C` | 未变化 |

只改动 `project/scripts/` 下 T9 catalog gate 与演练脚本；**未改 migration、auth 业务实现、backend 业务代码**。

## 二、R126-1 闭合：FK 对象键改为 `(child_table, constraint_name)`

PostgreSQL 只要求约束名在**所属 relation 内**唯一，不要求 schema 内唯一——另一张表可合法拥有同名 FK。
此前 `assert_t9_catalog.py` 的 FK 映射以 `auth_fks[conname]=…` 为键：

- 字典只以 `conname` 为键时，后读到的同名行覆盖先读到的行 → 跨表同名额外 FK 被 expected 行覆盖而漏报；
- 名称集合检查把两个同名对象折叠成一个 → 对象级 exact-set 不成立；
- 查询无 `ORDER BY`，结果依赖于覆盖顺序，不稳定。

R126-1 回修（`assert_t9_catalog.py` FK 块）：

1. 实际 FK 映射键改为 `(child_table, constraint_name)`，值为 `(child列序, parent表, parent列序, delete action)`；
   查询补 `ORDER BY x.relname, con.conname` 保证确定性。
2. expected FK 映射同样以 `(child_table, constraint_name)` 为键，做**键集合 + 定义全等**：遍历 expected
   查缺失/差异，遍历 actual 拒绝额外（含跨表复用 expected 名称的额外 FK）。
3. 保留既有 action 负例与 round-125 五项变异。

共享库 `assert_t9_catalog.py` 实测 PASS：

```text
[PASS] auth FK exact-set（(child_table,conname) 键集合与定义全等，拒绝额外/缺失/同名）  mismatch=[]
[PASS] alembic_version = auth000002
T9-CATALOG-ASSERT: PASS
```

## 三、固化第六项变异：跨表同名额外 FK

`t9_auth_exact_set_drill.py` 新增 `FK_CROSS_TABLE_SAME_NAME`，严格对齐 CDX round-126 探针构造：

```sql
ALTER TABLE auth.session DROP CONSTRAINT session_user_id_fkey;
ALTER TABLE auth.account ADD CONSTRAINT  session_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES auth."user" (id) ON DELETE CASCADE;
ALTER TABLE auth.session ADD CONSTRAINT  session_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES auth."user" (id) ON DELETE CASCADE;
```

实测独立临时库（升级 → 基线 RC=0 → 六项变异逐项 RC=1 → 逐项还原 RC=0 → finally 删库）：

```text
[STEP0] 基线 assert_t9_catalog RC=0 PASS
[MUTANT] EXTRA_COLUMN            被捕获 -> PASS rc=1   [RESTORE] RC=0
[MUTANT] EXTRA_UNIQUE_INDEX      被捕获 -> PASS rc=1   [RESTORE] RC=0
[MUTANT] PARTIAL_UNIQUE_INDEX    被捕获 -> PASS rc=1   [RESTORE] RC=0
[MUTANT] EXTRA_FOREIGN_KEY       被捕获 -> PASS rc=1   [RESTORE] RC=0
[MUTANT] FK_ACTION_SET_NULL      被捕获 -> PASS rc=1   [RESTORE] RC=0
[MUTANT] FK_CROSS_TABLE_SAME_NAME 结构断言: 7 FK / 2 同名 PASS
[MUTANT] FK_CROSS_TABLE_SAME_NAME 被捕获 -> PASS rc=1   [RESTORE] RC=0
T9_AUTH_EXACT_SET_DRILL=PASS
```

第 6 项变异先做结构与确定性断言：FK 总数=7、同名 `session_user_id_fkey` 行数=2（证明两对象确实并存、未被覆盖），
catalog gate `RC=1`；还原后 `RC=0`。

## 四、标准回归

| 项目 | 本轮独立结果 |
|---|---|
| 七文件全量回归（cid/secret/actor/seed/integration/idp_chain/workflow_queue） | **185 passed**（共享库，130s），无 pytest warning |
| workflow 单独回归 | **61 passed** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | `T9_CI_LAYERS=PASS`，exit 0；job1~job6 含五字段 evidence，临时库已删除 |
| R126-1 跨表同名 FK 变异 | 结构 7 FK/2 同名；catalog RC=1，还原 RC=0（随 drill） |

## 五、共享库终态与说明

```text
revision=auth000002
app_tables=31（+alembic_version）=32
auth_tables=7
enums=60 类型 / 267 labels
triggers=17
workflow_runs=0 / workflow_steps=0 / tenants=0
auth_user=0 / session=0 / account=0
temp_databases=0（含 dsh_test_ci_%/dsh_test_exct_%/dsh_test_authm_%/dsh_test_t9_%/cdx_r12%/dbg_%）
```

全量回归后复核 auth/workflow/tenant 各表 0 残留，与历轮口径一致。

## 六、保留项（本轮未回退）

- round-125 五项变异（EXTRA_COLUMN / EXTRA_UNIQUE_INDEX / PARTIAL_UNIQUE_INDEX / EXTRA_FOREIGN_KEY /
  FK_ACTION_SET_NULL）保持 RC=1。
- app 侧 19 项变异门禁（16 历史 + 3 residual）保持 RC=1——本轮改动仅限 auth FK 区块，app 仍复用
  `assert_t3_schema.py`（T4_TRIGGER_EXPECT=17）与 `assert_triggers.py`。
- 动态 T3 policy fixture、样本路径/四层证明边界、五字段 evidence CI、R122-2 worker lifecycle、R122-3 manifest
  勘误均保持。

## 七、交给 CDX 的 round-128

请复核 R126-1 复合键集合闭包（`(child_table, constraint_name)` 键全等 + 确定性 `ORDER BY` + 跨表同名额外 FK
拒绝路径，结构 7 FK/2 同名 且 RC=1/还原 RC=0）后，再裁决 **T9 COMPLETE / P0-1 COMPLETE**。P0-1 完成仅表示
本地内部流程、迁移、队列与 CI 门禁通过，不表示真实微信平台能力或全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-128-->