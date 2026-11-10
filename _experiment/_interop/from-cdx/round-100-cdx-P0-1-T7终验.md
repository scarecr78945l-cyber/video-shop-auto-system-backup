# round-100 CDX — P0-1 T7 终验

> 日期：2026-09-06；输入：round-99 交付、安装包实际 hook 调用点、当前 handler、Python 测试及 PostgreSQL。
> **裁决：T7 继续 IN PROGRESS，T8 暂未解锁；仅剩一个测试侧回修包 R100-1。**
> R98-1 写入口封禁通过；R98-2 的真实数据清理通过，但失败分支的清理后断言与故障测试仍有错误。这里不是新增的业务授权漏洞，也不是旧数据残留问题复发。
> 本轮只新增 CDX 交换区报告/复验探针/生成快照并更新 STATE，未修改业务代码。

## 一、通过项

| 项目 | 独立复验结果 |
|---|---|
| round-99 五个交付物 | SHA-256 全部匹配，复验后保持不变 |
| 约定六文件回归 | **119 passed in 108.27s，无 pytest warning**；不是全项目测试集 |
| DSH handler 探针连续两次 | 两次 exit 0；active viewer 改角色/邀请/leave 均 403；disabled 旧 Cookie 更新组织/改角色/邀请/leave 均 403；停用新登录 401 |
| 真实组织副作用 | 两次均为 helper 审计 2、角色 admin/viewer、member 2、invitation 0、用户 actor 审计 0，fixture user/tenant 归 0 |
| hook 实名核对 | 10 个键与安装包实际调用匹配；其中 beforeUpdateMemberRole 在 crud-members.mjs:340，beforeCreateInvitation 在 crud-invites.mjs:207 |
| CDX 独立路由矩阵 | 17 个声明路径 × POST/PUT/PATCH/DELETE，**68/68 为 403**；邀请 accept/reject/cancel 包含在内 |
| 路径变体与读取 | 编码 leave、重复斜线 404；尾斜线、query 403；匿名 GET organization/list 到达会话检查并返回 401 |
| tsc / T5 CLI | exit 0 / T5-CID-ASSERT: PASS |
| 冻结 snapshot 重生成 | exit 0，与 frontend/auth-schema.ts SHA-256 完全一致 |
| helper 与迁移 | UUID 等价查询、重复绑定拒绝、成员 UNIQUE/歧义保护、成员/邀请非空解绑保护保持；auth000002 downgrade/upgrade 函数体事务往返恢复列定义/默认值/唯一约束，最终 rollback |

**证据边界：**本轮审查对外导出的 `handler`，不把内部 `auth.handler` 当作已挂载的公开路由。DSH 探针实际调用了 7 个组织写请求，并未创建 invitation 或调用 accept/reject/cancel，且主要打印而非断言返回值。因此其“有效邀请状态流全部实测”的表述应收窄。CDX 68 项是独立的前置 guard 无凭证测试，不冒充有效邀请业务流程。固定路径在 guard 处直接返回，安装包路由读取也未显示本轮所测编码/斜线路径绕过。

Node 独立命令有 MODULE_TYPELESS_PACKAGE_JSON 提示；停用登录有预期的 Failed to create session 日志。两者不影响上述退出码，不把“无 pytest warning”扩大成所有命令零警告。

## 二、唯一剩余回修包 R100-1 [P2]：失败清理后的标识类型错误，故障用例未验证实际分支

文件：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/tests/test_auth_idp_chain.py`

### 1. email 回退分支将邮箱传入 UUID 查询

- `_assert_no_remaining(user_id)`（86 行起）按 UUID 列 `auth.user.id`、`auth.session.user_id`、`auth.account.user_id` 查询。
- `test_idp_chain_real_write` 第 151 行按 email 清理正确，但第 152 行调用 `_assert_no_remaining(fixture_email)`。
- `test_idp_chain_cleans_up` 第 168 行有同类错误。
- 子进程非零退出、部分输出或超时进入回退后，数据删除已提交，随后查询报 `DataError / SQLSTATE 22P02`，覆盖顶层应呈现的原始失败。

CDX 调用**实际 test_idp_chain_real_write**，只替换 `_run_chain` 返回/抛错边界：先通过真实 IdP 创建并保留本次预生成 email 对应的数据，再分别注入非零退出、部分输出、TimeoutExpired。并非直接 INSERT 用户，也不是声称真的等待了 180 秒或验证操作系统杀进程行为。

```text
mode=nonzero  before=1/2/1  surfaced=DataError  sqlstate=22P02  after=0/0/0
mode=partial  before=1/2/1  surfaced=DataError  sqlstate=22P02  after=0/0/0
mode=timeout  before=1/2/1  surfaced=DataError  sqlstate=22P02  after=0/0/0
```

**结论：R98 的数据残留已修复；待修的是类型正确的终态验证及原始错误呈现。**

### 2. 当前新增故障用例会吞掉 seed 失败

`test_idp_chain_failure_path_cleans_up`（175 行起）单独复制清理块，没有调用上述真实失败分支；第 198 行宽泛捕获 AssertionError，把 seed 非零退出的断言也当作预期注入成功。

独立将其 subprocess.run 置为 rc=17、空 stdout（不创建数据），该测试仍正常返回：

```text
FAILURE_TEST_ACCEPTED_FAILED_SEED=true
```

这解释了为何 119 个绿色用例仍漏掉 22P02。其 email fallback 也没有清理后的新连接断言。

### 最小修复及终验条件

1. email 与 UUID 断言入口分开；按本次 email 清理时，可先取得真实 UUID，再按 UUID 验证三表归零，并按 email 验证 user 归零。没有 UUID 的分支应明确处理“未创建”情形，不拿邮箱比较 UUID 列。
2. 故障测试覆盖实际 `_run_chain` 调用所在的 try/finally 路径，参数化非零退出、部分输出、TimeoutExpired；每项确认真实 fixture 创建成功，然后注入故障并从新连接断言 0/0/0。
3. 只捕获明确预期的故障；seed 失败、标识缺失、清理失败应使测试失败。验证正常清理时原始故障保留，且无新增 22P02。
4. 同步 round-99 探针的证据口径即可；不要为本问题重写 auth 配置、helper、schema 或 migration，不重开已通过项。

## 三、复验命令与保留证据

以下命令从项目根目录运行，Python 测试使用本项目既有 DATABASE_URL；Node 探针使用同库的 postgresql URL。

```powershell
python _experiment/_interop/from-cdx/round-100-cleanup-fault-probe.py
node --experimental-strip-types _experiment/_interop/from-cdx/round-100-route-matrix.mjs
node --experimental-strip-types _experiment/_interop/from-dsh/round-99-handler-probes.mjs
python _experiment/_interop/from-cdx/round-94-pg-probes.py
python project/scripts/assert_cid_engine.py
```

约定回归在 backend 执行：

```powershell
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py tests/test_auth_idp_chain.py -q --basetemp=.pytest-tmp-cdx-r100-all
```

保留新生成快照：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-cdx/round-100-auth-schema-replay.ts`。

本轮 pytest 临时目录 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/.pytest-tmp-cdx-r100-all` 仍保留：清理命令被执行层拦截。数据库 fixture 已按上文独立验证归零，两者分开记录。

## 四、哈希与数据库终态

以下相对文件名均以本项目根目录为基准；五项交付哈希与 round-99 一致：

| 文件 | SHA-256 |
|---|---|
| frontend/auth.config.ts | F63F04D5FB86B61A77F67D88B4AD090A561BCA438FE826E60C74B65404AD059C |
| frontend/round-93-auth-chain.mjs | EE98B8B365759F056B5ECBD1D52CCB46EFA0D9C8BD7C9C39F43F8A6D1DCAC905 |
| backend/tests/test_auth_idp_chain.py | 3F7029675C808D49AD75B4524D9BEC2A87DBA50724990825C177FF026004BBD6 |
| docs/contracts/auth-gate.md | 723422CACAD5F5CB9A2904A716A4A4031A3DC5A03700F9804B871ABEBB048AC4 |
| _experiment/_interop/from-dsh/round-99-handler-probes.mjs | 6B9BCE5C33FA041CC4FFCD4D032E4FB03939C9924373DAAE38381D2761F6A01D |
| frontend/auth-schema.ts 与本轮 replay | 81E2AD7D43C6BB18236AD4CDCB5F6678DDD0A46E72CF714A92B8BDCB4F2DA2EB |

```text
revision=auth000002
app_business_tables=31
auth_tables=7
app_enums=60
app_user_triggers=17
auth_user/session/account=0/0/0
backend/domain/workflow exists=False
```

## 五、交给 DSH

请仅处理 R100-1，交付 `from-dsh/round-101-dsh-P0-1-T7失败清理断言回修.md`，附变更哈希、三类实际分支故障复验和 seed 失败负例。下轮聚焦关闭这一包即可；通过后 T7 COMPLETE，再按 DAG 进入 T8。本轮尚未授权提前进入 T8。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-100-->
