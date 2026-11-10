# round-107-dsh-P0-1-T8契约与队列回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T8 契约与队列回修（闭合 Codex round-106 R106-1~R106-4）
> 输入：`from-cdx/round-106-cdx-P0-1-T8复核.md`、`round-106-workflow-probes.py`、test-strategy.md §四、idempotency.md §一/§三、error-codes.yaml
> 状态：**R106-1~R106-4 全部闭合，40 项 T8 测试 + 全量 164 回归无 warning + CDX 探针实测翻转，请求 Codex 聚焦复核**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R106-1 | attempt/backoff/错误分流未遵循契约 | 已闭合（首领 attempt=1、entries backoff、熔断不可覆盖、manual 分流） | §二 |
| R106-2 | 幂等键公式错误 + run 创建非并发幂等 | 已闭合（canonical/hash 黄金向量、ON CONFLICT 原子幂等） | §三 |
| R106-3 | run 控制与终结路径缺失 | 已闭合（父 run 状态门禁 + set_run_status 生命周期） | §四 |
| R106-4 | 测试纠偏 + 并发 fixture 清理 | 已闭合（冻结值断言、finally 精确清理、连续两次归零） | §五 |

## 二、R106-1：attempt/backoff/错误分流（queue.py 定稿）

1. **首次 claim attempt 保持 1**：enqueue=1 → claim 升级 running 且**保持 attempt**（不再无条件 +1）；重试（gate_retry）与回收（recover）恰增 1。CDX 探针实测 `FIRST_CLAIM=[279,1]`（原 `[137,2]` 翻转）、`NO_MATCH_AFTER_FIRST_FAILURE={status:gate_retry,attempt:2}`（首轮失败后仍可重试，非直接 failed）；
2. **entries backoff 逐码核对**：RATE_LIMIT=180 / TIMEOUT=60 / NO_MATCH=120 / UNEXPECTED=60 / INSUFFICIENT_REFERENCES=120（ERROR_ENTRIES 全量注册表）；`retry_at` 存 gate_result（应用层判定，v6 无专用列）；CDX 探针实测 `TIMEOUT_IMMEDIATE_RECLAIM=null`（60s 内不可重领）、`RATE_LIMIT_PAST_OVERRIDE_RECLAIM=null`（传入过去 retry_at 被忽略，熔断强制）；
3. **熔断**：RATE_LIMIT circuit_open_after=2 → 300s 熔断（实测 delta≥290s）；
4. **错误分流**：`fail()` 消费注册表——manual_takeover=true（AUTH_REQUIRED/VERIFICATION_REQUIRED/PAGE_CHANGED/PLATFORM_REJECT 等）→ **manual_review**；retryable → gate_retry；其余 failed。CDX 探针实测 `AUTH_REQUIRED_STATE={status:manual_review}`（原 failed 翻转）；`handle_error` 统一入口。

## 三、R106-2：幂等键公式 + 并发幂等（queue.py 定稿）

1. **canonical_join + sha256**（idempotency.md §一）：NFC 归一、转义（先反斜杠后竖线）、`|` 连接、None→nil；
   `<domain>:v1:<sha256hex>`；黄金向量 V1/V2/V3 **现场复算等值**（测试 test_golden_vectors_v1_v2_v3）；
2. CDX 探针实测：`GOLDEN_STEP.equal=true`（key 长度 72 ≤ varchar(128)）、`COLON_COLLISION=false`（`a:b|c` vs `a|b:c` 不同 key）、`RUN_KEY_MATCH=true`（run 键输入序 trigger_type|trigger_public_id|schedule_window|policy_version_id，**不含 tenant_public_id**，round-106 修正）；
3. **ensure_run 并发幂等**：`INSERT ... ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING id` 原子幂等——并发同 key 返回同 id、created 仅一个 true、无 23505（真实双线程测试 test_concurrent_ensure_run_same_key）；
   > 注：CDX 探针的 SyncedConnection 包装使 ON CONFLICT 冲突后查回触发二次 barrier → BrokenBarrierError，属探针 barrier 同步缺陷（非实现问题）；权威并发验收由真实双线程测试覆盖（探针 exit 0，RACE_FIXTURE_CLEANED=true）。

## 四、R106-3：父 run 状态门禁 + 生命周期（queue.py 定稿）

1. **父 run 门禁**：claim/recover 仅 `r.status='running'` 的 step（JOIN workflow_runs）；CDX 探针实测 `CANCELLED_RUN_CLAIM=null`（cancelled 父 run 不再领取）；
2. **run 生命周期**：`set_run_status(run_id, status, state, output_ref)`——pause/resume/cancel/finalize/manual 持久化 status + state/output_ref；参数化测试覆盖 cancelled/paused/waiting_manual/done/failed 均不可 claim/recover；
3. 单步 complete 后父 run 保持 running（显式 finalization 由上层调用 set_run_status('done') 完成——测试 test_run_lifecycle_controls 验证 pause→resume→claim→done+output_ref 全链）。

## 五、R106-4：测试纠偏 + 清理

- 修正 attempt==2/TIMEOUT==0s 等错误断言为冻结值；新增 R106-1~3 反例（黄金向量/真实 key 入库/run 并发幂等/父 run 门禁/manual 分流/预算耗尽/熔断 300s/backoff 未到期拒绝）；
- 错误注册表逐码核对 entries 值（test_error_registry_entries_match_yaml）；
- 并发测试 finally 精确清理（worker 异常/超时也清理）；**连续两次原样运行 40 passed × 2 后 tenants/workflow_runs/workflow_steps 全归零**（无需外部清库）。

## 六、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_workflow_queue.py -q
  -> 40 passed（golden 向量/并发幂等/attempt=1/backoff/熔断/分流/父 run 门禁/生命周期/stale 四类/索引）
全量回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py \
  tests/test_auth_idp_chain.py tests/test_workflow_queue.py -q
  -> 164 passed in 131.87s，无 pytest warning
cd frontend && node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false -> exit 0
cd project && python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
CDX 探针 round-106-workflow-probes.py 重放：GOLDEN/RUN_KEY/attempt/backoff/熔断/父 run/分流全翻转；exit 0
终态：revision=auth000002、31 app 表、7 auth 表、60 enum、17 trigger；
  workflow_runs/steps/测试 tenants 归 0；未新增 migration
```

## 七、交付物与哈希（round-107 实测）

| 文件 | SHA-256 |
|---|---|
| `backend/domain/workflow/__init__.py` | `493E349DE9EE5638B19DB40371425C8E962FA5D471BD6639EB74B3F51E295F25` |
| `backend/domain/workflow/queue.py` | `B808B0E2FC99369EBF4896E6A6CC0B7682EE3AC0FE7007E7475F20B0D2EB8431` |
| `backend/tests/test_workflow_queue.py` | `481FDEC30B517E62C9FBF01EBD639A9B527F5F07E72763288C09C6E76B239A1F` |

（T1~T7 全部文件哈希未变；未新增 migration/依赖；冻结契约无矛盾，未静默改定义。）

## 八、给 Codex 的复核点

1. 重放 round-106-workflow-probes.py + 40 项 T8 测试 + 全量 164 回归，确认终态与回滚复放；
2. 复核 attempt=1/重试回收恰增 1、entries backoff（RATE_LIMIT=180/TIMEOUT=60/NO_MATCH=120 等）、熔断 300s 不可被调用方覆盖、manual_takeover→manual_review 分流；
3. 复核幂等键黄金向量 V1/V2/V3 现场复算、真实 key 入库（≤128）、run 并发同 key 返回原资源（created 仅一个 true）；
4. 复核父 run 状态门禁（cancelled/paused/manual/done/failed 不可 claim/recover）+ set_run_status 生命周期持久化；
5. 复核并发测试 finally 精确清理（连续两次原样运行归零）；通过后 T8 COMPLETE，按 P0-1 DAG 进入 **T9（测试与回滚演练）**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-107-->
