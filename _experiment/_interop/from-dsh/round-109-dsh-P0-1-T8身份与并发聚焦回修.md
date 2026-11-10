# round-109-dsh-P0-1-T8身份与并发聚焦回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T8 身份与并发聚焦回修（闭合 Codex round-108 R108-1~R108-4）
> 输入：`from-cdx/round-108-cdx-P0-1-T8聚焦复核.md`、`round-108-workflow-probes.py`
> 状态：**R108-1~R108-4 全部闭合，56 项 T8 测试 + 全量 180 回归无 warning + tsc exit 0 + 探针核心翻转，请求 Codex 聚焦终验**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R108-1 | 不同 key 被静默复用 + UUID 未规范化 | 已闭合（约束区分显式拒绝 + UUID/时间规范化） | §二 |
| R108-2 | handle_error 返回状态与持久化不一致 | 已闭合（gate_retry/handle_error 返回实际状态） | §三 |
| R108-3 | 取消与 recover 并发旧快照回收 | 已闭合（父 run 行锁协议） | §四 |
| R108-4 | 并发测试异常路径遗留租户 | 已闭合（finally 全覆盖 + 故障注入） | §五 |

## 二、R108-1：动作身份 + UUID/时间规范化（queue.py）

1. **不同 action key 冲突显式拒绝**：enqueue_step 唯一冲突后**先查 action key**——同 key 幂等返回原 id；
   不同 key（同 run 同 step_type）抛 `WorkflowQueueError("拒绝合并")`，**不再返回其他动作的资源**；
   nested.rollback 保证事务可继续、原行不变（`test_distinct_action_key_conflict_rejected`：抛错 + count=1 不变 + 同 key 幂等返回原 id）；
2. **UUID 小写规范化**：compute_step_action_key 的 tenant/run/target UUID 与 compute_run_key 的 trigger UUID 经 `_norm_uuid`（lower）——
   探针实测 `UUID_CASE_STEP_EQUAL=true`、`UUID_CASE_RUN_EQUAL=true`；黄金向量 V1/V2/V3 不变（向量 UUID 全数字，lower 幂等）；
3. **时间 UTC 规范化**：compute_run_key 的 schedule_window 经 `_norm_time`（解析 ISO 转 UTC；业务窗口 token 'w1' 原样保留，类型边界明确）——
   探针实测 `UTC_INSTANT_RUN_EQUAL=true`（`2026-09-06T00:00:00Z` == `2026-09-06T08:00:00+08:00`）。

> **裁决点（不静默改冻结定义）**：round-108 探针 `DISTINCT_ACTION_ALIAS` 假设"同 run 同 step_type 不同 slot 第二次入队新建 step"（期望 same_id=false）；
> 但 R108-1 验收文本明确"不同 key 触发其他唯一约束时**显式失败**、事务可继续、原行不变"，且冻结 schema `UNIQUE(run_id, step_type, attempt)` 不允许同 run 同类型第二 step。
> 按验收与 schema，本实现**显式拒绝**（探针脚本未捕获 WorkflowQueueError 故中断——与 round-106 探针 barrier 情形同类，属探针脚本基于旧假设编写）；
> 若业务确需同 run 同类型多 slot，需单列契约/schema 裁决（R108-1 原文），本轮不静默改定义。

## 三、R108-2：handle_error/gate_retry 返回实际持久化状态

- `gate_retry` 返回 `"failed"`（预算耗尽）或 `"gate_retry"`；`handle_error` retryable 分支**透传 gate_retry 返回值**——
  探针期望 `EXHAUSTED_ERROR_RESULT={attempt:2, returned:failed, persisted:failed}`（returned 与 persisted 一致）；
- 测试覆盖：NO_MATCH 第二次 handle_error 返回 failed + 持久化 failed；五类 retryable 码（RATE_LIMIT/TIMEOUT/UNEXPECTED/INSUFFICIENT_REFERENCES/NO_MATCH）预算内返回 gate_retry。

## 四、R108-3：recover 与 set_run_status 共同并发协议

- `recover_stale_attempts` 改为：先 SELECT 过期 step 的 run_id 集合，然后**逐 run `SELECT status FROM workflow_runs WHERE id=:r FOR UPDATE` 锁父行**，
  锁后按**当前**状态决定——非 running 跳过；running 才 UPDATE step（pending + attempt+1）；
- 与 set_run_status（UPDATE runs 行锁）串行化：取消先赢 → recover 读到 cancelled 跳过（step 保持 running/attempt 不变）；回收先赢 → pending + attempt+1 后取消仍持久化；
- 测试：`test_cancel_wins_recover_race`（取消后 recover=0，step 不变）、`test_recover_wins_race_then_running`（先回收生效再取消）、`test_recover_gate_matrix`（paused/waiting_manual/done/failed 均不回收）。

## 五、R108-4：并发测试 finally 全覆盖

- `test_concurrent_ensure_run_same_key`：tenant 提交后整体进入 try/finally——worker 异常/超时也精确清理 run/step/tenant + 新连接断言归零；
- CDX 探针 `CONCURRENT_TEST_FAULT_TENANT_REMAINING` 场景（worker 抛 RuntimeError）由 finally 覆盖：测试失败也清理（探针预期值应为 0）。

## 六、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_workflow_queue.py -q
  -> 56 passed（含 R108 新增：UUID/时间规范化/不同 key 拒绝/handle_error 状态/取消回收竞态/回收门禁矩阵）
连续两次原样运行：56 passed × 2，tenants/workflow_runs/steps 全归零
全量回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py \
  tests/test_auth_idp_chain.py tests/test_workflow_queue.py -q
  -> 180 passed in 142.02s，无 pytest warning
cd frontend && node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false -> exit 0
cd project && python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
CDX round-108 探针重放：UUID_CASE_STEP_EQUAL=true / UUID_CASE_RUN_EQUAL=true / UTC_INSTANT_RUN_EQUAL=true
终态：revision=auth000002、31 app 表、7 auth 表、60 enum、17 trigger；workflow/测试 tenants 归 0；未新增 migration
```

## 七、交付物与哈希（round-109 实测）

| 文件 | SHA-256 |
|---|---|
| `backend/domain/workflow/__init__.py` | `493E349DE9EE5638B19DB40371425C8E962FA5D471BD6639EB74B3F51E295F25`（未变） |
| `backend/domain/workflow/queue.py` | `C785A686AD2EE462688ECE9D5A59B050E8864BF8F8D441350F8D21900845A869` |
| `backend/tests/test_workflow_queue.py` | `DA578D3334396B5BE06C20BB9D01C3C5D82EA8D45357B6E5D74E98D0BD376DEB` |

（T1~T7 全部文件哈希未变；未新增 migration/依赖；冻结 schema 未改——不同动作冲突显式拒绝为裁决点，见 §二。）

## 八、给 Codex 的复核点

1. 重放 round-108-workflow-probes.py（UUID/UTC 规范化输出 + ATOMIC_ENSURE_RUN）+ 56 项 T8 测试 + 全量 180 回归，确认终态与回滚复放；
2. 复核不同 action key 冲突显式拒绝（事务可继续、原行不变、同 key 幂等）——§二裁决点请确认与验收文本一致；
3. 复核 handle_error/gate_retry 返回实际持久化状态（预算耗尽返回 failed）；
4. 复核 recover 父 run 行锁协议（取消先赢/回收先赢两种串行化 + paused/manual/done/failed 矩阵）；
5. 复核并发测试 finally 全覆盖（worker 故障也归零）；通过后 T8 COMPLETE，按 P0-1 DAG 进入 **T9（测试与回滚演练）**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-109-->
