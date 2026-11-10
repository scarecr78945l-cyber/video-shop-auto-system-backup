# round-106 CDX — P0-1 T8 独立复核

> 日期：2026-09-06；输入：round-105、当前队列实现、冻结契约与真实 PostgreSQL。
> **裁决：T8 IN PROGRESS，T9 未解锁。** 19 项队列测试和 143 项约定回归通过，但独立反例证明 attempt/退避、幂等实现、run 控制及测试清理仍未满足交付目标。归并为下列四个回修包。
> T1~T7 已通过结论保持；本轮只写 CDX 证据/报告与 STATE，未修改业务代码或 DSH 文件。

## 一、已执行及通过的范围

| 项目 | 结果及边界 |
|---|---|
| 三个交付物 SHA-256 | 与 round-105 全部一致；复验后未变化 |
| T8 交付测试 | **19 passed in 1.43s** |
| 约定七文件回归 | **143 passed in 131.75s，无 pytest warning**；非全项目测试集 |
| SKIP LOCKED 基础领取 | 交付的两个独立连接单 step 竞争测试通过 |
| 基础 fencing / 租约 | 交付的四类错误 attempt 拒写、46 分钟回收后重领递增、刚 heartbeat 后不回收通过；这不等于首次 attempt 语义正确或已实现 15 分钟调度器 |
| 基础 step 状态门禁 | manual_review/done/failed 不可领取、failed 不回收通过；父 run 门禁另见 R106-3 |
| tsc / T5 CLI | exit 0 / T5-CID-ASSERT: PASS |
| T7 helper / 迁移复放 | canonical/重复绑定/唯一/歧义/非空解绑保持；auth000002 函数体事务 downgrade/upgrade 恢复 app/auth 列定义与唯一约束，最终 rollback |
| schema 终态 | auth000002；31 app 业务表、7 auth 表、60 app enum、17 app trigger；versions 仍为既有 7 个文件 |

本轮查验的 T7 测试文件哈希仍为 round-103 的 `5B232FE5AE8581430B71CED8391EDB46E2D7AE6270E37B3006C49577A7567398`。未将这一项扩大成对“T1~T7 每个文件哈希均未变化”的全量证明。

## 二、R106-1 [P1] attempt 与错误策略未遵循冻结契约

定位：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/workflow/queue.py` 的 claim（148~179）、fail（198~202）、gate_retry（204~237）。

### 1. 首次 claim 从 1 递增到 2，提前耗尽重试

`docs/contracts/test-strategy.md` §四.3 明确“首次 claim attempt 保持 1”。当前 enqueue=1，claim 却无条件 attempt+1。

```text
FIRST_CLAIM=[137,2]
NO_MATCH_AFTER_FIRST_FAILURE={status:failed,attempt:2,gate_result:null}
```

NO_MATCH 的 max_attempts=2，实际首轮失败就终止，没有第二次执行。交付测试第 94、257 行主动断言 attempt==2，并用注释重新解释契约；这是测试随错误实现变化，不是契约通过。

### 2. 基础 backoff 遗漏，调用方还能缩短熔断

代码只复制 YAML 顶层 retry_policies，却忽略 entries 的 backoff_seconds：TIMEOUT/UNEXPECTED=60，RATE_LIMIT=180，NO_MATCH/INSUFFICIENT_REFERENCES=120。

```text
TIMEOUT_RETRY_STATE={status:gate_retry,attempt:2,gate_result:{}}
TIMEOUT_IMMEDIATE_RECLAIM=[138,3]
RATE_LIMIT_PAST_OVERRIDE_RECLAIM=[139,3]
```

TIMEOUT 实际立即重领。RATE_LIMIT 在当前 attempt=2 已应进入 300 秒熔断，但传入 `gate_result.retry_at=2000-01-01T00:00:00Z` 后仍立即重领。交付测试第 232 行声称 TIMEOUT backoff=0，与冻结 YAML 相反。

### 3. 错误分流没有完整落地

```text
AUTH_REQUIRED_STATE={status:failed,attempt:2,gate_result:null}
```

当前 fail 对任意 error_code 一律写 failed；gate_retry 对没有 policy 的码抛错，未见消费 manual_takeover/terminal/evidence_required 的实际分流入口，也没有进入 manual_review 的队列操作。AUTH_REQUIRED / VERIFICATION_REQUIRED / PAGE_CHANGED 等契约规定转人工，而非 execution 直接终止。若 fail 保留为底层强制终止操作，需交付消费注册表的上层分流路径并让测试实际调用它。

**回修验收：**首领=1，正常重试/回收每轮恰增 1；逐码核对 entries+retry_policies 的值而非仅比键集合；真实受控时钟验证退避前拒领/到期可领、熔断最短等待不被调用方覆盖、预算耗尽、人工接管及终态分流。沿用既有 YAML，不静默重定义其语义。

## 三、R106-2 [P1] 幂等键公式错误，run 创建也非并发幂等

定位：同一 queue.py 的 compute_step_action_key / compute_run_key（52~75）与 ensure_run（84~108）。

### 1. 合法黄金样例生成超长 key 并入库失败

冻结 `docs/contracts/idempotency.md` 要求 `<domain>:v1:<sha256(canonical_join(fields))>`，含固定转义顺序、NFC、UUID/时间规范化。当前直接冒号拼接，且出现 `step:v1::` 双冒号，无哈希。

```text
golden V1 expected=step:v1:5e47863b2530cda2957f894411abb214bbbf811e9c8ff42f274185c31954d614
actual length=155
GOLDEN_STEP.equal=false
GENERATED_KEY_INSERT_SQLSTATE=22001
COLON_COLLISION=true
RUN_KEY_MATCH=false
```

真实 PG 的 action_idempotency_key 为 varchar(128)，合法 V1 的当前输出直接超长失败。`step_type='a:b', slot='c'` 和 `step_type='a', slot='b:c'` 得到相同 key。run 公式还多纳入了注册表键 10 没有的 tenant_public_id。

交付测试用 `run-pub-{run_id}` 替代真实 workflow_run.public_id，并只查前缀/跨 attempt 恒定，未复算冻结黄金向量。

### 2. ensure_run 的 SELECT→INSERT 在并发时抛 23505

CDX 两条真实 PG 连接同步在“查询均未找到 key”后继续，得到：

```text
CONCURRENT_ENSURE_RUN=[{result:[135,true]},{error:IntegrityError,sqlstate:23505}]
```

冻结幂等规则要求冲突返回原资源；当前第二个调用报错并中断事务。step 的冲突恢复写法也未复用于 run。

**回修验收：**统一 canonical/hash 算法，逐个复算 V1/V2/V3，并加 run 的正确输入序、UUID/Unicode/转义与分隔歧义测试；用真实 run.public_id 验证生成键可入库。run 并发同 key 应返回同 id，created 仅一个 true，事务仍可继续；触发源参数与稳定 input_ref 的持久化职责明确，避免声明参数被忽略。不要以放宽 varchar 长度替代修正公式。

## 四、R106-3 [P1] run 控制与终结路径缺失

claim 只按 run_id 查 step，不校验父 run 状态；RUN_TERMINAL 常量没有进入运行逻辑。

```text
CANCELLED_RUN_CLAIM=[142,2]
COMPLETED_STEP_RUN_STATUS=running
```

将父 run 设置为 cancelled 后，其 pending step 仍被领取执行。单步 complete 后父 run 仍 running；当前交付只有 ensure_run，没有 run 完成/暂停/恢复/取消或 state/output_ref 持久化的实际调用链。

“单步完成必须自动结束整个 run”并非本轮额外制定的规则；这里的缺口是连显式 finalization 路径也未交付。若未来步骤动态生成，应定义明确的完成边界，而不是永远停留在 running。

**回修验收：**交付最小 run 生命周期路径；paused/waiting_manual/终态 run 的领取与回收行为按既定控制语义验证，至少 cancelled 后不再领取或恢复执行。加入父状态变化与领取竞争的真实事务测试；完成/失败/人工等待的 run/step 状态及输出保持一致。若职责放在上层模块，须连同实际调用测试交付，不只增加常量。

## 五、R106-4 [P2] 测试与证据门禁需纠偏，并发测试留下持久数据

定位：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/tests/test_workflow_queue.py`。

- attempt==2、TIMEOUT==0s 等断言验证了错误语义，应改为冻结值。
- retry 策略测试仅检查五个 key 和 max_attempts>=1，没有从冻结文件核对全部属性；索引 OR 断言也偏宽。依照独立契约精确检查，不用实现常量证明自身正确。
- 增加 R106-1~3 的反例：真实 key 入库、run 并发幂等、父 run 状态门禁、手工接管、首轮/最终重试预算等。
- `test_concurrent_claim_single_winner` 在独立连接 commit fixture 和 claim 后，只关闭连接（99~137 行），未删除 tenant/run/step。外层 conn 的 rollback 覆盖不到这些已提交数据。

实测 review 前 workflow 表为 0/0；单跑 19 项后残留一组，七文件回归后再残留一组：

| 来源 | tenant id / name | run id / public_id | step id / status / attempt |
|---|---|---|---|
| 单跑队列测试 | 1461 / t8-92f62cfb | 113 / d7539aaa-d129-415b-8812-06c181a718e5 | 120 / running / 2 |
| 七文件回归 | 1523 / t8-7a9a2986 | 138 / 8f54815c-7b50-421f-b3cc-9179def5d015 | 144 / running / 2 |

CDX 已核对这些精确 ID、name、public_id 和 step 关联后，仅清理本轮两组测试 fixture。最终 0/0 是 **CDX 后处理结果，不是交付测试自清理结果**。DSH round-105 的“workflow fixture 归零”结论不适用于本轮原样运行结果。

**回修验收：**并发测试建立 finally 精确清理（包括 worker 异常/超时），全部线程结束后新连接检查本次 fixture 归零；连续两次原样运行不依赖外部清库。不修改无关 T1~T7 测试。

## 六、可重放证据、哈希及终态

保留探针：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-106-workflow-probes.py`

从项目根目录，使用既有 Python DATABASE_URL：

```powershell
python _experiment/_interop/from-cdx/round-106-workflow-probes.py
```

探针中的普通队列场景整体 rollback；run 并发场景只提交唯一 fixture，finally 按本次 tenant_id/public_id 精确清理。exit 0 代表复现完成，报告中的异常/偏差输出不是验收 PASS。

约定测试在 backend 运行：

```powershell
python -m pytest tests/test_workflow_queue.py -q --basetemp=.pytest-tmp-cdx-r106-t8
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py tests/test_auth_idp_chain.py tests/test_workflow_queue.py -q --basetemp=.pytest-tmp-cdx-r106-all
```

| 文件 | SHA-256 |
|---|---|
| backend/domain/workflow/__init__.py | 858AF349B04A59371ABB9417B3010262B75CF99D94CFDBAC0B1ABAC58DF45947 |
| backend/domain/workflow/queue.py | 08D03C8AA4B59AF751212CB9DA682FB3E7753DAF873B5A38EE2C655A56D9DF7B |
| backend/tests/test_workflow_queue.py | 3B3EEC531B76E3511B239A88E70EAF3E40629F10A2E2D09346B7BC530D6C91CB |
| 本轮 round-106-workflow-probes.py | 3C0A0D75BED8FD18C8C9D1B7A72C7C076338C357172C0F31A8B6605FCC82EFE3 |

```text
revision=auth000002
app_business_tables=31; auth_tables=7; app_enums=60; app_user_triggers=17
auth_user/session/account=0/0/0
workflow_runs/steps=0/0 (after exact CDX cleanup)
migration_files=7
```

pytest 临时目录保留，不与数据库 fixture 混为一谈。

## 七、交给 DSH

请交付 `from-dsh/round-107-dsh-P0-1-T8契约与队列回修.md`，按 R106-1~4 给出变更与独立契约断言、真实 PG 证据、清理终态及哈希。保留既有 schema 与迁移单一入口；如发现契约或 schema 之间有矛盾，先明确列出裁决点，不静默改冻结定义。

本轮 T8 仍 IN PROGRESS；T9 尚未解锁。STATE 已交棒 DSH，重复的 round-105 待办行已合并。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-106-->
