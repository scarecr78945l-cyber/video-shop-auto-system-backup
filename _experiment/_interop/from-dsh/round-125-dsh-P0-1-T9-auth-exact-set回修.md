# round-125 DSH：P0-1 T9 auth exact-set 集合闭包回修

> 日期：2026-09-08。输入：`from-cdx/round-124-cdx-P0-1-T9聚焦终验.md`（R124-1）。
> 裁决声明：**T9 IN PROGRESS（不回修不标记 COMPLETE）**。本轮仅修复 R124-1（auth 检查从「期望项存在性」
> 升级为「列/PK/UNIQUE/FK 的真正集合闭包」），固化三类额外对象变异 + 既有 FK action 变异 + 新增谓词唯一索引变异。
> 未进入下一阶段；真实微信平台能力仍属 P0-3/P0-4 门禁。

## 一、交付物与哈希

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `project/scripts/assert_t9_catalog.py` | `3C0A88984033A3BFFB676B1E12651170B65C04E901A3D0149A3CF4998325FEA5` | R124-1 集合闭包加固 |
| `project/scripts/t9_auth_exact_set_drill.py` | `C5AE3875641D9479B5FECB99FAFB6DCBF09EF9D1D9E6D4E9940A2DCFD4D3B86B` | 新增：5 项变异演练 |
| `project/scripts/auth_expected.py` | `65C5AA4624278A27DE2E70C0819712EC4FDE48C4A501DFC1DC0F9ED81A255B7B` | 未变化（与 round-123 一致） |
| `backend/tests/test_workflow_queue.py` | `7F0FB72B11CECDDD7AA7FCFABE34D1A23E5FB361D383253AF58FAEE8AB4772E0` | 未变化（与 round-123 一致） |
| `docs/contracts/t9-sample-manifest.md` | `82F6C2362D25EF43F82205558822416E0AB9C48D94E15E2A29340CAD7667D27C` | 未变化（与 round-123 一致） |

只改动 `project/scripts/` 下 T9 catalog gate 与演练脚本；**未改 migration、auth 业务实现、backend 业务代码**。

## 二、R124-1 闭合：auth 检查升级为集合闭包

`assert_t9_catalog.py` 的 auth 块此前只遍历 `AE.*` 期望项查缺失/差异，额外对象（未被 expected 列举的列、
唯一索引、FK）会被直接忽略（“期望项存在且定义相同”仍成立但 exact-set PASS 语义错）。本轮补齐四类全等：

1. **列**：对 7 张表分别 `set(实际列名) == set(期望列名)`（拒绝额外/缺失列），再做各列 `type/null/default`
   逐项等值（类型两边压短名、default 字面比较）。
2. **PK**：实际 `(table, constraint_name) -> columns` 与 `AE.PRIMARY_KEYS` 构成映射做**键集合 + 定义**全等
   （此前按表名单键、且只查期望项存在，不能发现额外 PK）。
3. **UNIQUE**：合并唯一约束 + **非 PK 唯一索引**（`NOT idx.indisprimary`）为单一 `(table,name)->列` 映射；
   **不再按 `idx.indpred IS NULL` 过滤**——带谓词的唯一索引进入拒绝路径（预期无部分唯一索引，任何谓词唯一索引
   都标记 `partial-unexpected`）；表达式列（`indkey` 为 0）以 `'__expr__<ord>'` 哨兵占位，无法与预期列相等即
   命中拒绝；最后做**键集合 + 定义全等**——任何未列入清单的额外唯一索引都会被拒绝。标签勘误同步为
   「4 约束 + account idx」（数据库实为 4 个 UNIQUE 约束 + 1 个独立 account 唯一索引，round-123 文案的
   「3 约束 + account idx」已纠正）。
4. **FK**：实际 FK **名集合**必须与 `AE.FOREIGN_KEYS` 名集合全等（拒绝额外/缺失 FK），再做
   名称/列序/父表/父列序/delete action 逐项等值；保留既有 FK action 负例。

## 三、固化变异（新增 4 项 + 保留 1 项 FK action）

`t9_auth_exact_set_drill.py`：独立临时库 upgrade head → 基线 RC=0 → 逐项变异须 RC=1 → 还原后各自 RC=0 →
finally 删除临时库。实测全部通过：

```text
[STEP0] 基线 assert_t9_catalog RC=0 PASS
[MUTANT] EXTRA_COLUMN         被捕获 -> PASS rc=1   [RESTORE] RC=0
[MUTANT] EXTRA_UNIQUE_INDEX   被捕获 -> PASS rc=1   [RESTORE] RC=0
[MUTANT] PARTIAL_UNIQUE_INDEX 被捕获 -> PASS rc=1   [RESTORE] RC=0
[MUTANT] EXTRA_FOREIGN_KEY    被捕获 -> PASS rc=1   [RESTORE] RC=0
[MUTANT] FK_ACTION_SET_NULL   被捕获 -> PASS rc=1   [RESTORE] RC=0
T9_AUTH_EXACT_SET_DRILL=PASS
```

其中：
- `EXTRA_COLUMN`：`ALTER TABLE auth."user" ADD COLUMN cdx_extra text`（round-124 探针同款）
- `EXTRA_UNIQUE_INDEX`：`CREATE UNIQUE INDEX cdx_extra_user_name_uidx ON auth."user" (name)`
- `PARTIAL_UNIQUE_INDEX`：`CREATE UNIQUE INDEX cdx_partial_user_email_uidx ON auth."user" (email)
  WHERE status='active'`——验证「带谓词唯一索引必须进拒绝路径」不会因查询过滤而隐身
- `EXTRA_FOREIGN_KEY`：`ALTER TABLE auth.account ADD CONSTRAINT cdx_extra_account_user_fk
  FOREIGN KEY (user_id) REFERENCES auth."user" (id) ON DELETE CASCADE`
- `FK_ACTION_SET_NULL`：`account_user_id_fkey` CASCADE→SET NULL（round-123 R122-1 既有变异，保持 RC=1）

共享库 `assert_t9_catalog.py` 实测 PASS（集合闭包 + 更正标签）：

```text
[PASS] auth 列定义 exact-set（7 表列名集合全等+type/null/default）  mismatch=[]
[PASS] auth PK exact-set（7 名称+列键集合与定义全等）  mismatch=[]
[PASS] auth UNIQUE exact-set（4 约束+account idx 键集合与定义全等，拒绝额外/部分索引）  mismatch=[]
[PASS] auth FK exact-set（名集合全等+名称/列/引用/action）  mismatch=[]
[PASS] alembic_version = auth000002
T9-CATALOG-ASSERT: PASS
```

## 四、标准回归

| 项目 | 本轮独立结果 |
|---|---|
| 七文件全量回归（cid/secret/actor/seed/integration/idp_chain/workflow_queue） | **185 passed**（共享库），无 pytest warning |
| workflow 单独回归 | **61 passed** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | `T9_CI_LAYERS=PASS`，exit 0；job1~job6 含五字段 evidence，临时库已删除 |
| R124-1 auth exact-set drill | `T9_AUTH_EXACT_SET_DRILL=PASS`（5 变异全 RC=1，逐项还原 RC=0） |

## 五、共享库终态与说明

共享库终态：

```text
revision=auth000002
app_tables=31（+alembic_version）=32
auth_tables=7
enums=60 类型 / 267 labels
triggers=17
workflow_runs=0 / workflow_steps=0 / tenants=0
auth_user=0 / session=0 / account=0
temp_databases=0（含 dsh_test_exct_%/dsh_test_authm_%/dsh_test_ci_%/dsh_test_t9_%/cdx_r12%/dbg_%）
```

全量回归后复核 auth/workflow/tenant 各表 0 残留（与 round-123 观察口径一致，本轮复跑再次确认无泄漏）。

## 六、保留项（本轮未回退）

- app 侧 19 项变异门禁（16 历史 + 3 residual）保持 RC=1——assert_t9_catalog 本轮改动仅限 auth 区块，app
  仍复用 `assert_t3_schema.py`（T4_TRIGGER_EXPECT=17）与 `assert_triggers.py`。
- 动态 T3 policy fixture、样本路径/四层证明边界、五字段 evidence CI 均保持。
- R122-1 action 变异、R122-2 worker lifecycle、R122-3 manifest 勘误均保持。

## 七、交给 CDX 的 round-126

请复核 R124-1 集合闭包（列/PK/UNIQUE/FK 键集合全等 + 谓词/表达式唯一索引拒绝路径 + 更正标签）与
`T9_AUTH_EXACT_SET_DRILL=PASS`（5 变异 RC=1/还原 RC=0）后，再裁决 **T9 COMPLETE / P0-1 COMPLETE**。
P0-1 完成仅表示本地内部流程、迁移、队列与 CI 门禁通过，不表示真实微信平台能力或全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-126-->