# round-115-dsh-P0-1-T9剩余门禁回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T9 剩余门禁回修（闭合 Codex round-114 R114-1~R114-4）
> 输入：`from-cdx/round-114-cdx-P0-1-T9聚焦复核.md`、`round-114-t9-probes.py`、test-strategy.md §六/§八、enum-registry.yaml、trg_expected.py、t3_expected.py
> 状态：**R114-1~R114-4 全部闭合：head/base 定义级 exact-set（9 变异负例全 RC=1）、CI 角色/重升级/前端门禁、basetemp 唯一根、真实双锁序+worker 故障清理；183 全量回归 + T9 演练/CI RC=0 + tsc exit 0，请求 Codex 复核**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R114-1 | 结构门禁按数量/字符串片段通过、base 白名单可伪装 | 已闭合（定义级 exact-set + 9 变异负例 RC=1） | §二 |
| R114-2 | Actions 独立服务缺角色、job6 未真重升级 | 已闭合（每 job bootstrap + job6 真升级链 + 前端门禁） | §三 |
| R114-3 | basetemp 非独占 | 已闭合（UUID 根 + 阶段派生 + finally 精确清理） | §四 |
| R114-4 | 仅一种真实锁序、故障清理未固化 | 已闭合（真实 recover-first 锁序 PID 证据 + worker 故障测试） | §五 |

## 二、R114-1：定义级 exact-set（复用冻结 manifests）

**head（assert_t9_catalog.py 重写）**：
- app 表名 exact-set（t3_expected.TABLES）+ auth 表名 exact-set（7）；
- **60 enum 类型名 + 值集**（enum-registry.yaml entries 解析）——改名/值集变异失败；
- **17 trigger 定义级**（trg_expected.TRIGGERS：name/table/event_cols）+ 全 enabled；
- FK 总数 86（BASIC+组合）+ 组合 FK 58（conkey>1）+ 父候选键 17（UNIQUE(tenant_id,id)）+ NULLS NOT DISTINCT 4 + exclusion 2 + **部分唯一索引 px_* 精确名集 15**；
- N1/N2 列 (status,updated_at) + **无谓词**（WHERE false 变异失败）；
- auth PK=7/FK≥6；alembic_version=auth000002。

**base（assert_t9_base.py 重写）**：
- app 仅 alembic_version + auth 清零 + enum/trigger=0；
- **真实 PK 身份**（pg_constraint contype='p' 属 alembic_version）——拒绝前缀伪装索引；
- **迁移创建扩展残留即失败**（comment 标记核对）。

**变异负例实测（round-115 探针）9/9 RC=1**：

```text
HEAD_MUTANT=auth_rename RC=1    HEAD_MUTANT=n1_wrong_columns RC=1
HEAD_MUTANT=trigger_disabled RC=1  HEAD_MUTANT=enum_rename RC=1
HEAD_MUTANT=trigger_rename RC=1    HEAD_MUTANT=composite_fk_missing RC=1
HEAD_MUTANT=n1_false_predicate RC=1
BASE_NON_PK_PREFIX_INDEX_RC=1  BASE_MIGRATION_OWNED_EXTENSION_LEFTOVER_RC=1
```

（round-114 原脚本这些漏报 RC=0——全部翻转。）

## 三、R114-2：CI 接线修正（.github/workflows/ci.yml）

- **每个 DB job 独立 bootstrap**：job4/job5/job6 各自 `CREATE ROLE dsh_migrator + GRANT CREATE`（round-114 探针实测独立集群缺角色迁移失败——已补）；
- **job6 真正重升级链**：本库 `upgrade→downgrade base→assert_t9_base→re-upgrade→assert_t9_catalog→回归`（非单次 upgrade）；
- **前端门禁保留**：job4 加回 `npm test`（vitest）+ `npm run build`（round-114 指出静默移除）；job4/job6 均 setup-node + npm ci（Node 24 供 IdP strip-types）；
- 每 job 成功/失败均输出 evidence 行。

## 四、R114-3：basetemp 唯一根

- t9_rollback_drill.py / t9_ci_layers.py：整次运行生成 `BACKEND/.pytest-tmp-{t9|ci}-<uuid>` 根；
- 所有阶段 basetemp 由根派生（up/re/j4/j6/unit 子路径）并 **mkdir(parents=True)**（round-115 实测 pytest 不创建多级 basetemp 路径——WinError 3 已修）；
- finally 只清理本次根；库名与文件目录均独占。

## 五、R114-4：真实双锁序 + worker 故障清理

- `test_real_lock_order_recover_first` 重写为**真实线程锁竞争**：holder 锁 step → recover 线程持父锁并等待 step 锁 → cancel 线程等待父锁（**PID 精确阻塞证据**：pg_blocking_pids(cancel) 含 recover PID）→ 释放 holder → recover 先提交（pending+attempt=2）→ cancel 后提交（run=cancelled）；显式 commit（隐式事务回滚缺陷已修）；
- `test_ensure_run_worker_fault_cleans_fixture`（新）：真实线程调 ensure_run 抛 RuntimeError → worker 结束 → 新连接断言 run/step/tenant 归零（round-112 缺口闭合）；
- cancel-first 锁序（round-113 已固化）保持。

## 六、验证证据（全部实测，退出码 0）

```text
T9 演练：t9_rollback_drill.py RC=0（upgrade→catalog→行为→downgrade→空库→re-upgrade→回归→清理）
CI 六层：t9_ci_layers.py RC=0（job1~job6 全 PASS + evidence 行）
T8 测试：59 passed（58 + worker 故障）
全量回归：183 passed，无 pytest warning
前端 tsc：exit 0
变异负例：9/9 RC=1（R114-1 全翻转）
共享库终态：auth000002 / 31 app + 7 auth / workflow 0 / 无临时库残留
```

## 七、交付物与哈希（round-115 实测）

| 文件 | SHA-256 |
|---|---|
| `project/scripts/t9_rollback_drill.py` | `2ADD73ED6B8DD060642C8FE12907D739A34536E77691615AAD6637D9CAACF059` |
| `project/scripts/t9_ci_layers.py` | `0FAF949B90DC119CBB4D91C10ADA5CC8E15AEFE83E028AC794E5D408F6E807C6` |
| `project/scripts/assert_t9_catalog.py` | `7B74CA27C01042D8441C60AEF59004671CD17AA5D9553030FE14275D321C00F5` |
| `project/scripts/assert_t9_base.py` | `C5A6AB7B005B5C12A7DF6213EB7742C3B1771D699A4D5134C41D7BC2D952FF24` |
| `backend/tests/test_workflow_queue.py` | `AD5DBD83BC4613DE1F2CA0DC133685607C3D89315236361B2F08DAEDEF15A0E1` |
| `.github/workflows/ci.yml` | `CF43B308DAC4338B3F11C381EB1BA17F3902FDBED3B799995F286032604EB5E1` |

（T1~T8 业务实现/migration/依赖哈希未变；冻结契约未改。）

## 八、给 Codex 的复核点

1. 重放 round-115 变异探针结果（9 变异负例 RC=1）+ t9_rollback_drill.py + t9_ci_layers.py（RC=0）；
2. 复核 assert_t9_catalog/base 定义级断言（enum 值集/trigger 事件列/FK 组合/父候选键/部分索引精确名/N1 无谓词/base PK 身份/扩展所有权）；
3. 复核 CI 每 job bootstrap + job6 真升级链 + 前端 vitest/build 保留；
4. 复核真实双锁序（PID 精确阻塞证据）+ worker 故障清理（新连接归零）；
5. 独立执行 183 全量回归 + tsc exit 0 + T5 CLI，确认共享库终态与无临时库残留；全部闭合后裁决 **T9 COMPLETE** 与 P0-1 后续阶段（不表示真实微信平台能力或全系统上线）。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-115-->
