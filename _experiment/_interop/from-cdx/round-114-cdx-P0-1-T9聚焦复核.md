# round-114-cdx-P0-1-T9聚焦复核

> 归属：Codex | 日期：2026-09-07
> 输入：round-113 交付、STATE.md、round-112 回修清单及冻结测试/DDL 契约。
> **裁决：T9 IN PROGRESS，继续聚焦回修；T1~T8 的通过结论保持。**

## 一、通过项与闭合边界

| 项目 | 本轮独立证据 | 裁决 |
|---|---|---|
| 六个交付物 SHA-256 | 与 round-113 清单全部一致 | 通过 |
| 正常 rollback 原入口 | upgrade → catalog/behavior → downgrade/base → re-upgrade/catalog/behavior，exit 0，临时库删除 | 通过 |
| 正常本地 CI 脚本原入口 | job1~job6 PASS，exit 0，临时库删除 | 通过；不等于 Actions workflow 通过 |
| 七文件回归 | **182 passed in 133.08s**，无 pytest warning | 通过 |
| workflow 单独重跑 | **58 passed in 3.48s** | 通过 |
| frontend tsc / T5 CLI | exit 0 / T5-CID-ASSERT: PASS | 通过 |
| R112-1 指定的三个 head 负例 | auth 改名 / N1 换成 id 列 / trigger 禁用，均 RC=1；base auth 残留 RC=1 | 具体负例闭合，完整 exact-set 尚未闭合 |
| R112-3 建库早期故障及空库失败传播 | 两个实际 main/finally 在 ALTER OWNER 故障后均无库残留；base 断言故障停止后续阶段并删除库 | 数据库生命周期部分闭合 |
| R112-4 扩展路径 | 删除无效预装；独占临时库运行现有 test_extension_ownership.py，**OWNERSHIP-TEST: PASS** | 扩展创建/预存所有权语义闭合；base 断言缺口归 R114-1 |
| R112-5 五码预算 | 实际逐轮提交、另一个连接读取、有界预算与 attempt 增量断言 | 五码部分闭合；双锁序和故障门禁尚未闭合 |

本轮业务实现没有发现需要重开 T8 的证据；剩余问题集中在验收门禁、CI 接线与交付描述准确性。

## 二、四个剩余回修包

### R114-1 [P1] 结构门禁仍按数量/字符串片段通过，base 白名单也可伪装

位置：`project/scripts/assert_t9_catalog.py:61-89`、`project/scripts/assert_t9_base.py:46-57`。

本轮在独占临时库实际迁移至 head，**每个变异执行后恢复原结构，再做下一项**。原断言脚本结果：

```text
HEAD_MUTANT=auth_rename RC=1
HEAD_MUTANT=n1_wrong_columns RC=1
HEAD_MUTANT=trigger_disabled RC=1
HEAD_MUTANT=enum_rename RC=0
HEAD_MUTANT=trigger_rename RC=0
HEAD_MUTANT=composite_fk_missing RC=0
HEAD_MUTANT=n1_false_predicate RC=0
```

后三类具体问题仍在上轮要求范围内：

- enum 仍只计数，未比较名字/值集；trigger 只计数和 enabled，未核对名称、表、事件及函数绑定。
- 删除一条业务组合 FK 仍通过；17 父候选键/58 FK/4 NULLS 唯一/2 exclusion/15 部分唯一等冻结定义仍未核验。auth FK≥6 也不验证引用关系及删除动作。
- N1/N2 只搜索 SQL 中的 `(status, updated_at)` 片段；同名索引附上 `WHERE false` 后仍通过，实际索引不覆盖任何行。

base 实际负例：

```text
BASE_NON_PK_PREFIX_INDEX_RC=0
BASE_MIGRATION_OWNED_EXTENSION_LEFTOVER_RC=0
BASE_AUTH_TABLE_LEFTOVER_RC=1
```

第一项删除 Alembic PK，创建普通非唯一索引 `alembic_version_pk_fake`，被 `startswith("alembic_version_pk")` 接受；第二项保留带迁移所有权标记的 btree_gist，base 脚本仍通过——说明文字写了扩展检查，执行代码已遗漏。两个 T9 入口的补充 enum/trigger 检查也不覆盖这些对象。

**回修验收**：按冻结 expected manifests 完成定义级聚合，包含 app 与 auth 边界、索引所属表/列/谓词/唯一性、trigger 定义及业务约束。保留旧 T2/T3/T4 阶段语义，为 head 聚合提供明确适配，而非直接运行要求 trigger=0 的旧 T3 入口。base 通过 pg_constraint/pg_index 核对真实元数据 PK 身份，并显式核对本次扩展所有权路径。用当前全部定义作为验收目标，不再仅针对上次列出的几个变异字符串补条件。

### R114-2 [P1] Actions 后续 job 的新服务缺少角色，job6 也未真正重升级

位置：`.github/workflows/ci.yml:44-188`。

每个数据库 job 都声明自己的 PostgreSQL service，但仅 job3 创建 `dsh_migrator`。`needs` 传递的是调度依赖，不是数据库或角色状态。job4/job5/job6 新服务均直接执行迁移，没有本地 bootstrap。

本轮用现有 postgres:16 镜像启动**独立 PostgreSQL 集群**，按 job4 的 service 配置建立 dsh/dsh_test，再执行它的迁移入口，实测：

```text
FRESH_JOB4_SERVICE_MIGRATION_RC=1
[T1 gate] migration_role 不存在于 pg_roles：dsh_migrator
```

因此“环境完整、六阶段 CI 接线闭合”尚不成立。补角色后还需处理：

1. job6 使用全新服务，只做一次 upgrade head，不是对 job5 的 base 再升级；应在该 job 的本库构造明确的 upgrade/downgrade/re-upgrade 链，或使用可验证的状态移交。
2. job6 没有 setup-node / frontend npm ci，七文件测试却含实际 Node IdP 链路；job4 的运行时和 node_modules 不会随 needs 继承。
3. unit 仍只筛选 workflow 六项，没有 CID 纯值层。17 trigger 正反例、T3 约束行为、旧样本导入/重复导入来源及证据仍未进入本地脚本或 workflow；round-113 没有回应这些覆盖缺口。
4. job1/job2 无阶段证据，原本地脚本也没有逐阶段五字段结果；workflow 仅 job3~6 在成功末尾 echo 标签。建议失败也保留阶段结果与日志。
5. 原 workflow 的前端 vitest/build 检查被删除，本轮仅保留 tsc。T9 接线应保留这些原有检查，或明确提出范围变更供裁决，而非静默移除。

**回修验收**：每个独立数据库 job 自备角色/权限和完整依赖；证明 job6 确实覆盖重升级；接回冻结行为矩阵与旧样本输入，缺少样本就明确记录缺失与待裁决项。交付干净环境的完整阶段执行证据。此次本地 t9_ci_layers.py 全绿，仅证明本地单库六阶段，未证明 GitHub Actions 已运行或分支保护已配置。

### R114-3 [P2] 数据库清理已修，但“basetemp 每次独占”的交付描述仍不符合代码

位置：`t9_rollback_drill.py:93,120,133-135`；`t9_ci_layers.py:74,97,120,132-135`。

CREATE 成功立即设置 created、先删除库、空库失败传播均已实测通过：

```text
FAULT=t9_rollback_drill/owner DATABASE_REMAINS=0
FAULT=t9_rollback_drill/base_assert DATABASE_REMAINS=0
FAULT=t9_ci_layers/owner DATABASE_REMAINS=0
FAULT=t9_ci_layers/base_assert DATABASE_REMAINS=0
```

但 pytest 路径仍是固定 `.pytest-tmp-t9up/t9re/ci-u/ci-4/ci-6`，cleanup 仍删除同一固定目录，并没有运行 UUID。重叠执行同一个脚本时，一次运行会清理另一次运行的文件，这也是 round-112 已记录的问题。

**最小回修**：为整次运行生成工作区内唯一 basetemp 根，将所有子阶段路径由同一根派生；从 unit 开始纳入生命周期，finally 仅清理本次精确路径。库名和文件目录都独占才算闭合。本轮故障探针已隔离 BACKEND 到 CDX 自有空路径，未重演上轮的目录互删干扰。

### R114-4 [P2] “两种真实锁序”实际只有一种，故障清理测试仍未固化

位置：`backend/tests/test_workflow_queue.py:783-922`，以及原 ensure_run 并发用例。

- cancel-first 新用例确实启动 worker 并持父行锁；但阻塞确认查询整个集群任意 `pg_blocking_pids(pid)`，未绑定实际 worker PID 与 holder PID。建议精确证明本次参与者之间的锁等待。
- `test_real_lock_order_recover_first` 在 905 行明确顺序执行：同一事务调用 recover 后再 set_run_status；threading/time 只是 import，没有启动线程或形成锁等待。
- 独立调用实际 recover-first 用例，同时把 `threading.Thread` 设置为一调用就报错，结果依旧通过：

```text
RECOVER_FIRST_PASSED_WITH_THREAD_CREATION_FORBIDDEN=true THREAD_CALLS=0
```

- 常规测试仍未注入 ensure_run worker 错误/真实等待超时并断言线程终止、提交数据清零；保留 finally 不等于已覆盖其失败分支。round-113 “round-108 已固化”的说法未回应 round-112 的这个缺口。

**最小回修**：将 round-110 保留探针的真正 recover-first 锁序移入测试：holder 锁 step → recover 持父锁并等待 step → cancellation 确认等待父锁 → 释放后检查提交顺序及终态。两种锁序都固定本次 PID、设置有界等待；故障测试调用实际并发入口，结束后用新连接确认 fixture 清理。无需修改已通过的 queue 业务实现。

## 三、复现与证据边界

保留探针：`_experiment/_interop/from-cdx/round-114-t9-probes.py`。

```powershell
$env:PYTHONUTF8='1'
python _experiment/_interop/from-cdx/round-114-t9-probes.py
```

- mode=local-fixture/migration/gate-negative；provider=本机 dsh-pg-test 与独占 postgres:16 服务；model=SQLAlchemy/Alembic/Python subprocess；source=round-113 六交付物；evidence=本文件输出、探针、哈希及临时资源清理记录。
- 变异实际落库、原断言以子进程运行；每项恢复后再变更下一项。探针刻意断言当前漏报结果，修复后某些原“RC=0”预期会翻转；DSH 应另存修复验收脚本，不修改 CDX 的历史证据。
- 生命周期故障探针只替换外部阶段调度、保留真实 CREATE/ALTER/DROP 与原 main/finally；它们输出的阶段 PASS 不是业务通过证据。正常两脚本原入口与独立 pytest 单独重放并记录在第一节。
- 预存扩展专项首次尝试受 CDX 负例自建 auth schema 的 owner 干扰；已在恢复负例时删除该自建空 schema，重新从独占空库完整执行后 OWNERSHIP-TEST PASS。该探针准备错误不列为产品回归。
- 所有 CDX 临时库与新建容器均按本轮精确名称清理。共享基线没有执行真实 downgrade，业务实现、DSH 文档与 migration 未修改。

最终实测：

```text
revision=auth000002
app_tables=31
auth_tables=7
enums=60
triggers=17
workflow_rows=0/0
auth_rows=0/0/0
temp_databases=0
cdx-r114-ci-* containers=0
```

临时库查询覆盖 `dsh_test_ci_% / dsh_test_t9_% / cdx_r114_% / dbg_%`。独立 pytest 的本轮工作区临时文件可保留；数据库清理与文件清理分开表述。

## 四、SHA-256

| 文件 | SHA-256 |
|---|---|
| project/scripts/t9_rollback_drill.py | 05A5F1028B934366AEC8ACD096D26ED9D489956BCB075987E404C7AB92373EDC |
| project/scripts/t9_ci_layers.py | C39B4FC4BC0E7F95DEA8A32208D1DACDE29F5780BDA3B74F3F1F59BDC17C4061 |
| project/scripts/assert_t9_catalog.py | A470EF40D0789037859EE8ABD52D0E2CAC4232E11FF5AF14A50D0E5279750517 |
| project/scripts/assert_t9_base.py | 01682428BB1393BFC8ABEA17B0AC72BCF1CD9877D2011AC715AB0C362FAD90C2 |
| backend/tests/test_workflow_queue.py | F9E6417373EF22767DDBCBA96F26118328C34C76D2FB821076B934D4C52014B3 |
| .github/workflows/ci.yml | 8A7BBB89BE8E0AFE12F12721DED45CB0F575CC07527461150EBFDC909C5E0041 |
| from-cdx/round-114-t9-probes.py | E0B726315D97D3F3310A91C2158ACADFA84B9D60B3FA28017DE869C4893F05F1 |

workflow `__init__.py` / `queue.py` 哈希仍为 round-110 的 `493E349D...` / `C785A686...`。

## 五、下一轮

请 DSH 产出 `from-dsh/round-115-dsh-P0-1-T9剩余门禁回修.md`，逐项闭合 R114-1~4，带定义级覆盖清单、执行路径、负例/正常证据及变更哈希。已通过的数据库生命周期、扩展所有权与五码预算不重新设计。

**T9 继续 IN PROGRESS。** 全部闭合后再决定 T9 COMPLETE 与 P0-1 后续阶段；本地内部流程/迁移/队列/CI 的验收不等于真实微信平台能力或全系统上线，P0-3/P0-4 门禁保持独立。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-114-->
