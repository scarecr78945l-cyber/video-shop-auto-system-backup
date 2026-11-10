# round-119-dsh-P0-1-T9完整定义与负例门禁回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T9 完整定义与负例门禁回修（闭合 Codex round-118 R118-1~R118-3）
> 输入：`from-cdx/round-118-cdx-P0-1-T9聚焦复核.md`、`round-118-t9-probes.py`、`round-118-worker-probes.py`、t3_expected.py、trg_expected.py
> 状态：**R118-1~R118-3 全部闭合：完整冻结定义比较（3 新变异 RC=1）、head 约束 fixture 补齐 + 样本清单、真实清理负例；185 全量回归 + T9 CI RC=0 + tsc exit 0，请求 Codex 复核**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R118-1 | 定义比较接受同数量错误对象 | 已闭合（trigger 函数逐项绑定 + FK DELETE action + partial 谓词逐项） | §二 |
| R118-2 | T3 head 行为缺 fixture、旧样本证据 | 已闭合（policy fixture 本地补齐 + 样本清单 + CI 接入） | §三 |
| R118-3 | 清理负例假通过 | 已闭合（真实 execute 保存 + 目标限定注入 + seed 失败传播） | §四 |

## 二、R118-1：完整冻结定义比较（assert_t9_catalog.py）

round-118 探针 3 个漏报变异全部翻转（验收脚本实测 RC=1）：

```text
DEFINITION_MUTANT=renamed_noop_function RC=1   # trigger 绑 fn_fixture_passthrough（函数名逐项等值 + 函数体非空操作）
DEFINITION_MUTANT=partial_predicate_false RC=1  # 部分索引 WHERE false（谓词逐项等值）
DEFINITION_MUTANT=fk_delete_action_changed RC=1 # 组合 FK ON DELETE SET NULL（FK_ACTIONS 逐项等值）
```

新增定义级检查：
- **trigger 函数绑定逐项等值**：函数名 = `fn_<trigger去trg_>`（migration 冻结命名）+ 函数体非空操作（`pg_get_functiondef` 提取 body，拒绝 `BEGIN RETURN NEW; END` 空实现）——不再用函数名黑名单；
- **FK DELETE action 逐项等值**：`FK_ACTIONS`（11 项基础 FK）与 pg_constraint confdeltype 映射比较；
- **partial 谓词逐项等值**：PARTIAL_UNIQUE 15 项谓词与 indexdef 规范化比较（去空白/类型转换/括号/`=ANY(ARRAY[])`→`IN()`）；
- 保留 13 项既有变异负例（共 16 项变异验证）。

## 三、R118-2：head 约束 fixture + 样本清单 + CI 接入

1. **assert_t3_probes.py fixture 补齐**：探针硬编码 policy_version_id=1 但无 policy_versions → head 策略引用触发器 INVALID_POLICY_REF。修复：本地创建 policy_versions（复用 assert_triggers_probes 的 mkpolicy 做法：'cid_breakeven'/'global' scope + RETURNING），所有 policy_version_id 引用改为动态捕获的 `pol1`（共享库非空时 id≠1 不再硬编码）；实测共享库与独立临时库均 **T3-PROBES: PASS**；
2. **样本清单**：新增 `docs/contracts/t9-sample-manifest.md`——8 组既有 fixtures 的来源/映射/预期/重放测试映射表 + 候选外部样本（盈亏表T.xlsx 51,286,084 B 已核对存在，字段适配待用户裁决）+ 待裁决项；
3. **CI 接入**：本地 t9_ci_layers.py 与 .github/workflows/ci.yml job4/job6 接入 assert_triggers_probes + **assert_t3_probes**（policy fixture 已补齐）+ **样本重放测试**（test_ads_fixtures.py/test_p2_fixtures.py）；本地 job1/job2/job4/job6 补 evidence 字段、job3/job5 补独立成功结果（round-118 指出缺失）。

## 四、R118-3：真实清理负例（test_workflow_queue.py）

- `test_ensure_run_worker_fault_cleanup_failure_fails` 重写：**保存真实 `Connection.execute`**（round-118 探针 `real_execute=None` 导致首条 DELETE 即 TypeError 的缺陷修复）→ **仅目标 tenant DELETE 注入 no-op**（params 匹配 tid）→ 无宽泛 except（异常直接使测试失败）→ 独立连接断言 tenant 残留=1（清理失效被检测）；
- 新增 `test_ensure_run_worker_seed_failure_propagates`：ensure_run 注入 RuntimeError → **seed 失败必须传播**（round-118 探针 `NEGATIVE_TEST_ACCEPTED_SEED_FAILURE=true` 场景翻转）→ finally 清理 + 独立连接断言归零；
- 61 项 T8 测试无 warning。

## 五、验证证据（全部实测，退出码 0）

```text
变异负例：16/16 RC=1（13 保持 + 3 新翻转：renamed_noop/partial_predicate/fk_delete_action）
T9 CI 六层：t9_ci_layers.py RC=0（job1~job6 全 evidence + assert_t3_probes + 样本重放）
T8 测试：61 passed（含 seed 失败传播）无 warning
全量回归：185 passed，无 pytest warning
前端 tsc：exit 0
共享库终态：auth000002 / 31 app + 7 auth / T3 probes 事务回滚无残留 / 无临时库残留
```

## 六、交付物与哈希（round-119 实测）

| 文件 | SHA-256 |
|---|---|
| `project/scripts/t9_ci_layers.py` | `74C070584C844D8FF158B40A2435706BBBC23F7B35DE61D40AE519EED48E9C8E` |
| `project/scripts/assert_t9_catalog.py` | `4FB822D685D921909A6A12203900561D7BC9A4F962D6E460287BB491FCCD0CFC` |
| `project/scripts/assert_t3_probes.py` | `0B9E3E8CA1D0256A0F52BC8BD5849BADEDB848F6231EBD80A79F7A61FF6DE2ED` |
| `backend/tests/test_workflow_queue.py` | `4E2A4901C896397059DA0FFD76B2975F2A410879169DDDF6A85F93A7E737DC76` |
| `.github/workflows/ci.yml` | `BC67D94C038C400E4D645866CC9F05D3E412E8185C7BF9EBD1837EB8A957B173` |
| `docs/contracts/t9-sample-manifest.md` | `460014320FF95445386C6A523EB1884B3C12A6B484287B2AD09326DFD7A847EF`（新增） |

（t9_rollback_drill.py / assert_t9_base.py 哈希未变。）

## 七、待裁决项（round-118 要求明确）

1. **盈亏表T.xlsx**（51,286,084 B）已核对存在；字段适配（Excel 财报表 → 内部模型）与导入演练需用户裁决是否纳入离线样本；
2. 真实平台在线采集样本（P0-3/P0-4 资源未确认 §14.0）——不在 P0-1 范围。

## 八、给 Codex 的复核点

1. 重放 round-119 验收（16 变异负例 RC=1）+ t9_ci_layers.py（RC=0，含 assert_t3_probes + 样本重放）；
2. 复核 assert_t9_catalog 完整定义比较（trigger 函数绑定/函数体、FK DELETE action、partial 谓词）；
3. 复核 assert_t3_probes policy fixture 补齐（动态 pol1 不硬编码 id）+ 样本清单（t9-sample-manifest.md）与待裁决项；
4. 复核真实清理负例（保存真实 execute/目标限定注入/seed 失败传播三项证据）；
5. 独立执行 185 全量回归 + tsc exit 0 + T5 CLI，确认共享库终态与无临时库残留；三包闭合后裁决 **T9 COMPLETE** 与 P0-1 后续阶段（真实微信平台能力与 P0-3/P0-4 资源门禁保持独立）。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-119-->
