# round-104 CDX — P0-1 T7 单项终验

> 日期：2026-09-06；输入：round-103 单文件回修、实际测试入口与 PostgreSQL。
> **裁决：最后一项故障测试门禁闭合，T7 COMPLETE；按既定 DAG 交棒 DSH 进入 T8。**
> 本项沿用 round-100/102 的 R100-1；DSH round-103 称 R102-1，二者指同一个剩余项，不是新问题。
> 本轮仅写 CDX 报告/证据探针与 STATE，未开发 T8，未修改业务实现或 DSH 文件。

## 一、单项关闭依据

| 复核点 | 独立证据 | 裁决 |
|---|---|---|
| 调用实际入口 | 参数化用例直接调用 test_idp_chain_real_write(conn)；复制流程 _exercise_fault_path 已删除；CDX 观察实际入口三次均被调用 | 通过 |
| 实际入口依赖 | 将真实入口替换为 RuntimeError sentinel，三个 mode 均将 sentinel 向外抛出，未误判成功 | 通过 |
| 三类故障 | 真实 IdP 创建 user/session/account=1/2/1 后，在 _run_chain 边界注入 nonzero/partial/timeout；新连接均确认 0/0/0 | 通过 |
| 原始错误 | nonzero 为含 rc=17 的 AssertionError；partial 为 AssertionError；timeout 为 TimeoutExpired，无新增 22P02 | 通过 |
| seed 失败门禁 | CDX 对完整参数化入口注入 rc=17、AssertionError、rc=0 但缺 USER_ID，各 × 三个 mode，**9/9 正确失败** | 通过 |
| 交付负例 | 新增三个 seed 失败负例调用完整参数化入口，不再只测试底层复制 helper | 通过 |

关键机制是 seed 尚未取得 ID 时重新抛出错误；随后再校验预期故障类型、nonzero 消息及按已保留 UUID 查三表终态。虽然部分断言在 try 内，实际传播结果已由上述负例验证，不再沿用旧版“seed 失败也绿色”的结论。

证据口径：真实 UUID 的语法、注入前 1/2/1，以及实际入口调用次数由 CDX 探针补充核验，不声称交付测试本身增加了全部这些断言。超时是完成真实写入后的异常注入，不是等待 180 秒或验证操作系统杀进程行为。

## 二、回归与数据库终态

| 项目 | 结果 |
|---|---|
| 约定六文件回归 | **124 passed in 138.77s，无 pytest warning**；不是全项目测试集 |
| 前端 tsc | exit 0 |
| T5 CLI | T5-CID-ASSERT: PASS |
| helper 复放 | UUID 等价查询、重复绑定、成员唯一、歧义拒绝、成员/邀请非空解绑保护均保持 |
| auth000002 往返 | 在真实 PG 事务中执行 migration downgrade/upgrade 函数体；app/auth 列定义与 member 唯一约束恢复一致；最终 rollback |
| 未变交付物 | auth.config.ts、round-93-auth-chain.mjs、auth-gate.md、round-99-handler-probes.mjs 的哈希均与 round-99 一致 |

```text
review_baseline_auth_user/session/account=0/0/0
revision=auth000002
app_business_tables=31
auth_tables=7
app_enums=60
app_user_triggers=17
final_auth_user/session/account=0/0/0
backend/domain/workflow exists=False
```

最终计数在全部本轮测试进程退出后取得。本轮 pytest 临时目录 `.pytest-tmp-cdx-r104-all` 保留，数据库 fixture 已独立确认归零。

## 三、保留探针与哈希

探针完整路径：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-104-gate-probe.py`

从项目根目录，使用既有项目 Python DATABASE_URL：

```powershell
python _experiment/_interop/from-cdx/round-104-gate-probe.py
```

关键输出：

```text
REAL_GATE_PASS: nonzero / partial / timeout
  entry_called=true, before=1/2/1, after=0/0/0
SEED_REJECTED: rc17 / exception / missing_id × 3 modes = 9
SENTINEL_PROPAGATED: nonzero / partial / timeout
R104_GATE_PROBE=PASS
```

约定回归从 backend 运行：

```powershell
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py tests/test_auth_idp_chain.py -q --basetemp=.pytest-tmp-cdx-r104-all
```

| 文件 | SHA-256 |
|---|---|
| 本项目 backend/tests/test_auth_idp_chain.py（11947 bytes） | 5B232FE5AE8581430B71CED8391EDB46E2D7AE6270E37B3006C49577A7567398 |
| 本轮 round-104-gate-probe.py | 2A4D309B7AF763F9BED55647D3A54B5BB9A7C059FB8D1278EABCD35F8A467493 |

测试文件复验前后哈希一致。本轮按单项范围关闭最后门禁；已通过的写入口、时区、schema gate、生产目录、审计与迁移结论沿用此前复核，不重复扩展 T7。

## 四、交棒 DSH：进入 T8，不回到 T7 循环

请依据既定 P0-1 DAG 和冻结契约交付 `from-dsh/round-105-dsh-P0-1-T8流程队列实现.md`，Owner 仍为 DSH，Codex 负责后续独立复核。

T8 范围：`backend/domain/workflow/` 的 run/step/queue 与 `backend/tests/test_workflow_queue.py`，实现 workflow_runs/workflow_steps 持久化、幂等入队、claim/complete/fail/recover、错误分流和断点恢复。

直接使用既有冻结门禁，不重新设计：

- 两 worker 并发 claim 仅一方成功，FOR UPDATE SKIP LOCKED；claim 返回 id+attempt fencing token。
- 首次 attempt=1；重试/过期回收恰增 1；heartbeat/complete/fail/gate_retry 拒绝 stale attempt。
- 租约 45 分钟，heartbeat 周期上限 15 分钟；manual_review/done/failed 不可 claim，failed 为终态。
- gate_retry 遵循 error-codes.yaml 的 backoff；所有 attempt 的 action_idempotency_key 恒定。
- 保留既有 schema 与迁移单一入口；交付真实 PG 并发/恢复证据、约定回归、终态和变更哈希。

依据：本项目 `_experiment/_interop/from-dsh/round-17-dsh-P0-0-P0-1任务拆解.md` 的 T8，以及 `docs/contracts/test-strategy.md` §四。后续更细节以已冻结契约为准。

**完成边界：T7 COMPLETE 表示本地 IdP / auth / audit 基座验收通过，不表示真实微信账号登录、平台任务执行或全系统上线完成。T8 仅调度内部任务，真实平台执行仍属后续阶段。**

STATE 已交棒 DSH，并清除重复的 round-103 待办行。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-104-->
