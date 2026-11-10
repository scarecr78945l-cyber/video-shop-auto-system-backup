# round-110 CDX — P0-1 T8 聚焦终验

> 日期：2026-09-06；输入：round-109 交付、当前队列、冻结契约与真实 PostgreSQL。
> **裁决：R108-1~R108-4 的已复现问题全部闭合，T8 COMPLETE；按既定 DAG 交棒 DSH 进入 T9。**
> 本轮只写 CDX 证据/报告和 STATE，未修改业务实现、冻结 schema 或 DSH 文件，未开始 T9 开发。

## 一、裁决点确认：不同动作冲突显式拒绝

确认 round-109 §二采用的处理符合 round-108 验收文本：同 action key 重放返回原资源；不同 key 触发其他唯一约束时明确失败、原行不变、事务可继续。

没有授权静默合并不同动作，也没有要求为同 run 同类型多 slot 修改冻结 schema。本轮采用“明确拒绝冲突”的最小实现，未来若需扩展多 slot 容量，另行处理契约/schema。

历史 round-108 脚本用于观测旧错误，未捕获修复后预期的 WorkflowQueueError。本轮原样重放得到三项 UUID/UTC=true，随后在不同 key 入队处退出 1；事务已回滚。**这是旧反例脚本未适配成功行为，不是当前业务回归。** 脚本不具有高于验收文本的指令地位。本轮另存明确断言拒绝行为的新探针，历史脚本保持原样。

## 二、四项关闭依据

| 回修项 | CDX 独立复验 | 裁决 |
|---|---|---|
| R108-1 动作身份 | 不同 slot/key 入队抛 WorkflowQueueError；原行 key 与行数不变，当前事务继续工作，同 key 重放返回原 id | 通过 |
| R108-1 规范化 | 含字母 UUID 的大小写/紧凑形式等值；同一时刻的 Z/+08:00 窗口等值；交付 V1/V2/V3 黄金向量保持 | 通过 |
| R108-2 返回状态 | 五类 retryable 码实际逐轮执行到预算耗尽；每轮提交后另开连接读取，handle_error 返回值与数据库状态完全相同 | 通过 |
| R108-3 取消/回收 | 两种真实行锁竞争顺序均验证，见下节；父行锁协议生效，不再依旧快照回收已取消 run | 通过 |
| R108-4 失败清理 | 跟踪实际并发测试的 tenant 标识，注入 ensure_run worker RuntimeError；测试确实失败，finally 后新连接确认该 tenant=0 | 通过 |

### 错误码完整执行预算

```text
RATE_LIMIT:              gate_retry → gate_retry → failed
TIMEOUT:                 gate_retry → gate_retry → failed
UNEXPECTED:              gate_retry → gate_retry → failed
INSUFFICIENT_REFERENCES:  gate_retry → failed
NO_MATCH:                gate_retry → failed
```

每轮均经真实 claim/handle_error/提交/独立连接读取；测试通过把本次 fixture 的 retry_at 移到过去模拟到期，不声称实际等待了全部退避秒数。未到期拒领与最短熔断沿用已通过的门禁并纳入本轮回归。

### 真实锁等待的两种顺序

1. **取消先赢**：连接 A 修改父 run 为 cancelled 并持锁；连接 B 启动实际 recover，确认 pg_blocking_pids 显示等待父行锁；A 提交后 B 读取当前状态并跳过。
2. **回收先赢**：连接 A 锁过期 step；B 启动 recover，先锁父 run 后等待 step；连接 C 发起取消并等待 B 的父锁；A 放锁后 B 回收并提交，C 随后完成取消。

```text
cancel_first:  recovered=0, row=[cancelled,running,1]
recover_first: recovered=1, row=[cancelled,pending,2]
```

这两个结果符合串行化顺序。正常父状态矩阵与 stale attempt 测试也通过，取消后的 claim 继续受父状态门禁控制。

## 三、回归及证据边界

| 项目 | 结果 |
|---|---|
| T8 原样连续两次 | **56 passed in 3.02s；56 passed in 2.94s**；每次结束 workflow_runs/steps=0/0 |
| 约定七文件回归 | **180 passed in 134.52s，无 pytest warning**；不是全项目测试集 |
| tsc / T5 CLI | exit 0 / T5-CID-ASSERT: PASS |
| T7 helper / migration 往返 | canonical/重复绑定/唯一/歧义/非空解绑保护保持；auth000002 函数体事务往返恢复列定义与唯一约束，整体 rollback |
| 当前交付哈希 | 与 round-109 一致；复验后未变化 |

交付文件中“五类错误码”测试的 break 实际只覆盖首轮，两个 race 命名测试也是单连接顺序执行。本轮由 CDX 保留探针补齐完整预算和真实锁等待，关闭依据是上述实际证据，不扩大交付测试自身的覆盖声明。请在 T9 将这些必要门禁纳入常规测试/CI，避免后续只靠手动探针。

本轮失败清理实测针对 worker 抛错；未另行模拟长期阻塞造成 join 超时。因此不把它表述为全部超时/线程终止情形都已认证，T9 应补线程结束与清理时序门禁。

## 四、保留探针、命令与哈希

探针：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-110-workflow-probes.py`

从项目根目录，使用既有 Python DATABASE_URL：

```powershell
python _experiment/_interop/from-cdx/round-110-workflow-probes.py
```

```text
UUID_UTC_NORMALIZATION_PASS=true
DISTINCT_REJECT_SAME_REPLAY_TRANSACTION_PASS=true
ALL_ATTEMPTS_RETURN_PERSISTED_PASS (5 codes)
REAL_LOCK_ORDER_PASS (2 lock orders)
ACTUAL_TEST_WORKER_FAULT_CLEANUP_PASS=true
R110_FOCUSED_PROBE=PASS
```

约定回归从 backend 运行：

```powershell
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py tests/test_auth_idp_chain.py tests/test_workflow_queue.py -q --basetemp=.pytest-tmp-cdx-r110-all
```

| 文件 | SHA-256 |
|---|---|
| backend/domain/workflow/__init__.py | 493E349DE9EE5638B19DB40371425C8E962FA5D471BD6639EB74B3F51E295F25 |
| backend/domain/workflow/queue.py | C785A686AD2EE462688ECE9D5A59B050E8864BF8F8D441350F8D21900845A869 |
| backend/tests/test_workflow_queue.py | DA578D3334396B5BE06C20BB9D01C3C5D82EA8D45357B6E5D74E98D0BD376DEB |
| 本轮 round-110-workflow-probes.py | B801CC9AC67D99DBA366877FC4169892F09ECC23B6EDDA28B9406A6D5A999AB7 |

全部测试与探针退出后的数据库终态：

```text
revision=auth000002
app_business_tables=31; auth_tables=7; app_enums=60; app_user_triggers=17
workflow_runs/steps=0/0
auth_user/session/account=0/0/0
test_tenants(name t8-* or cdx-r110-*)=0
```

探针只清理其跟踪的 tenant_id/public_id；故障测试自清理已在探针外层兜底前独立确认。pytest 临时目录保留，不与业务残留混淆。

## 五、交棒 DSH：T9 测试与回滚演练

请依据已冻结 `docs/contracts/test-strategy.md` §一/§二/§八和 P0-1 DAG，交付 `from-dsh/round-111-dsh-P0-1-T9测试与回滚演练.md`。

- 在独立临时测试库演练，保持当前共享基线库；先记录库标识和基线，再运行升降级，禁止误对共享数据执行清空演练。
- 正确顺序为：空库 upgrade head → catalog exact-set + 行为测试 → downgrade base + 空库对象断言 → re-upgrade head + catalog/behavior 回归。降到 base 后不运行依赖 schema 的整套 pytest 来冒充预期成功。
- 覆盖旧样本导入、跨 tenant 约束、CID 复算、幂等重放、trigger 正反例及本轮真实队列竞态/失败清理；fixture 归属与清理须可追踪。
- CI 分离 lint、无 DB unit、migration、catalog/repository/trigger/fixture-e2e、downgrade 空库断言、re-upgrade 回归；migration 失败阻断后续。
- 测试结果携带 mode/provider/model/source/evidence，附可重放命令、独立库终态、回滚证据、变更哈希；将本轮补充的完整预算/真实锁竞争门禁固化。

**完成边界：T8 COMPLETE 表示内部流程与最小队列当前范围通过，不表示 P0-1 全部完成、真实微信平台执行能力通过或全系统可上线。T9 完成后再进行后续阶段裁决。**

STATE 已交棒 DSH，并合并重复的 round-109 待办行；不再停留于已关闭的 T8 四项讨论。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-110-->
