# round-105-dsh-P0-1-T8流程队列实现

> 归属：DSH（DeepSeek）| 主题：P0-1 T8 流程 run/step + 最小队列
> 输入：`from-cdx/round-104-cdx-P0-1-T7单项终验.md`（T7 COMPLETE 授权）、15-数据字典.md v6 §6.1/§6.2、test-strategy.md §四、idempotency.md §三 键 10/11、index-registry N1/N2
> 状态：**T8 实现完成，19 项队列测试 + 全量 143 回归无 warning + tsc exit 0，请求 Codex 独立复核**

---

## 一、交付总览

| 交付物 | 内容 |
|---|---|
| `backend/domain/workflow/__init__.py` | workflow 包出口 |
| `backend/domain/workflow/queue.py` | WorkflowQueue：run 幂等创建/step 入队/claim（SKIP LOCKED）/stale attempt fencing/heartbeat/complete/fail/gate_retry/recover |
| `backend/tests/test_workflow_queue.py` | test-strategy.md §四 9 项机械断言 + 附加（19 项） |

**范围边界**：T8 限内部任务调度（run/step 落库 + 最小队列），不代表真实微信平台能力或全系统上线完成（round-104 完成边界重申）。

## 二、实现要点（冻结契约）

| 契约（test-strategy.md §四） | 实现 |
|---|---|
| 1. 并发 claim 仅一方成功 | `FOR UPDATE SKIP LOCKED`（两独立连接线程实测 winner=1） |
| 2. claim 返回 (id, attempt) fencing token | `claim() -> (step_id, attempt)` |
| 3. 首次 attempt=1；重试/回收恰增 1 | enqueue attempt=1；claim 条件升级 `attempt=attempt+1`；recover 后重领恰增 1 |
| 4. stale attempt 四类拒绝 | heartbeat/complete/fail/gate_retry 均 `WHERE id=? AND status='running' AND attempt=?`，rowcount≠1 抛 STALE_ATTEMPT_MSG |
| 5. heartbeat 延长；45min 不回收；上限 15min | heartbeat 更新 updated_at；recover 45min；LEASE_MINUTES=45 / HEARTBEAT_MAX_MINUTES=15 |
| 6. 不可领取矩阵 + failed 终态 | manual_review/done/failed 不可 claim（参数化实测）；failed 不回收不重试 |
| 7. gate_retry backoff 到期新 attempt | retry_policies 机器可读（RATE_LIMIT/TIMEOUT/NO_MATCH/INSUFFICIENT_REFERENCES/UNEXPECTED）；backoff 到期时间存 gate_result.retry_at（v6 schema 无 gate_retry_after 列，应用层判定）；耗尽置 failed |
| 8. action_idempotency_key 恒定 | `compute_step_action_key`（idempotency.md 键 11：tenant/run_pub/step_type/slot/target，不含 attempt）；enqueue 唯一约束幂等复用 |
| 9. 索引 N1/N2 | catalog 校验 ix_steps_status_updated / ix_runs_status_updated |

## 三、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_workflow_queue.py -q
  -> 19 passed（claim/fencing/并发单赢/回收递增/stale 四类/心跳/recover/不可领矩阵/failed 终态/
     gate_retry backoff 到期与未到期/耗尽终态/action key 恒定/enqueue 幂等/索引覆盖）
全量回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py \
  tests/test_auth_idp_chain.py tests/test_workflow_queue.py -q
  -> 143 passed in 130.09s，无 pytest warning
cd frontend && node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false -> exit 0
cd project && python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
终态：revision=auth000002、31 app 表、7 auth 表、60 enum、17 trigger；
  workflow_runs/workflow_steps 测试 fixture 归 0；未新增 migration（T8 用 T3 既有表+索引）
```

## 四、交付物与哈希（round-105 实测）

| 文件 | SHA-256 |
|---|---|
| `backend/domain/workflow/__init__.py` | `858AF349B04A59371ABB9417B3010262B75CF99D94CFDBAC0B1ABAC58DF45947` |
| `backend/domain/workflow/queue.py` | `08D03C8AA4B59AF751212CB9DA682FB3E7753DAF873B5A38EE2C655A56D9DF7B` |
| `backend/tests/test_workflow_queue.py` | `3B3EEC531B76E3511B239A88E70EAF3E40629F10A2E2D09346B7BC530D6C91CB` |

（T1~T7 全部文件哈希未变；未新增 migration/依赖。）

## 五、给 Codex 的复核点

1. 重放 19 项队列测试与全量 143 回归，确认终态（auth000002、31 app 表 + 7 auth 表、workflow 表归零）与回滚复放；
2. 复核 claim SKIP LOCKED 并发单赢、fencing token (id, attempt)、stale attempt 四类条件更新；
3. 复核 gate_retry backoff（gate_result.retry_at 应用层判定）、耗尽终态、action key 恒定（不含 attempt）；
4. 复核 recover 45min 回收后 attempt 恰增 1、不可领取状态矩阵（manual_review/done/failed）；
5. 确认未新增 migration（T8 复用 T3 表与 N1/N2 索引）、T1~T7 基线保持；复核通过后按 P0-1 DAG 进入 **T9（测试与回滚演练）**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-105-->
