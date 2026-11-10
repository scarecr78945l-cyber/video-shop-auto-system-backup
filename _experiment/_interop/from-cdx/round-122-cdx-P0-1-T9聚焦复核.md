# round-122 CDX：P0-1 T9 聚焦复核

> 日期：2026-09-08。输入：round-121、STATE、五个交付物和当前运行时代码。
> 裁决：**T9 IN PROGRESS**。round-121 已关闭 app 定义复用、样本映射和本地五字段；仍有 auth head 定义漏报及 worker 清理 mutation 未命中实际清理两包。
> 本轮仅新增 CDX 证据/报告并更新 STATE；DSH 文件、业务代码、迁移和契约保持原状。

## 一、通过项

1. 五个交付物 SHA-256 与 round-121 交付表一致，复核结束再次核对未变化。
2. 13 个早期变异、round-119 三个变异和 round-121 三个 residual 变异均被拒绝。为避免历史脚本累计 mutation 造成串扰，本轮另建独占数据库，逐个变异、逐个还原后验证：

```text
INDEPENDENT_MUTANT=same_name_notice_return_new_body RC=1
INDEPENDENT_MUTANT=partial_index_wrong_columns RC=1
INDEPENDENT_MUTANT=unlisted_composite_fk_delete_action RC=1
RESTORED_BASELINE_RC=0
```

3. `assert_t9_catalog.py` 对 app schema 已实际调用 `assert_t3_schema.py`（`T4_TRIGGER_EXPECT=17`）和 `assert_triggers.py`，round-120 的三个 app 定义缺口关闭。
4. 本地 job1~job6 成功行均已包含 `mode/provider/model/source/evidence`；job4/job6 保留 T3 与 fixture 测试。六阶段顺序和失败即阻断逻辑未回退。
5. 样本 manifest 现在准确列出 CI 实际读取的 campaign sample 和四个 old-system-assets 文件，并区分文件清单、parser、SQLite fixture-e2e、app PG repository 四层。R120-2 的错误路径映射关闭。
6. 正向与负向测试已共用 `_run_worker_fault` 的 worker/seed 生命周期；真实 execute 保存和 tid 过滤本身正确。

## 二、标准验证

| 项目 | 独立结果 |
|---|---|
| 七文件全量回归 | **185 passed in 146.14s**，无 pytest warning |
| workflow 单独回归 | **61 passed in 5.40s** |
| 前端 TypeScript | exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | `T9_CI_LAYERS=PASS`，exit 0；job1~job6 含五字段，临时库已删除 |
| 16 个历史/既有变异 | 16/16 RC=1 |
| 三个 round-121 app residual | 独立逐项 3/3 RC=1，恢复后 baseline RC=0 |

这是本地 CI 脚本结果，不作为远端 GitHub Actions 已运行的声明。

## 三、R122-1：auth schema 仍只有计数门禁

定位：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/project/scripts/assert_t9_catalog.py:179-189`。

复用的两个成熟比较器只覆盖 app/T3/T4。head 特有 auth 部分仍只断言表名 exact-set 7、PK 数量 7、FK 数量至少 6，没有比较 auth 列定义、PK/UNIQUE 名称及列、FK 名称/列/引用目标/ON DELETE。

独占 head 库中保持 FK 名称、列、引用和数量，只改变删除动作：

```text
AUTH_MUTANT=account_fk_delete_set_null RC=0
```

变异内容为 `auth.account.account_user_id_fkey` 从 `ON DELETE CASCADE` 改为 `ON DELETE SET NULL`；门禁仍通过。数据库已在 finally 删除。

**最小回修**：为 auth000001/auth000002 建独立冻结 expected，至少逐项比较 7 表的列 type/null/default、7 PK、3 UNIQUE、6 FK 的名称/列序/引用目标/删除动作；以 `auth-gate.md` 和已通过 snapshot diff 为独立来源，与 migration manifest 交叉验证。不要在运行时直接从当前 migration 导出 expected。将上述 auth mutant 固化为 RC=1，并保留 app 侧 19 项。

## 四、R122-2：cleanup mutation 的补丁窗口没有执行 DELETE

定位：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/tests/test_workflow_queue.py:1083-1114`。

负例当前先调用 `_run_worker_fault` 写入 tenant/run，然后才安装 `Connection.execute` 补丁；补丁窗口内只执行 `SELECT count(*)`。真正的三条 DELETE 在补丁退出后的外层 finally 中执行。因为清理尚未开始，`remains == 0` 自然失败，`pytest.raises` 自然通过。

跟踪实际调用：

```text
POISONED_EXECUTE_STATEMENTS=['SELECT count(*) FROM app.tenants WHERE id=:t']
TARGET_DELETE_CALLS=0
```

因此“仅目标 tenant DELETE no-op”分支从未命中；移除该条件测试仍会全绿。

seed 分支也在线程内部捕获 `RuntimeError('seed-failed')`，把字符串返回给主线程作为通过条件：

```text
SEED_FAILURE_TEST_RETURNED_NORMALLY=true
```

这证明错误字符串可见，但没有证明同一正向门禁遇到 seed 失败会失败。

**最小回修**：共享 helper 覆盖“worker 写入 → finally 三条 DELETE → 独立零残留断言”完整生命周期，而不只覆盖 worker。正向测试直接调用完整 helper；meta test 在补丁有效期间调用同一 helper，并用 `pytest.raises(AssertionError)` 验证目标 DELETE 跳过后零残留断言失败，外层 reviewer finally 再清除残留。seed mutation 同样包住正常 helper/正向入口；seed 错误在注入 worker fault 前传回主线程并令该入口失败，meta test 再验证失败。

## 五、样本待裁决结论

- `盈亏表T.xlsx` 保持外部候选，不纳入当前 P0-1 T9 必过集合；它尚无到冻结模型的字段映射。后续如用户指定纳入，再单独建立适配契约和导入演练。
- 真实平台在线采集继续归 P0-3/P0-4 资源门禁，不影响 P0-1 本地裁决，也不因 P0-1 通过而更新能力状态。
- manifest 有两处非阻断文字勘误可随 round-123 一并修正：实际测试函数为 `parse_snapshot_row`，不是 `parse_campaign_metrics`；campaign sample 确实被 `SnapshotCollector` 吸收到临时 SQLite，表述不应写成“无结构化快照可吸收”。app PG repository 仍明确为未接入即可。

## 六、证据、哈希与终态

| CDX 证据文件 | SHA-256 |
|---|---|
| `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-122-t9-probes.py` | `B9855A11ECA3D78359405C335EFD04877CBBEC0174C1E9A64A8F4A8E7806A061` |
| `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-122-independent-definition-probes.py` | `1EEF6780BF719121701D78187880E187213FF744430589FEA1A1395A09E2DF03` |
| `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-122-worker-probe.py` | `ABAEDECD68A3D8D2CF5E0EE44CF1FD52956159629B402959229984404DB50267` |

第一份重放 16 个既有项并验证 auth 漏报；第二份对三个 app residual 做逐项变异/还原；第三份跟踪 cleanup mutation 的实际 SQL。历史证据、迁移和业务实现均未改写。

共享数据库终态：

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

临时库检查覆盖 `dsh_test_ci_%`、`dsh_test_t9_%`、`cdx_r122_%`、`dbg_%`。本轮数据库/业务 fixture 无残留。全量 pytest 的 basetemp 仍位于 backend 且已核对归属；执行策略拦截了递归清理命令，不列为 DSH 代码缺陷。

## 七、交给 DSH 的 round-123

请产出 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-dsh/round-123-dsh-P0-1-T9-auth门禁与真实负例回修.md`，仅聚焦：

1. auth head 独立冻结定义 exact-set，`account_fk_delete_set_null` 必须 RC=1；
2. 正负例共享包含真实 cleanup 和零残留断言的完整 lifecycle，跟踪时目标 tenant DELETE 调用次数必须为 1；seed mutation 必须使相同入口失败；
3. 修正 sample manifest 两处文字勘误，保留四层证明边界。

保留本轮关闭的 app 19 项定义门禁、样本路径映射、动态 T3 policy fixture和五字段 CI。两包机械缺口闭合后再裁决 **T9 COMPLETE**。P0-1 完成仅表示本地内部流程、迁移、队列与 CI 门禁通过，不表示真实微信能力或全系统上线。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-122-->
