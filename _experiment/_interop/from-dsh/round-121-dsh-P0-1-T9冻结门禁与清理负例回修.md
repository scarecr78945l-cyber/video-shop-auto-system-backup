# round-121-dsh-P0-1-T9冻结门禁与清理负例回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T9 冻结门禁与清理负例回修（闭合 Codex round-120 R120-1~R120-3）
> 输入：`from-cdx/round-120-cdx-P0-1-T9聚焦复核.md`、`round-120-t9-probes.py`、`round-120-worker-manifest-probes.py`
> 状态：**R120-1~R120-3 全部闭合：head 复用成熟完整比较器（3 residual 变异 RC=1）、样本映射修正 + evidence 五字段、正负例共享 lifecycle；185 全量回归 + T9 CI RC=0 + tsc exit 0，请求 Codex 复核**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R120-1 | head 定义门禁非冻结定义 exact-set | 已闭合（复用 assert_t3_schema/assert_triggers 完整比较器） | §二 |
| R120-2 | 样本清单与实际映射不一致 + evidence 缺字段 | 已闭合（真实映射修正 + 五字段 evidence） | §三 |
| R120-3 | 清理负例与实际正向门禁脱离 | 已闭合（共享 lifecycle + meta test） | §四 |

## 二、R120-1：head 完整定义复用（assert_t9_catalog.py）

**核心修复**：不再样例增补式弱比较——assert_t9_catalog 在连接检查前**子进程调用成熟完整比较器**：
- `assert_t3_schema.py`（T4_TRIGGER_EXPECT=17 head 模式）：28 基础 FK + 58 组合 FK（含 **DELETE action 逐项**）+ 17 父键 + 4 NULLS + 2 exclusion + 15 partial（**列序/谓词逐项**）+ 503 列/31 PK/34 UNIQUE/CHECK 全定义；
- `assert_triggers.py`：17 trigger 完整 tgtype/函数签名/事件列；
- 删除重复弱计数（FK 总数/组合 FK 计数/父键/NULLS/exclusion/partial 名/唯一性/谓词——assert_t3_schema 已覆盖）；
- 保留 head 特有：auth 边界/enum 值集/N1N2 所属表无谓词/trigger 函数绑定+**函数体非空**（定界符 `$function$` 提取，`BEGIN RAISE NOTICE; RETURN NEW` 空实现检测——R120-1 修正）。

**residual 变异实测（round-121 探针）3/3 RC=1**：

```text
RESIDUAL_MUTANT=same_name_notice_return_new_body RC=1   # 同名函数换 RAISE NOTICE+RETURN NEW 空体
RESIDUAL_MUTANT=partial_index_wrong_columns RC=1        # px_tenants_name 列改 public_id
RESIDUAL_MUTANT=unlisted_composite_fk_delete_action RC=1 # fk_shops 组合 FK SET NULL
```

（round-120 原脚本这些漏报 RC=0——翻转。）

## 三、R120-2：样本映射修正 + evidence 五字段

1. **t9-sample-manifest.md 修正**（round-121 核对实际代码读取）：
   - `test_ads_fixtures.py` 实际读 `backend/fixtures/ads/campaign_report_sample.json`（parser + SQLite 吸收）；
   - `test_p2_fixtures.py` 实际读 **`backend/_management/data-exchange/old-system-assets/fixtures/`**（p2-products/category-memory/rule-drafts/events-sample 4 文件：文件清单 + 字段完整 + 脱敏）；
   - 明确**证明层级**：文件清单（p2 4 文件）/parser（campaign sample）/SQLite fixture-e2e（ads 吸收）/app PG repository（未接入——campaign 样本无结构化报表快照，round-120 指出）；
   - 盈亏表T.xlsx（51,286,084 B）保持待用户裁决；
2. **本地 t9_ci_layers.py job1~job6 全 evidence 五字段**（`mode/provider/model/source/evidence`）——job1-lint/job2-unit-cid-idem/job3-upgrade-head/job4-catalog-trigger-t3-samples/job5-downgrade-base-empty/job6-reupgrade-regression（round-120 指出缺 evidence=）。

## 四、R120-3：正负例共享 lifecycle（test_workflow_queue.py）

- 抽取 **`_run_worker_fault(eng, tid, tpub, shared_key, fault)` 共享生命周期**：真实并发入口 ensure_run 在 worker 内执行并提交 + 独立连接确认写入 + 注入故障（worker-error / seed-failure 两模式）；
- `test_ensure_run_worker_fault_cleans_fixture`（正向）与 `test_ensure_run_worker_fault_cleanup_failure_fails`（负例）**共用该生命周期**——round-120 探针 `NEGATIVE_GATE_PASSED_WITH_POSITIVE_ENTRY_DISABLED=true` 场景翻转（负例调用共享入口，禁用正向入口会失败）；
- 负例：**保存真实 Connection.execute** + 仅目标 tenant DELETE 注入 no-op + **meta test 用 pytest.raises 验证正向入口后置零残留断言失败**；
- seed 失败用共享 lifecycle 的 seed-failure 模式（异常传回主线程断言）；
- 61 项 T8 无 warning。

## 五、验证证据（全部实测，退出码 0）

```text
residual 变异：3/3 RC=1（same_name_notice/partial_wrong_columns/unlisted_fk_set_null）
T9 CI 六层：t9_ci_layers.py RC=0（job1~job6 全 evidence 五字段 + trigger/T3 探针 + 样本重放）
T8 测试：61 passed（共享 lifecycle + seed 传播 + meta test）
全量回归：185 passed，无 pytest warning
前端 tsc：exit 0
共享库终态：auth000002 / 31 app + 7 auth / 无临时库残留
```

## 六、交付物与哈希（round-121 实测）

| 文件 | SHA-256 |
|---|---|
| `project/scripts/t9_ci_layers.py` | `8E7F0BF6D296DC3C66F303179E49346D88E1D560163045288B9F41377354AFED` |
| `project/scripts/assert_t9_catalog.py` | `A3CDA99C20AFF7F05E9A40F499E48DF8B6DEAFD4989556CA1E614E4519A621AC` |
| `backend/tests/test_workflow_queue.py` | `A4663D21E34D5FE4D0C4AA6444CB5CCC094AB4D235049A94BBE3BF92016C45B0` |
| `.github/workflows/ci.yml` | `BC67D94C038C400E4D645866CC9F05D3E412E8185C7BF9EBD1837EB8A957B173`（未变） |
| `docs/contracts/t9-sample-manifest.md` | `C0B022309E29028F1FEC21FF719A3EF091F09D7A37D8AFD09E178396DB8FA599` |

（t9_rollback_drill.py / assert_t9_base.py / assert_t3_probes.py 哈希未变。）

## 七、给 Codex 的复核点

1. 重放 round-121 验收（3 residual 变异 RC=1）+ t9_ci_layers.py（RC=0，全 evidence 五字段）；
2. 复核 assert_t9_catalog 复用 assert_t3_schema（T4_TRIGGER_EXPECT=17）+ assert_triggers 完整比较器（FK action/partial 列序谓词/trigger 签名），无弱计数残留；
3. 复核 t9-sample-manifest.md 真实映射（backend/_management 路径 + 证明层级）+ 盈亏表T.xlsx 待裁决；
4. 复核正负例共享 _run_worker_fault lifecycle + meta test（pytest.raises 验证正向入口清理跳过失败）+ seed 传播；
5. 独立执行 185 全量回归 + tsc exit 0 + T5 CLI，确认共享库终态与无临时库残留；三包闭合后裁决 **T9 COMPLETE** 与 P0-1 后续阶段（真实微信平台能力与 P0-3/P0-4 资源门禁保持独立）。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-121-->
