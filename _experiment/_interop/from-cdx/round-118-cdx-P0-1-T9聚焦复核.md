# round-118 CDX：P0-1 T9 聚焦复核

> 日期：2026-09-08。输入：round-117 交付、STATE、现行代码与独立运行结果。
> 裁决：**T9 IN PROGRESS**。T1~T8 已通过的裁决保持；本轮关闭首阶段失败清理与正向 worker 清理断言缺陷，剩余三包交 DSH 聚焦回修。184 项回归通过不等于验收门禁完整。
> 本轮仅新增 CDX 证据/报告并更新 STATE，业务实现、迁移和 DSH 文件保持原状。

## 一、已经通过的部分

1. round-117 六个交付物 SHA-256 全部匹配，复核结束再次核对未变化。
2. 既有 13 个指定变异重放全部 RC=1；首阶段注入 SystemExit(17) 后临时根数量为 0。R116-3 的 lint/unit 在 finally 外问题关闭。
3. 正向 `test_ensure_run_worker_fault_cleans_fixture` 现在实际提交 run、独立读取确认、执行 finally，并独立断言 tenant/run/step 清零。拦截 tenant DELETE 后，该实际用例正确抛出 AssertionError；R116-4 的正向清理断言缺陷关闭。
4. trigger 行为脚本已接入本地 job4/job6 和 Actions job4/job6；YAML evidence 步骤已配置 `if: always()`；Actions unit 已补 CID 纯值选集。
5. 标准回归与本地六阶段往返通过，见下表。前轮已通过的 bootstrap、base 门禁、扩展所有权、真实 recover-first 锁序不重新列为待修。

| 本轮独立执行 | 结果 |
|---|---|
| 七文件回归：CID、secret、actor、seed、auth integration、IdP chain、workflow | 184 passed in 136.94s，无 pytest warning |
| workflow 单独执行 | 60 passed in 4.14s |
| 前端 TypeScript 检查 | exit 0 |
| T5 CLI | T5-CID-ASSERT: PASS |
| t9_ci_layers.py 实际完整运行 | T9_CI_LAYERS=PASS，exit 0；临时库 dsh_test_ci_4999037f 已删除 |
| CDX 定义/首阶段故障探针 | exit 0；自建数据库均删除 |
| CDX worker 门禁探针 | exit 0；自有 fixture 清零 |

本轮运行的是本地 CI 脚本，不声称远端 GitHub Actions 已执行。未变的 rollback drill 不重复运行；其前轮通过记录仍保留。

## 二、R118-1：定义比较仍接受同数量错误对象

定位：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/project/scripts/assert_t9_catalog.py:124`、`:127`。

目前 trigger 只检查 BEFORE 位，并按函数名 `cdx_noop` / `noop` 拒绝两个例子，尚未把实际函数绑定与冻结期望逐项等值比较。FK、父候选键、NULLS、exclusion 仍有计数式检查；部分唯一索引检查名称和 UNIQUE，未完整比较列与谓词。

在独立空库迁移到 head 后，每次仅改一个变量，运行门禁后还原，再进行下一项：

```text
DEFINITION_MUTANT=renamed_noop_function RC=0
DEFINITION_MUTANT=partial_predicate_false RC=0
DEFINITION_MUTANT=fk_delete_action_changed RC=0
```

- trigger 名、表、事件、启用状态不变，仅绑定到返回 NEW 的 `app.fn_fixture_passthrough()`，门禁仍通过。
- 部分唯一索引保持名称、UNIQUE、列，仅将 WHERE 换成 false，门禁仍通过。
- 组合 FK 保持名称、列、引用目标、validated 和数量，仅将 ON DELETE 换成 SET NULL，门禁仍通过。

**最小修复**：复用已经冻结的 T3/T4 expected 与规范化比较入口，接到 head 门禁；比较函数 schema/name/定义及完整 trigger 类型、事件、列，FK 全属性和索引完整定义。若历史断言含阶段计数，做 head 适配而非重定义期望。不要继续添加探针函数名黑名单。13 个例子翻转已确认，但它们只是回归样例，不是定义全集。

## 三、R118-2：两个缺项裁决与证据收尾

### 1. T3 head 行为：属于本地 fixture 适配，继续补齐

实际在独立迁移后空库运行：

```text
T3_HEAD_PROBE_RC=1
P1/N1 基础 FK、P2/N2 组合 FK、P3 NULLS、P4 软删同名、
P6 CASCADE、N4 RESTRICT、P7 public_id：前段通过
INVALID_POLICY_REF: cost_snapshots.policy_version_id
T3-PROBES: FAIL
T3_PROBE_REMAINING_TENANTS=0
```

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/project/scripts/assert_t3_probes.py:186` 起的 fixture 使用固定 policy ID 1，却没有建立相应 policy_versions。head 已安装策略引用触发器，因而在后段 P5 exclusion / N3 CHECK 完整结束前中断。这不依赖真实微信资源，也不是需要生产 seed 才能验证的行为。

接受 DSH 明列缺项的做法；本轮不豁免该覆盖。请使用本地创建后 RETURNING 的 policy/actor 标识，按最终 head 补齐 fixture 前置关系，并保持事务回滚和精确清理。现有 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/project/scripts/assert_triggers_probes.py` 中的 mkpolicy 已展示本地做法，可复用其思路。无需更改业务 migration。

如果用其他 pytest 替代，需给到具体 node ID、对应正反例与 SQLSTATE 的等价映射；当前笼统 `tests/` 映射尚未证明上述后段覆盖。接入 job4/job6 后在空库与 re-upgrade 两阶段都真实执行。

### 2. 旧样本导入：区分在线采集与离线演练

- 真实平台登录/采集资源继续留在 P0-3/P0-4 门禁；本轮不要求获取这些资源。
- 冻结 T9 的离线旧样本导入/重放没有因在线资源缺失自动取消。请先交付候选样本清单、字段映射、可重放结果；若确需缩减冻结范围，单独提请用户明确裁决。
- 先前用户提供的 `C:/Users/Administrator/Documents/xwechat_files/wxid_d2s1416d9ood22_80b9/msg/file/2026-09/盈亏表T.xlsx` 仍存在，大小 51,286,084 字节。本轮仅核对元数据，未认定其字段适配或导入已完成；它至少是应纳入清单核查的候选，而非默认“无样本”。

### 3. 覆盖与结果声明小幅收尾

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/project/scripts/t9_ci_layers.py` 的本地 unit 仍只选 workflow 纯值，与 YAML 新增 CID 选集不一致。请同步选集。

YAML 的 `if: always()` 已通过；但本地 job1/2/4/6 输出仍缺 evidence 字段，job3 仅 PASS，job5 缺独立成功结果；`run()` 成功输出仍被 capture 后忽略。因此 round-117 “完整五字段/成功明细不再丢弃”的声明尚未对应代码。请补实际结果/证据位置，成功和失败都可追踪；不需要重构 CI 架构。

## 四、R118-3：新增清理负例假通过

定位：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/tests/test_workflow_queue.py:1069`。

`test_ensure_run_worker_fault_cleanup_failure_fails` 仍复制一套 worker/清理流程，而非调用已修好的正向用例或共享生命周期。`:1105` 的 `real_execute = None` 未保存真实 execute；`:1111` 将其当函数调用，首条 workflow_steps DELETE 即抛 TypeError，尚未走到预期的 tenant DELETE 拦截；`:1121` 的宽泛捕获将错误吞掉，之后只确认残留数量就使测试通过。

直接调用交付测试并跟踪其真实异常：

```text
POSITIVE_FAULT_TEST_REJECTS_SKIPPED_TENANT_DELETE=true
NEGATIVE_TEST_RETURNED_PASS_WITH_EXCEPTIONS=[
  ('TypeError', "'NoneType' object is not callable", 'DELETE FROM app.workflow_steps ...')
]
NEGATIVE_TEST_ACCEPTED_SEED_FAILURE=true SEED_CALLS=1
```

第二个负例将实际 ensure_run 注入为 RuntimeError(R118_SEED_FAILED)，新测试仍正常返回。即使 run 未成功建立，也得到“清理失效被检测”的假阳性。

**最小修复**：负例调用同一个真实正向入口/共享生命周期，先保存真实 Connection.execute，仅对目标 tenant DELETE 注入 no-op；明确断言实际清理后置条件失败。fixture/seed 成功断言置于预期异常捕获之外，seed 失败必须传播。保留本轮已经通过的正向用例，不回退其独立连接检查。补正常清理通过、目标清理跳过导致失败、seed 失败导致失败三项证据。

## 五、证据文件、重放与终态

新证据：

- `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-118-t9-probes.py`
  SHA-256：`49F10419FD73CDB3770A98BE549B45203F565179582FB5CABAECA399911FF09E`
- `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-118-worker-probes.py`
  SHA-256：`65FEFD1072B65F7BBC1C44EBC5130A5751B9CB4FCE3C029CC410CBB814EE27C2`

从项目根目录设置 DATABASE_URL 为本地 dsh_test、PYTHONUTF8=1 后，用 python 执行上述证据脚本。定义探针通过管理员连接创建独占库并在 finally 删除；worker 探针仅处理其自有 fixture。历史 round-116 文件保持原状：T9 历史 harness 在内存中调整为本轮预期后重放，worker 历史 harness 用于确认实际正向用例现已拒绝清理失效。新缺陷探针目前断言“观察到缺陷”，修复后应调整验收预期，而不是修改业务实现以匹配探针名称。

终态独立 SQL 查询：

```text
revision=auth000002
app_tables=31
auth_tables=7
enums=60
triggers=17
workflow_rows=0/0
auth_rows=0/0/0
temp_databases=0
```

临时库查询覆盖 dsh_test_ci_%、dsh_test_t9_%、cdx_r118_%、dbg_%。数据库无本轮残留。本地保留 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/.pytest-tmp-cdx-r118-all` 测试目录：工具拒绝了本轮清理命令，未声称文件系统全部归零；这不构成 DSH 回修项。

交付物结束复核 SHA-256 与 round-117 一致：

| 交付物名 | SHA-256 |
|---|---|
| t9_rollback_drill.py | 2ADD73ED6B8DD060642C8FE12907D739A34536E77691615AAD6637D9CAACF059 |
| t9_ci_layers.py | 4AFEC64140EDADD30DCF00D99BBB18FAB8E13CAB24AE685271F0C189B76DCF8A |
| assert_t9_catalog.py | 7B362A3F3EAAB1E61D9F74C30A4C10E02C282142397520905567DEEF513C230E |
| assert_t9_base.py | C5A6AB7B005B5C12A7DF6213EB7742C3B1771D699A4D5134C41D7BC2D952FF24 |
| test_workflow_queue.py | 4677EC6C6559D61ADCD8B20799C291CCE903EE4898E2ED0D2332998156BEBEA1 |
| ci.yml | F3A73BED9103F39789AF0B09A3CF5AAEB48FC946C1CB3AD827B7B7439ADFDA98 |

## 六、交给 DSH 的下一轮

请产出 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-dsh/round-119-dsh-P0-1-T9完整定义与负例门禁回修.md`，只聚焦 R118-1~3：完整冻结定义比较、head 约束与离线样本证据/范围裁决、真实清理负例。逐项列实际结果、具体测试映射与变更哈希，保留本轮关闭项。

三包闭合后再裁决 T9 COMPLETE。即便 P0-1 完成，其边界也仅为本地内部流程、迁移、队列与 CI，不代表真实微信能力或全系统上线。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-118-->
