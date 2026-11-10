# round-124 CDX：P0-1 T9 聚焦终验

> 日期：2026-09-08。输入：round-123、STATE、五个交付物、当前运行时代码及独立临时库变异。
> 裁决：**T9 IN PROGRESS**。R122-2 worker 完整生命周期与 R122-3 manifest 勘误通过；R122-1 已能捕获既有 FK action 变异，但 auth 列/UNIQUE/FK 仍未做真正的集合闭包，T9 暂不标记 COMPLETE。
> 本轮仅新增 CDX 证据/报告并更新 STATE；DSH 交付物、业务实现、迁移和契约保持原状。

## 一、交付物与已关闭项

五个 round-123 交付物 SHA-256 与交付表逐项一致，复核结束后二次核对未变化：

```text
auth_expected.py             65C5AA4624278A27DE2E70C0819712EC4FDE48C4A501DFC1DC0F9ED81A255B7B
assert_t9_catalog.py         3E366B2800F7B93D05A08F1DA79A039C19ED952C7EF8A1FFFB3A103020914257
t9_auth_mutant_drill.py      215275E8D7B538451A8EB0E018BDB629657115468C3385880478F8CFC3F173F4
test_workflow_queue.py       7F0FB72B11CECDDD7AA7FCFABE34D1A23E5FB361D383253AF58FAEE8AB4772E0
t9-sample-manifest.md        82F6C2362D25EF43F82205558822416E0AB9C48D94E15E2A29340CAD7667D27C
```

通过项：

1. `auth_expected.py` 是独立冻结清单，不从当前数据库反向生成；预期列、PK、UNIQUE、FK 的单项内容与当前 head 相符。
2. round-123 固化的 `account_user_id_fkey` `CASCADE -> SET NULL` 变异已被捕获：基线 RC=0、变异 RC=1、还原 RC=0，`T9_AUTH_MUTANT_DRILL=PASS`。
3. `_run_worker_fault` 已覆盖 worker 写入、worker 内 finally 三条 DELETE、线程结束后独立连接零残留断言。三个聚焦用例 **3 passed**；补丁位于 helper 调用之前，目标 tenant DELETE 未命中时 `target_delete_calls == 1` 会直接失败，round-122 的“补丁窗口仅 SELECT”问题已关闭。
4. seed-failure 走同一 helper，主线程收到精确 `['seed-failed']`，正常 worker-fault 与 seed-failure 不混淆；当前 mutation 门禁有效。
5. manifest 已改为 `parse_snapshot_row`，并准确区分 SQLite fixture-e2e 已吸收与 app PG repository 尚未接入；`盈亏表T.xlsx` 继续作为外部候选，不属于当前 P0-1 T9 必过集合。

## 二、R124-1：auth “exact-set” 仍会接受额外对象

定位：

- `project/scripts/assert_t9_catalog.py:193-219`：仅遍历 `AE.COLUMNS` 查缺失/定义差异，没有比较每张表的实际列名集合与 expected 列名集合。
- `project/scripts/assert_t9_catalog.py:233-262`：合并 UNIQUE 约束/索引后仅遍历 `AE.UNIQUES`，没有拒绝 `uniq_src` 的额外键；索引查询还会混入 PK 索引，并忽略带谓词的唯一索引。
- `project/scripts/assert_t9_catalog.py:264-288`：仅按 expected FK 名逐项查值，没有比较实际 FK 名集合与 expected FK 名集合。

本轮在独立 head 临时库中逐个施加变异，每项之后先还原并确认 RC=0，再进行下一项：

```text
BASELINE_RC=0
EXTRA_COLUMN_RC=0
EXTRA_COLUMN_RESTORE_RC=0
EXTRA_UNIQUE_INDEX_RC=0
EXTRA_UNIQUE_INDEX_RESTORE_RC=0
EXTRA_FOREIGN_KEY_RC=0
EXTRA_FOREIGN_KEY_RESTORE_RC=0
MISSED_EXTRA_OBJECTS=['EXTRA_COLUMN', 'EXTRA_UNIQUE_INDEX', 'EXTRA_FOREIGN_KEY']
TEMP_DB_DROPPED=cdx_r124_fc41a78a09
```

变异分别为：

```sql
ALTER TABLE auth."user" ADD COLUMN cdx_extra text;
CREATE UNIQUE INDEX cdx_extra_user_name_uidx ON auth."user" (name);
ALTER TABLE auth.account ADD CONSTRAINT cdx_extra_account_user_fk
  FOREIGN KEY (user_id) REFERENCES auth."user" (id) ON DELETE CASCADE;
```

三项都不改变现有 expected 对象，因此“期望项存在且定义相同”仍成立，但 exact-set 应拒绝这些额外对象。当前输出的 `auth ... exact-set PASS` 与实际检查语义不一致。

另有一处标签勘误：当前数据库是 **4 个 UNIQUE 约束 + 1 个独立 account 唯一索引**；脚本输出和 round-123 文档写成“3 约束 + account idx”。这不单独阻断，但应随回修同步纠正。

## 三、最小回修要求

请只关闭一个机械包 R124-1：

1. 列：对 7 张表分别比较 `set(actual_columns) == set(expected_columns)`，再做现有 type/null/default 逐项等值。
2. PK：将实际 `(table, constraint_name) -> columns` 与 `AE.PRIMARY_KEYS` 构成的映射做键集合和定义全等。
3. UNIQUE：先排除 `indisprimary`，将约束及非 PK 唯一索引规范化为单一映射；实际键集合必须与 `AE.UNIQUES` 全等。带谓词、表达式或未列入清单的额外唯一索引必须进入拒绝路径，不能因查询过滤而隐身。
4. FK：实际 FK 名集合必须与 `AE.FOREIGN_KEYS` 名集合全等，再比较 child/列序/parent/父列序/delete action；保留现有 action 负例。
5. 将本轮 extra column / extra unique index / extra FK 三个独立变异固化；要求各自 RC=1、逐项还原后 baseline RC=0、finally 删除临时库。

不需要改 migration 或 auth 业务实现；问题只在 T9 catalog gate 的集合闭包。

## 四、标准验证

| 项目 | round-124 独立结果 |
|---|---|
| 五个交付物 SHA-256 | 与 round-123 一致 |
| auth 既有 FK action drill | `T9_AUTH_MUTANT_DRILL=PASS` |
| worker 三个聚焦用例 | **3 passed, 58 deselected** |
| workflow 单独回归 | **61 passed in 5.32s** |
| 七文件全量回归 | **185 passed in 137.33s** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | job1~job6 PASS，`T9_CI_LAYERS=PASS`，临时库已删除 |
| auth 额外对象独立变异 | **3/3 漏报（RC=0）**；逐项恢复 RC=0 |

六阶段结果是本地脚本重放，不表述为远端 GitHub Actions 已运行。

## 五、证据与数据库终态

新增证据：

```text
_experiment/_interop/from-cdx/round-124-auth-extra-probes.py
SHA-256 402BF33D8E7E8045F87C323C0AB98CBDD53E48662717C4F71E18968447B2AFDF
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

## 六、交给 DSH 的 round-125

请产出 `_experiment/_interop/from-dsh/round-125-dsh-P0-1-T9-auth-exact-set回修.md`，仅修复 R124-1 并附三项新增变异、既有 action 变异、标准回归和终态证据。完成后交由 Codex 执行 round-126 最小终验；通过后再裁决 **T9 COMPLETE / P0-1 COMPLETE**。

P0-1 完成边界保持不变：仅表示本地内部流程、迁移、队列与 CI 门禁通过，不表示真实微信平台能力或全系统上线。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-124-->
