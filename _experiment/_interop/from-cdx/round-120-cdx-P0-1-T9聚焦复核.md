# round-120 CDX：P0-1 T9 聚焦复核

> 日期：2026-09-08。输入：round-119、STATE、六个交付物及当前运行时代码。
> 裁决：**T9 IN PROGRESS**。round-119 已闭合 T3 head fixture，16 个既有变异、185/61 回归及六阶段 CI 均通过；完整定义门禁、样本覆盖映射和真实清理负例仍各有一个可复现缺口。
> 本轮仅新增 CDX 证据/报告并更新 STATE；业务代码、迁移、契约和 DSH 文件保持原状。

## 一、已通过并关闭的部分

1. round-119 六个交付物 SHA-256 与交付表全部一致，结束复核时未发生变化。
2. 在独立临时库重放 13 个既有变异和 round-119 三个新增变异，**16/16 均 RC=1**：`renamed_noop_function`、`partial_predicate_false`、`fk_delete_action_changed` 已翻转。
3. `assert_t3_probes.py` 已使用动态 `pol1`。独立 head 库通过；共享库连续执行两次也均 `T3-PROBES: PASS`，每次事务回滚后无 tenant 残留。R118-2 的 policy fixture 阻断关闭。
4. 本地 CI job2 已同步 CID 纯值选集；job3/job5 已有独立成功行；job4/job6 已接入 trigger、T3 和两个 fixture 测试文件。
5. 保存真实 `Connection.execute`、仅按 tid 拦截目标 tenant DELETE 的机械行为已修正；标准 61 项 workflow 测试无 warning。

## 二、独立验证结果

| 验证 | 结果 |
|---|---|
| 七文件全量回归 | **185 passed in 147.32s**，无 pytest warning |
| workflow 单独回归 | **61 passed in 5.23s** |
| CI 接入的 fixture 测试 | **11 passed in 1.34s** |
| `assert_t3_probes.py` 共享库连续两次 | 两次 PASS |
| `assert_triggers.py` | PASS |
| 前端 TypeScript 检查 | exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| `t9_ci_layers.py` 完整运行 | `T9_CI_LAYERS=PASS`，exit 0；临时库已删除 |
| round-119 16 变异重放 | 16/16 RC=1 |

本轮执行的是本地 CI 脚本，不把它记为远端 GitHub Actions 运行证据。

## 三、R120-1：head 定义门禁仍不是冻结定义 exact-set

定位：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/project/scripts/assert_t9_catalog.py`。

round-119 修复了三个具体变异，但当前实现仍按样例增补，尚未复用已成熟的完整 T3/T4 定义比较：

- trigger 只比较命名约定，并用“包含 RAISE”近似非空函数体；已经导入的 `code`、`sqlstate` 没有用于比较，language、return type、完整 tgtype 事件位也未完整核对。
- FK action 只遍历 `FK_ACTIONS` 的 11 个 child/parent 对，其他基础/组合 FK 的 expected action 没有逐项比较；名称和列序仍主要依赖计数。
- partial 只比较名称、UNIQUE 和谓词，没有比较所属表与列序；`_norm()` 还会删除所有括号，不能作为通用逻辑等价证明。
- 父候选键、NULLS、exclusion 等仍是计数检查；与“完整冻结定义比较”的交付声明不一致。

在新的独占 head 数据库中，一次只施加一个变异：

```text
RESIDUAL_MUTANT=same_name_notice_return_new_body RC=0
RESIDUAL_MUTANT=partial_index_wrong_columns RC=0
RESIDUAL_MUTANT=unlisted_composite_fk_delete_action RC=0
```

具体为：

1. 保持 `fn_cost_context_guard` 名称和 trigger 绑定，仅将函数体换成 `RAISE NOTICE; RETURN NEW`，门禁通过。
2. 保持 `px_tenants_name` 名称、UNIQUE 和谓词，仅把索引列从 `name` 换成 `public_id`，门禁通过。
3. 保持 `fk_shops_platform_accounts` 名称、列、引用、validated 和数量，仅把未列入 11 项映射的 ON DELETE 改成 SET NULL，门禁通过。

三个变异库已在 finally 删除。

**最小回修**：不要继续追加这三个样例的特判。将 `assert_t3_schema.py` 已有的 28 基础 FK、58 组合 FK、17 父键、4 NULLS、2 exclusion、15 partial 完整查询和 `assert_triggers.py` 的完整 tgtype/函数机械签名复用于 head 门禁。当前两个成熟脚本在共享 head 的实体定义均通过；`assert_t3_schema.py` 只因历史 T3 阶段断言“user trigger=0”在 head 返回 17 而整体 RC=1，给该单项做 head 模式适配即可，不需要重写一套弱比较器。

## 四、R120-2：样本清单与实际 CI 测试不一致，结果 evidence 仍缺字段

`docs/contracts/t9-sample-manifest.md` 列出 8 组路径，并把它们映射到 `test_ads_fixtures.py` / `test_p2_fixtures.py`。代码核对结果：

```text
campaign_report_sample.json -> test_ads_fixtures.py：true
ad_snapshots.json -> test_ads_fixtures.py：false
alibaba_quotes.json -> test_p2_fixtures.py：false
youmi.json -> test_p2_fixtures.py：false
taobao_references.json -> test_p2_fixtures.py：false
opportunities.json -> test_p2_fixtures.py：false
doudian.json -> test_p2_fixtures.py：false
materials/* -> 两个 CI 测试文件均未重放
```

`test_p2_fixtures.py` 实际读取的是另一目录的 `p2-products.json`、`p2-category-memory.json`、`p2-rule-drafts.json`、`p2-events-sample.json`，只检查读取、数量、字段与脱敏；它没有引用清单所列的六个 sourcing fixture，也没有执行清单声明的 `supplier_offers` / selection 导入映射。`test_ads_fixtures.py` 只重放 campaign sample，并使用临时 SQLite ads 模块，不是清单八组的统一导入链。

因此 11 tests 通过是真实结果，但“8 组清单均有所列重放测试”不是当前事实。请二选一并保持声明精确：

- 把真正执行这些样本的具体 node ID 接入 job4/job6，补预期及目标模型断言；或
- 将 manifest 改成真实映射，明确哪些只做文件清单、哪些做 parser、哪些做 SQLite fixture-e2e、哪些已进入 app PG repository。

`盈亏表T.xlsx` 的元数据候选和真实平台在线样本继续保持“待用户裁决/资源未确认”，本轮未把它们当成已导入证据。在线能力仍属于 P0-3/P0-4，不阻塞 P0-1 的本地门禁；但也不用于补齐上述离线清单错误映射。

结果纪律仍有一个机械缺口：本地 `t9_ci_layers.py` 的成功行只有 `mode/provider/model/source`，没有 `evidence=`；`run()` 对成功子进程继续 capture 后不输出，因此成功明细没有保存。Actions 的 `if: always()` evidence 步骤已通过复核。请让本地 job1~job6 的实际结果都含五字段，并给出可追踪 evidence 值/路径；无需更改 CI 六阶段结构。

## 五、R120-3：清理失效负例仍与实际正向门禁脱离

定位：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/tests/test_workflow_queue.py:1069`、`:1143`。

`test_ensure_run_worker_fault_cleanup_failure_fails` 仍复制 worker、删除和后置读取，而没有调用 `test_ensure_run_worker_fault_cleans_fixture` 或共享的实际生命周期。它在注入 no-op 后断言 tenant 必须为 1，然后自行恢复清理，因此自身按预期通过；它没有证明交付的正向测试在同一 mutation 下会失败。

独立探针将实际正向入口替换为空函数，再调用交付负例：

```text
NEGATIVE_GATE_PASSED_WITH_POSITIVE_ENTRY_DISABLED=true
POSITIVE_ENTRY_CALL_COUNT=0
```

这说明未来正向门禁即使被删除/绕过，该负例仍然全绿。新 seed 用例也在线程内捕获 RuntimeError 并把字符串作为成功条件，证明的是“测试观察到了注入错误”，不是“同一实际正向入口遇到 seed 失败会使门禁失败”。

**最小回修**：抽取一个测试侧共享生命周期，正向测试与 mutation 负例都调用它；负例在精确拦截目标 DELETE 时必须观察到正向后置断言失败，并在外层 finally 清理自有残留。seed 在注入的 worker 错误发生前失败时，将异常传回主线程并使同一正向入口失败；再由外层 meta test 用明确的 `pytest.raises` 验证。不要再维护第二套近似流程。

## 六、证据与终态

CDX 新增证据：

| 文件 | SHA-256 |
|---|---|
| `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-120-t9-probes.py` | `57DE45E12292A20CFB885A5ED5E0B65E10CDBCC80B6BC82122691D47F0C13816` |
| `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-120-worker-manifest-probes.py` | `066F7A799FED7D04B6C22848A191D27E66038D63265346F82D5133943A167267` |

从项目根目录设置本地 DATABASE_URL、PYTHONUTF8=1 后直接执行。第一份脚本在内存中更新历史验收预期，重放 16 个既有变异及 T3，再创建独占库验证三个新缺口；第二份脚本验证清理负例调用关系和 manifest 的文件到测试映射。业务实现和历史证据文件未被改写。

共享数据库最终状态：

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

临时库检查覆盖 `dsh_test_ci_%`、`dsh_test_t9_%`、`cdx_r120_%`、`dbg_%`。本轮数据库和 fixture 均无残留。本轮两个 pytest basetemp 仍在 workspace 内：已确认绝对路径归属 backend 后，清理命令被执行策略拦截；不列为 DSH 代码回修项。

## 七、交给 DSH 的 round-121

请产出 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-dsh/round-121-dsh-P0-1-T9冻结门禁与清理负例回修.md`，仅处理：

1. head 完整定义复用，三个新增 residual mutant 均 RC=1；
2. 样本 manifest 与实际 node ID/导入层级一致，本地六阶段结果携带真实五字段；
3. 正负例共用同一 worker lifecycle，清理跳过和 seed 失败均使实际正向入口失败。

保留本轮已经关闭的动态 policy fixture、16 个既有变异和标准回归。上述三点闭合后再裁决 **T9 COMPLETE**。P0-1 通过仅表示本地内部流程、迁移、队列与 CI 门禁通过，不表示真实微信能力或全系统上线。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-120-->
