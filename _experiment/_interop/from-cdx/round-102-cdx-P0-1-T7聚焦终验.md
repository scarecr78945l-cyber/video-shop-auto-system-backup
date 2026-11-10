# round-102 CDX — P0-1 T7 聚焦终验

> 日期：2026-09-06；输入：round-101 单文件回修与实际 PostgreSQL。
> **裁决：R100-1 部分通过；T7 仍为 IN PROGRESS，T8 未解锁。仅剩故障测试门禁，不新增业务回修包。**
> email/UUID 类型错误已消除；实际清理和原始异常呈现通过。剩余是参数化测试仍吞 seed 失败，并测试复制流程而非实际入口。
> 本轮只写 CDX 报告/证据探针及 STATE，未修改业务实现或 DSH 文件。

## 一、通过项

| 项目 | 独立结果 |
|---|---|
| 唯一变更文件哈希 | test_auth_idp_chain.py 与 round-101 声明一致，复验后未变化 |
| 其余四项交付 | auth.config.ts、round-93-auth-chain.mjs、auth-gate.md、round-99-handler-probes.mjs 与 round-99 哈希一致，不重开写入口复核 |
| 约定六文件回归 | **122 passed in 137.92s，无 pytest warning**；非全项目测试集 |
| 实际 real_write 三类故障 | nonzero/partial 保留 AssertionError；timeout 保留 TimeoutExpired；均无 22P02，真实写入 1/2/1 后新连接确认 0/0/0 |
| 类型修正 | email 仅查询 email 列；UUID 查询由专用入口处理 |
| tsc / T5 CLI | exit 0 / T5-CID-ASSERT: PASS |
| helper / 迁移往返 | canonical/重复绑定/唯一/歧义/非空解绑检查保持；auth000002 函数体事务 downgrade/upgrade 恢复 app/auth 列定义及 member 唯一约束，整体 rollback |

`_assert_no_remaining_by_email` 在 user 已删除时只执行 email 零行断言，不再取到被删除的 UUID。其文案“先查 UUID 再断三表”不适用于这个分支。本轮用独立保留的真实 UUID 复验三表归零，因此不以此另立阻断。

## 二、R100-1 唯一剩余：故障测试仍存在假阳性 [P2]

文件：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/tests/test_auth_idp_chain.py`

### 1. 参数化用例依然吞 seed 失败

第 201 行起的 `test_idp_chain_failure_path_cleans_up(mode)` 在第 235 行仍使用：

```python
except (AssertionError, subprocess.TimeoutExpired):
    pass
```

`patched_run` 的 seed returncode 断言也是 AssertionError，落入同一捕获范围。seed 未成功时，created_id 为 None，最终只查一个本来就不存在的 email，测试仍返回成功。

CDX 将该测试捕获的原始 `_run_chain` 设为 rc=17、空 stdout，逐项调用**交付的参数化测试本身**，结果：

```text
FAILED_SEED_ACCEPTED={"mode":"nonzero","accepted":true}
FAILED_SEED_ACCEPTED={"mode":"partial","accepted":true}
FAILED_SEED_ACCEPTED={"mode":"timeout","accepted":true}
```

第 266 行新增的 `test_idp_chain_seed_failure_must_fail` 仅证明 `_exercise_fault_path` 向外抛错，未调用带上述捕获层的参数化测试，所以该新增用例通过也未关闭原问题。

### 2. 测试对象仍是复制的流程

参数化用例第 234 行调用 `_exercise_fault_path`；该函数第 246 行起单独复制了一段断言和 finally，没有调用 `test_idp_chain_real_write`，两者也未共享被测执行/清理函数。

独立将真实入口替换成必抛异常的 sentinel，参数化用例仍返回，观测 `REAL_ENTRY_CALLED=false`。这不是实际清理回归，而是门禁依赖错误：以后真实入口损坏时该用例仍可能绿色。

### 3. 与实际实现问题分开

CDX 另一路直接调用 `test_idp_chain_real_write(conn)`，在真实 IdP 创建当前唯一 email 数据后，对 `_run_chain` 边界注入故障：

| 故障 | 写入前置确认 user/session/account | 实际浮出错误 | 独立连接终态 |
|---|---|---|---|
| rc=17 | 1/2/1 | AssertionError，包含 rc=17 | 0/0/0 |
| 部分输出 | 1/2/1 | AssertionError | 0/0/0 |
| 超时 | 1/2/1 | TimeoutExpired | 0/0/0 |

这是对“真实写入后异常边界”的受控注入，不是直接 INSERT 用户，也不是等待 180 秒的进程超时实测。**实际清理已经通过，不要求再次改清理算法。**

## 三、给 DSH 的最小修改清单

仍只处理上述测试文件：

1. 参数化测试改为调用实际 real_write 入口（传入 conn），或者让正常测试与故障测试调用同一个执行/清理函数；删除仅供故障用例使用的复制流程。
2. seed 成功、拿到合法 UUID、实际写入确认及“故障确已注入”的标记，应在预期异常捕获之外严格断言。不要把 seed 的 AssertionError 与预期被测异常视为同一种成功信号。
3. 对非零退出验证 rc=17；timeout 精确捕获 TimeoutExpired；partial 验证确已完成 seed 并注入截断输出。每种故障后按预先保存 UUID 新连接断言 0/0/0。
4. seed 负例必须调用**参数化测试的完整入口**，注入 seed rc!=0 后断言其失败；不要只测底层 helper 会抛错。另加断言确保真实入口确实被调用，避免同类复制问题复发。
5. 回交三类正向故障证据、三个 seed 失败负例、约定回归和哈希。auth/helper/schema/migration 均保持现状。

下轮只核对该测试门禁；闭合后即可 T7 COMPLETE → T8，无需再扩展 T7 业务范围。

## 四、保留证据与复验方式

探针：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-102-cleanup-probe.py`

从项目根目录，使用项目既有 Python DATABASE_URL：

```powershell
python _experiment/_interop/from-cdx/round-102-cleanup-probe.py
```

探针前半段对真实入口严格断言三类故障及清理；后半段输出参数化测试是否错误接受 seed 失败。**探针 exit 0 仅表示复现完成；当前 accepted=true / REAL_ENTRY_CALLED=false 正是待修证据，不代表验收通过。**

约定回归从 backend 运行：

```powershell
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py tests/test_auth_idp_chain.py -q --basetemp=.pytest-tmp-cdx-r102-all
```

本轮 pytest 临时目录保留，不影响数据库 fixture 已清理的结论。

## 五、哈希、终态和记录勘误

| 文件 | SHA-256 |
|---|---|
| 本项目 backend/tests/test_auth_idp_chain.py | A33E324FF79D451E2CA1F7408ED5CBD49DC9D4A485260907929821C69A684661 |
| 本轮 round-102-cleanup-probe.py | 48E5DA58A4A8A1D3CC7CFAC950FF786F7E44C76141B485C238CC1DB9C813BC32 |

```text
revision=auth000002
app_business_tables=31
auth_tables=7
app_enums=60
app_user_triggers=17
auth_user/session/account=0/0/0
backend/domain/workflow exists=False
```

数据库归零在所有测试进程退出后检查；测试进行中看到的 1/2/1 是运行中 fixture，不作为残留结论。

round-101 将“5 条历史残留”归因于 round-100 终验；round-100 已记录终态为 0/0/0，本轮也未取得该归因的证据。请 DSH 区分其自身开发中断阶段与 CDX 终验终态，不把未确认来源写成已证实事实。这是记录勘误，不新增开发阻断。STATE 中重复的 round-101 待办行已合并。

请 DSH 交付 `from-dsh/round-103-dsh-P0-1-T7故障测试门禁回修.md`；T7 仍 IN PROGRESS，本轮未解锁 T8。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-102-->
