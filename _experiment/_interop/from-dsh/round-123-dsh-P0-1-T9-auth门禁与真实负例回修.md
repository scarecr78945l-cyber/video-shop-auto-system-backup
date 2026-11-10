# round-123 DSH：P0-1 T9 auth 门禁与真实负例回修

> 日期：2026-09-08。输入：`from-cdx/round-122-cdx-P0-1-T9聚焦复核.md`（R122-1~R122-3）。
> 裁决声明：**T9 IN PROGRESS（不回修不标记 COMPLETE）**。本轮聚焦关闭 R122-1（auth 定义门禁漏报）、
> R122-2（cleanup mutation 补丁窗口未命中真实清理）、R122-3（manifest 两处文字勘误）。
> 未进入 T8/下一阶段；真实微信平台能力仍属 P0-3/P0-4 门禁。

## 一、交付物与哈希

| 文件 | SHA-256 |
|---|---|
| `project/scripts/auth_expected.py` | `65C5AA4624278A27DE2E70C0819712EC4FDE48C4A501DFC1DC0F9ED81A255B7B` |
| `project/scripts/assert_t9_catalog.py` | `3E366B2800F7B93D05A08F1DA79A039C19ED952C7EF8A1FFFB3A103020914257` |
| `project/scripts/t9_auth_mutant_drill.py` | `215275E8D7B538451A8EB0E018BDB629657115468C3385880478F8CFC3F173F4` |
| `backend/tests/test_workflow_queue.py` | `7F0FB72B11CECDDD7AA7FCFABE34D1A23E5FB361D383253AF58FAEE8AB4772E0` |
| `docs/contracts/t9-sample-manifest.md` | `82F6C2362D25EF43F82205558822416E0AB9C48D94E15E2A29340CAD7667D27C` |

来源规则（R122-1 要求）：auth expected 来自 `auth-gate.md` snapshot（hash `81E2AD7D...`）+ `auth000001/000002`
migration manifest，**不从当前运行时导出**（杜绝「迁移与自身一致」假通过）。

## 二、R122-1 闭合：auth head 独立冻结定义 exact-set

新建 `project/scripts/auth_expected.py`（独立冻结 expected）与 `assert_t9_catalog.py` 内 auth 定义级 exact-set：

- **列定义**：7 表（user/session/account/verification/organization/member/invitation）逐列比较
  `(type, nullable, default)`；类型两边规范化（`timestamp with time zone`→`timestamp`，
  `character varying`→`text`）；default 做字面比较（`now()`/`false`/`'active'::text`/`gen_random_uuid()`）。
- **PK**：7 个 `_pkey(id)` 名称+列 exact-set。
- **UNIQUE**：统一合并唯一约束 + 唯一索引源（`user_email_unique`/`session_token_unique`/
  `organization_slug_unique` + account 索引 `account_issuer_accountId_uidx` + member 组合
  `member_organization_id_user_id_uidx`），名称+列 exact-set。
- **FK**：6 个名称/列序/引用目标/ON DELETE 逐项比较。

修复了三处定义漏报根因：

1. 列类型两侧规范化不一致（仅 expected 侧 `timestamp with time zone→timestamp`，DB 侧保持原形）→ 两侧都压短名。
2. uuid PK `id` 列 DB 默认 `gen_random_uuid()`（迁移生成）在 expected 里记 `None` → 改成 `gen_random_uuid()`
   且 default 升级为字面比较（`id` 缺默认的变异现在必须失败）。
3. UNIQUE 检查首轮无 `idx_map` 回退即把「仅索引」的 account/member 组合判定 mismatch 后，第二轮未清空列表，
   残留误报 → 统一 one-of(约束,索引) 单源覆盖，删除冗余首轮。

**真实负例固化（`t9_auth_mutant_drill.py`）**：独立临时库 upgrade head → 基线 `assert_t9_catalog` RC=0 →
对 `auth.account.account_user_id_fkey` 施加 `ON DELETE CASCADE → SET NULL` 变异 → `assert_t9_catalog` 必须 RC=1
（FK action 变化被捕获）→ 还原 CASCADE 后 RC=0 → finally 清理临时库。实测：

```text
[STEP1] upgrade head OK
[STEP2] 基线 assert_t9_catalog  PASS rc=0
[STEP3] 变异 account_user_id_fkey=ON DELETE SET NULL 被捕获 -> PASS rc=1
[STEP4] 还原 CASCADE 回归  PASS rc=0
T9_AUTH_MUTANT_DRILL=PASS
```

> 说明：修复过程中发现 `assert_t9_catalog.py` 的 FK action CASE 有误——PG `confdeltype` 的 `'n'`=SET NULL、
> `'a'`=NO ACTION，原实现把 `'n'` 误映射为 `NO ACTION`（`'a'` 才应映射 NO ACTION，原还多了个不存在的 `'s'`）。
> 该错误会让 SET NULL 变异显示为 NO ACTION 而「仍失败但标签错」；已修正为
> `'a'→NO ACTION, 'n'→SET NULL, 'c'→CASCADE, 'r'→RESTRICT, 'd'→SET DEFAULT`，变异 drill 现在正确断言 `SET NULL`。

共享库 `assert_t9_catalog.py` 实测 PASS（定义级）：

```text
[PASS] auth 列定义 exact-set（7 表）  mismatch=[]
[PASS] auth PK exact-set（7 名称+列）  mismatch=[]
[PASS] auth UNIQUE exact-set（5：3 约束 + account idx）  mismatch=[]
[PASS] auth FK exact-set（6 名称/列/引用/action）  mismatch=[]
[PASS] alembic_version = auth000002
T9-CATALOG-ASSERT: PASS
```

## 三、R122-2 闭合：正负例共享完整 lifecycle + 补丁命中真实清理

`_run_worker_fault` 扩展为**全生命周期探针**（不只覆盖 worker）：

1. worker 线程内真实并发入口 `ensure_run` 执行并提交（worker-error 写入 run/step fixture；seed-failure 让
   ensure_run 抛错并捕获 propagate）；
2. **finally 三表清理**（workflow_steps / workflow_runs / tenants 按 tenant_id 精确 DELETE）移入 worker 内；
3. 线程后**独立新连接零残留断言**（run=0 && tenant=0），失败即抛 AssertionError。

返回值改为 `(worker_error 列表, cleanup ok 布尔)`。正向 `test_ensure_run_worker_fault_cleans_fixture` 直接调用
完整 helper 并断言错误串与清理无异常；seed 正例 `test_ensure_run_worker_seed_failure_propagates` 走同 helper
`fault="seed-failure"` 断言 `["seed-failed"]` 且 `cleanup_ok`。

负例 `test_ensure_run_worker_fault_cleanup_failure_fails`：**在调用 helper 之前**植入
`Connection.execute` 补丁，补丁仅对 `DELETE FROM app.tenants WHERE id=:t`（目标 tenant）做 no-op，其余放行；
测例包裹 `pytest.raises(AssertionError)` 调用同一 helper；补丁必须真实命中目标 tenant DELETE **恰好 1 次**
（证明包裹的是真实 finally 清理而非仅 SELECT）。实测：

```text
3 passed, 58 deselected in 1.01s     （三个 worker-fault 正/负/seed 用例）
61 passed in 3.93s                   （test_workflow_queue.py 全文件）
```

跟踪口径：补丁生效窗口内目标 tenant DELETE 调用次数固定为 1，且不做该 no-op 时（正向）清理后零残留断言自然
通过；做 no-op 时该断言抛 `AssertionError` 被 `pytest.raises` 捕获——此即「同一正向门禁遇到清理失败会失败」的
真实证明（修正 round-122 指出的「补丁窗口仅 SELECT、DELETE 0 次就能假通过」）。

## 四、R122-3 闭合：sample manifest 文字勘误

`docs/contracts/t9-sample-manifest.md`：

- parser 标识 `parse_campaign_metrics` → `parse_snapshot_row`（`backend/ads/report.py`，测试
  `test_ads_fixtures.py` 实际使用）；保留 old-system `wechat_ads.py::parse_campaign_metrics` 仅为历史来源注记。
- 证明层级更正：`campaign_report_sample.json` **确实经 `SnapshotCollector.run_once` 吸收到临时 SQLite**
  （独立 tmp_path 库），表述不再写「无结构化快照可吸收」；明确 **app PG repository 仍未接入**（尚无写往 app
  PG 业务表的 repository 路径，为后续真实平台样本预留）。
- 四层证明边界（文件清单 / parser / SQLite fixture-e2e / app PG repository）保持不变；`盈亏表T.xlsx` 仍为外部
  候选、不纳入 P0-1 T9 必过集合；真实平台资源仍属 P0-3/P0-4。

实测：`test_ads_fixtures.py + test_p2_fixtures.py` = **11 passed**（manifest §三 与 CI job4/job6 一致）。

## 五、标准回归

| 项目 | 本轮回溯结果 |
|---|---|
| 七文件全量回归（cid/secret/actor/seed/integration/idp_chain/workflow_queue） | **185 passed**（共享库），无 pytest warning |
| workflow 单独回归 | **61 passed** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | `T9_CI_LAYERS=PASS`，exit 0；job1~job6 含五字段 evidence，临时库已删除 |
| R122-1 auth mutant | `T9_AUTH_MUTANT_DRILL=PASS`（SET NULL 变异 RC=1，还原 RC=0） |

## 六、共享库终态与说明

共享库终态（清残留后）：

```text
revision=auth000002
app_tables=31（+alembic_version）=32
auth_tables=7
enums=60 类型 / 267 labels
triggers=17
workflow_runs=0 / workflow_steps=0 / tenants=0
auth_user=0 / session=0 / account=0
temp_databases=0（含 dsh_test_ci_%/dsh_test_t9_%/dsh_test_authm_%/cdx_r122%/dbg_%）
```

> 本轮全量回归后首次检查发现 1 条 auth.user 残留（disabled + 会话/账号）；
> 独立重跑 `test_auth_idp_chain.py + test_auth_integration.py`（14 passed）后各表 0 残留，确认测试自身清理
> 闭合；残留已清除并复核 auth=0/0/0。列为交接观察项——若 CDX 复跑发现 auth 行非零，请指出具体用例以便定位。

## 七、保留项（本轮未回退）

- app 侧 19 项变异门禁（16 历史 + 3 residual）保持 RC=1——assert_t9_catalog 本轮改动仅限 auth 区块，app
  仍复用 `assert_t3_schema.py`（T4_TRIGGER_EXPECT=17）与 `assert_triggers.py`，无定义回退。
- 动态 T3 policy fixture（本地 pol1 不硬编码 id）、样本路径映射、五字段 evidence CI 均保持。
- `盈亏表T.xlsx` 保持外部候选；真实平台在线采集仍归 P0-3/P0-4。

## 八、交给 CDX 的 round-124

请复核 R122-1~R122-3 三包机械闭合后，再裁决 **T9 COMPLETE**。P0-1 完成仅表示本地内部流程、迁移、队列与
CI 门禁通过，不表示真实微信能力或全系统上线。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-124-->