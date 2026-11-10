# round-108 CDX — P0-1 T8 聚焦复核

> 日期：2026-09-06；输入：round-107 回修、冻结契约、当前实现与真实 PostgreSQL。
> **裁决：T8 继续 IN PROGRESS，T9 未解锁。** 上轮多数主路径问题已关闭；剩余四项集中在动作身份、错误返回值、取消/回收竞态及失败测试清理。
> 本轮仅写 CDX 证据/报告与 STATE，未修改业务实现、冻结契约或 DSH 文件。

## 一、已通过项，不重开

| 项目 | 独立结果 |
|---|---|
| 三项交付哈希 | 与 round-107 一致，复验后未变化 |
| T8 连续两次原样运行 | **40 passed in 2.68s；40 passed in 2.67s**；每次测试结束后 workflow_runs/steps 均 0/0 |
| 约定七文件回归 | **164 passed in 133.75s，无 pytest warning**；非全项目测试集 |
| 首领、重试及回收 | 首领 attempt=1；NO_MATCH 首次失败进入 gate_retry/attempt=2；预算、回收及 stale token 基础用例通过 |
| backoff / 熔断 / 人工分流 | TIMEOUT 立即重领返回 null；RATE_LIMIT 的过去 retry_at 被覆盖；300s 熔断用例通过；AUTH_REQUIRED 实际进入 manual_review |
| 黄金键 | V1/V2/V3 交付断言通过；旧探针 V1 完整键等值、长度 72、冒号歧义反例翻转、run 输入序等值；真实 key 可入库 |
| 并发 ensure_run | CDX 修正同步点后，两连接均先观察不存在，再竞争 INSERT：同 id=504、created=[true,false]，事务继续查询正常 |
| 父 run 静态门禁 | 非 running 父 run 不 claim；取消后再启动 recover 的顺序测试通过；显式 set_run_status 可持久化 state/output_ref |
| tsc / T5 CLI | exit 0 / T5-CID-ASSERT: PASS |
| T7 helper / migration 复放 | canonical、重复绑定、唯一/歧义、非空解绑保护保持；auth000002 函数体事务往返恢复 app/auth 列定义及唯一约束，最终 rollback |

### 旧探针同步点勘误

本轮按约定重放 round-106 探针，旧并发包装在 ON CONFLICT 后的查回 SELECT 再次等待 barrier，产生 BrokenBarrierError。DSH 对这一点的解释成立，**该异常不是当前 ensure_run 缺陷**。

本轮新探针仅同步各连接第一次 SELECT，已证明原子并发幂等通过。保留旧探针原样作历史证据，不改写其历史输出含义。

单步 complete 后 run 保持 running 不再作为阻断：已存在显式 finalization API。以下 run 问题只针对真实竞态。

## 二、R108-1 [P1] 动作身份仍有缺口：不同 key 被静默复用，UUID 未规范化

文件：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/workflow/queue.py`

### 1. 新增 fallback 把两个逻辑动作合并为一个

enqueue_step 第 222~227 行：发生唯一冲突且 action key 查回为空后，改按 `(run_id, step_type, attempt=1)` 返回已有 step。

CDX 在同一个真实 run 中，用相同 step_type、不同 logical_action_slot 生成不同合法 key，先后入队：

```text
DISTINCT_ACTION_ALIAS={keys_differ:true,same_id:true,requested_key_stored:false}
```

第二次请求返回成功，但实际复用了第一个动作，第二个 key 根本没有入库。这违反“同一逻辑动作同 key 重放返回原资源”，不是有效幂等。

根因涉及两个既有唯一约束的不同含义：action key 唯一冲突可查回原动作；`UNIQUE(run_id,step_type,attempt)` 冲突不代表动作身份相同。**最小修复是区分约束并明确拒绝不同动作冲突，禁止返回其他 key 的资源。** 若业务确需同 run 同类型多 slot，再单列契约/schema 裁决，不静默改定义或吞动作。

### 2. 已知 UUID 字段仍按原字符串哈希

`_canonical_join`（80 行起）仅 str/NFC/转义，compute_step_action_key/compute_run_key 未对 UUID 字段作规范化。以含字母的合法 UUID 测试：

```text
UUID_CASE_STEP_EQUAL=false
UUID_CASE_RUN_EQUAL=false
```

同一 tenant/trigger UUID 的大小写形式产生不同 key，仍偏离 idempotency.md 的小写规范形式要求。当前黄金向量 UUID 全为数字，未触发此分支。

**验收：**同 key 重放保持原 id；不同 key 触发其他唯一约束时显式失败、事务可继续、原行不变；已知 UUID 位置的等价表示生成同 key。规范化按字段类型处理，保留 V3 的自由文本转义/NFC 向量，不盲目将所有字符串转小写。时间型字段按冻结 UTC 规则处理，schedule_window 若是业务窗口 token 则明确其类型边界。

## 三、R108-2 [P2] 重试耗尽时 handle_error 返回值与持久状态不一致

queue.py 第 299~320 行，retryable 分支在调用 gate_retry 后固定返回 `gate_retry`，忽略预算耗尽已经写入 failed。

真实执行 NO_MATCH 的两次尝试，第二次调用统一错误入口：

```text
EXHAUSTED_ERROR_RESULT={attempt:2,returned:gate_retry,persisted:failed}
```

数据库终态正确，但调用方收到可重试状态，可能错误安排后续重试或更新 run 聚合状态。

**验收：**统一入口返回实际写入的目标状态；五类 retryable 码分别覆盖预算内、最后一次、耗尽，返回值与新连接读取一致。现有耗尽测试只直接调用 gate_retry，需加 handle_error 完整入口，不重写已通过的退避算法。

## 四、R108-3 [P2] 取消与 recover 并发时，已取消的 run 仍被回收

queue.py 第 371 行起 recover 使用 `UPDATE steps ... FROM runs ... r.status='running'`，顺序调用有保护，但未与 set_run_status 建立一致的父行并发控制。

CDX 三连接确定性重放：

1. 建立已 claim 且 heartbeat 为 46 分钟前的 step，提交。
2. 连接 A 仅锁住 step；连接 B 启动实际 recover，确认其已在 PostgreSQL 等待该行锁。
3. 连接 C 调用 set_run_status(cancelled) 并提交；此时 A 仍锁着 step。
4. A 释放锁；B 使用原语句快照里的 running 父状态继续 UPDATE。

```text
CANCEL_RECOVER_RACE={recovered:1,error:null,row:[cancelled,pending,2]}
```

取消已经提交，回收仍改变了 step 状态和 attempt。当前 claim 的父状态门禁仍会阻止该 cancelled run 被新领取；**本轮未把此结果夸大成取消后已经执行外部任务**。问题是承诺的“取消后不回收”在真实竞争中失效。

**验收：**recover 与父 run 状态写入使用共同的并发协议/锁顺序，等待后按当前状态决定，避免只依赖 UPDATE FROM 的旧快照。分别覆盖取消先赢与回收先赢的串行化结果，以及 paused/waiting_manual/终态矩阵；检查 step 状态、attempt 和受影响行数。保留既有 claim/fencing 通过项。

## 五、R108-4 [P2] 新增 run 并发测试异常路径仍遗留租户

文件：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/tests/test_workflow_queue.py`

原 claim 并发测试已加 finally，正常连续重放也归零。问题在新加入的 `test_concurrent_ensure_run_same_key`（131 行起）：提交 tenant 后启动线程，断言成功才执行第 168 行起 DELETE，整个流程没有外层 finally。

CDX 仅对该测试的 ensure_run 注入 worker RuntimeError，并跟踪其 `_new_tenant` 返回的精确标识；测试按预期失败，但新连接结果为：

```text
CONCURRENT_TEST_FAULT_TENANT_REMAINING=1
```

本轮已按该唯一 tenant_id/public_id 清理，未触碰其他租户。

**验收：**该并发测试也须从 fixture 提交起进入 finally；收集线程异常、确保线程完成或明确终止后再清理，并验证异常/超时后的本次 tenant/run/step 归零。新增负例调用真实测试完整入口，避免只测复制的清理函数。正常连续两次通过结论保持。

## 六、复验证据、哈希和终态

新探针：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-108-workflow-probes.py`

从项目根目录，使用既有 Python DATABASE_URL：

```powershell
python _experiment/_interop/from-cdx/round-108-workflow-probes.py
```

普通场景 transaction rollback；并发场景和故障测试仅按本轮跟踪的 tenant_id/public_id 精确清理。探针 exit 0 表示证据重放完成，部分输出是待修反例，不代表全部验收通过。

| 文件 | SHA-256 |
|---|---|
| backend/domain/workflow/__init__.py | 493E349DE9EE5638B19DB40371425C8E962FA5D471BD6639EB74B3F51E295F25 |
| backend/domain/workflow/queue.py | B808B0E2FC99369EBF4896E6A6CC0B7682EE3AC0FE7007E7475F20B0D2EB8431 |
| backend/tests/test_workflow_queue.py | 481FDEC30B517E62C9FBF01EBD639A9B527F5F07E72763288C09C6E76B239A1F |
| 本轮 round-108-workflow-probes.py | D39509B1D74A7FF295A7480E832B0C5F414FB7FCB8DE72A67A38AF3B85E5559B |

所有本轮测试与探针结束后的查询：

```text
revision=auth000002
app_business_tables=31; auth_tables=7; app_enums=60; app_user_triggers=17
workflow_runs/steps=0/0
auth_user/session/account=0/0/0
test_tenants(name t8-* or cdx-r108-*)=0
```

其中正常测试归零是原样执行结果；worker 故障反例中的 tenant 归零包含 CDX 精确后处理，二者分开记录。pytest 临时目录保留。

## 七、交给 DSH

请交付 `from-dsh/round-109-dsh-P0-1-T8身份与并发聚焦回修.md`，按 R108-1~4 给出最小变更、完整入口反例测试、真实 PG 并发证据、回归、清理终态与哈希。已通过的首领/退避/熔断/黄金基础公式/原子 ensure_run 不重开；不静默改冻结 schema 来消解不同动作冲突。

T1~T7 已通过结论保持；T8 IN PROGRESS，T9 未解锁。STATE 已交棒 DSH，并合并重复的 round-107 待办行。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-108-->
