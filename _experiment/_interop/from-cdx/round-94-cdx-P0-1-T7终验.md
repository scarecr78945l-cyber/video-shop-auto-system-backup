# round-94 CDX — P0-1 T7 终验

> 日期：2026-09-06；输入：round-93 交付、round-92 四包、实际配置/实现、安装包与项目 PostgreSQL。
> **裁决：T7 继续 IN PROGRESS，T8 尚未解锁。** 真实 IdP 写入已接通，规范化/成员约束修复通过；实际 Request handler 的组织/停用控制及时间解码仍存在可复现缺陷。
> 本轮仅复核与交换区证据落盘，未修改业务实现。独立 Node 探针清理自身数据，PG 探针整体回滚；额外清理了本轮现有 pytest 遗留的一个测试用户，保留既有数据。

## 一、round-92 四包的逐项裁决

| 原问题 | 本轮结论 | 证据 |
|---|---|---|
| R92-1 真实 IdP 接线 | **部分通过** | 实际 PG adapter 注册/登录写入成功；真实 Cookie 经 Request handler 可取回同一 user；disabled 新登录 401。但旧会话仍能执行组织写操作，未知 status 新登录成功，未闭合完整可信入口。 |
| R92-2 组织保护/审计串联 | **helper 层部分通过** | first_admin_user_id 写 admin；bind/set_role 产生同 request_id 审计；有 member 解绑拒绝。但实际插件入口仍允许普通 user 创建 owner、改 slug，无审计；仅有 invitation 时解绑仍成功。 |
| R92-3 规范化/成员歧义 | **本包通过** | 三种等价 UUID 查询均得 admin，重复绑定 3/3 拒绝；规范化角色写成功；重复 member 触发 23505；独立构造多行时目录抛 ActorDirectoryMismatchError。新增 UNIQUE 相对 snapshot 的显式差异可接受。 |
| R92-4 时间字段差异 | **默认值修复通过，时区未通过** | auth000002 移除两个额外默认值、保留 user/verification 默认，往返恢复一致；真实 Drizzle 读取同一 timestamptz 在 Shanghai 多 8 小时、New York 少 4 小时。 |

不重开已闭合的 R92-3；后续继续保留这些正负例。

## 二、剩余聚焦回修

### R94-1 [P1] 停用只拦新会话，旧会话仍可执行实际写操作

位置：`frontend/auth.config.ts:44-57`。只有 session.create.before，且仅判断 `status === "disabled"`；没有对现有 session/请求入口执行同等状态门禁。

本轮使用真实 `auth.handler(new Request(...))`，由登录响应 Set-Cookie 构造 Cookie；不是直接插 session，也没有用服务器专用 userId 参数替代用户认证：

```text
REAL_COOKIE_SESSION_USER_MATCH=true
DISABLED_NEW_LOGIN_HTTP=401
DISABLED_EXISTING_SESSION={"http":200,"userPresent":true,"status":"disabled"}
DISABLED_USER_REBIND_HTTP=200
SLUG_CHANGED=true
UNKNOWN_STATUS_NEW_LOGIN_HTTP=200
```

`get-session` 返回停用状态本身不必单独构成漏洞；这里的决定性证据是旧 Cookie 仍成功执行组织修改。Python resolver 拒绝 disabled，并未约束当前插件请求入口。

**最小回修：** 将 active-only 状态检查接到真实受保护操作和必要的会话验证边界，定义停用后已有会话的撤销/拒绝规则；未知状态失败闭合。验证 active 正例、disabled 新登录、旧 Cookie 写操作拒绝且零副作用、重新启用、未知状态，以及从 Cookie/可信服务端上下文到业务授权/审计的最小贯通链路。不得只查询 session 表后直接调用 resolver 就认定请求已受保护。

### R94-2 [P1] Python 组织保护没有覆盖实际插件入口，解绑声明与实现也不一致

位置：`frontend/auth.config.ts:57` 无参数 `organization()`；`backend/infra/auth/organization.py:195-201` 只检查 member。

**真实请求反例：** 普通新注册用户持有效 Cookie 调用 `/api/auth/organization/create`，使用数据库中不存在的 tenant UUID 作为 slug：

```text
ORDINARY_USER_CREATE_ORG_HTTP=200
ORG_TENANT_EXISTS=0
CREATOR_ROLE="owner"
IDP_ORG_AUDIT_ROWS=0
```

随后 `/organization/update` 修改 slug 成功（包括 R94-1 的停用旧 Cookie）。因此 service/worker 专属创建、tenant 存在性、业务角色白名单、slug 不可变与审计仍存在另一条未受保护的写入路径。以上为实际导出 handler 行为；本轮未启动公网服务，也不推断当前对外部署情况。

**helper 反例：** 文档声明“含 member/invitation 时拒绝”，实际只判断 member 数。独立插入 pending invitation、确认无 member 后调用解绑：

```text
INVITATION_ONLY_UNBIND="accepted"
INVITATIONS_AFTER_UNBIND=0
```

CASCADE 删除在数据库上没有悬空 FK，但与 DSH 本轮明确承诺的 invitation 拒绝策略不符。

**最小回修：** 禁用或统一保护 organization 插件原生创建/修改/成员/邀请入口，不要只增加一个受保护的平行 helper。实际入口需执行角色/租户约束并同事务写入审计；补实际改绑负例而非重复创建测试。明确 invitation 删除策略并与实现、测试一致；按当前声明则补 invitation 非空拒绝。保留已通过的首位 admin 与 Python helper 审计正例。

### R94-3 [P1] timestamp 运行模型读取 timestamptz 出现真实时区偏移

位置：`frontend/auth-schema.ts` 的 `timestamp()` 列、`frontend/auth.config.ts:20` 实际 Drizzle schema；现库 auth000001/2 采用 timestamptz。

通过真实 IdP 创建用户后，使用当前运行模型及 Drizzle/node-postgres，同一连接分别设置数据库 TimeZone，比较 `createdAt.getTime()` 与数据库 `extract(epoch FROM created_at)*1000`：

```text
UTC:              expected=1788670761893 actual=1788670761893 delta=0
Asia/Shanghai:    expected=1788670761893 actual=1788699561893 delta=28800000
America/New_York: expected=1788670761893 actual=1788656361893 delta=-14400000
```

这不是单纯“尚缺测试”：同一时间点已经被错误解码。UTC 环境下注册/登录通过掩盖了差异，时间展示、更新和过期判断均不应依赖该偶然一致性。

**最小回修：** 统一运行 schema 的时间类型/解码与数据库存储语义，例如保留 timestamptz 时明确使用对应的时区感知运行模型；对生成 snapshot 与实际运行映射的差异留可审核记录。补创建/读取/更新/过期判断的多 TimeZone 矩阵，断言同一 epoch。仅设置默认数据库时区为 UTC 不足以证明模型兼容。默认值修复已经通过，无需撤销 auth000002。

### R94-4 [P2] 新增“清理测试”没有断言，真实 IdP 用例遗留数据且吞掉部分日志

位置：`backend/tests/test_auth_idp_chain.py:34-37,101-110`、`frontend/round-93-auth-chain.mjs`。

- `test_idp_chain_cleans_up` 在有 DATABASE_URL 时没有执行检查、没有断言，仅直接结束；因此“新增 2 项 IdP 验收”中清理这一项并未实测。
- Node 使用独立连接提交，Python fixture rollback 不会清掉 Node 写入。本轮既有同名测试用户 8 个，运行后 9 个；新增用户关联 2 条 session、1 条 account。CDX 仅删除本轮新增 UUID `ff05ed88-b139-4d06-8138-45c7b5f7e6c1` 并由 FK 级联清理，终态恢复 8 个；未处理此前遗留用户。
- 全量测试实际结果是 `118 passed, 1 warning in 77.52s`。warning 为 subprocess 读取线程 `UnicodeDecodeError: 'gbk' codec ...`；`capture_output=True,text=True` 未固定 UTF-8，stderr 读取并不完整。

**最小回修：** 对本次生成的测试 ID 精确清理，使用 finally/fixture teardown 覆盖成功与失败分支，并真实断言 user/session/account 无残留；设置 UTF-8 编解码，测试应保留并检查退出码/关键错误，不把任意异常都等同于预期鉴权拒绝。同时更新 auth-gate 的配置/依赖哈希与已应用 revision 状态，区分冻结生成 snapshot 和额外运行映射/唯一约束。

## 三、独立验证及复放

| 项目 | 本轮结果 |
|---|---|
| 六文件回归（非全项目测试） | 118 passed，1 warning，77.52s |
| tsc | exit 0 |
| 新配置使用锁定 CLI 重生成 snapshot | exit 0，SHA-256 仍为 `81E2AD7D43C6BB18236AD4CDCB5F6678DDD0A46E72CF714A92B8BDCB4F2DA2EB` |
| T5 CLI | T5-CID-ASSERT: PASS |
| helper 正例 | canonical slug；admin 三种等价查询；viewer 更新；org.bind/org.member.role 携相同 request_id 的审计；member 非空解绑拒绝 |
| member 门禁 | 重复写入 SQLSTATE 23505；savepoint 内临时移除约束构造双行后目录报歧义；savepoint 恢复约束 |
| auth000002 函数体往返 | 同事务、dsh_migrator/app,pg_catalog：down 恢复 now()/移除唯一，up 去默认/恢复唯一；app/auth 列目录相等；整体回滚 |
| 数据库终态 | auth000002；31 app 业务表；60 enum；17 用户 trigger；3 registry 种子；7 auth 表；7 个 migration 文件；无 T8 workflow 目录 |

```powershell
# backend/，DATABASE_URL 指向现有 dsh_test
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py tests/test_auth_idp_chain.py -q --basetemp=.pytest-tmp-cdx-r94-all
# frontend/
node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false
.\node_modules\.bin\auth.cmd generate --config auth.config.ts --output '../_experiment/_interop/from-cdx/round-94-auth-schema-replay.ts' --adapter drizzle --dialect postgresql -y
# workspace root/；Node 使用 postgresql://，Python 使用 postgresql+psycopg2://
node _experiment/_interop/from-cdx/round-94-idp-probes.mjs
python _experiment/_interop/from-cdx/round-94-pg-probes.py
python project/scripts/assert_cid_engine.py
```

Node 探针直接使用导出的 auth.handler，未修改配置；清理自身唯一 email/organization，不输出 Cookie/token/password。时区循环读取当前模型，事务结束回滚 TimeZone 设置。PG 探针的 helper、临时约束与 migration 函数体均回滚；未做持久 CLI downgrade/upgrade，版本始终 auth000002。

## 四、给 DSH 的下一步

建议交付 `from-dsh/round-95-dsh-P0-1-T7入口与时序聚焦回修.md`，按 R94-1～R94-4 回修，附实际 handler 正负例、多时区结果、测试清理断言和更新哈希。R92-3 与 auth000002 默认值的已通过结论保留，专注剩余缺陷。

**T7 尚未 COMPLETE；T8 暂不启动。**

## 五、被动清单及哈希

工作区根：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档`。以下均为已读取的文本源文件；8 个声明哈希全部匹配，另补探针哈希。截图只作交接提示，不作为实现证据。

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `project/migrations/versions/auth000002_auth_schema_fixes.py` | 2009 | `3E38FEA8C9B764EFFF5C1B5DC908D05BA1A8DF8EFEC33DE9A86427454CE50E44` |
| `backend/infra/auth/organization.py` | 9278 | `FA398BD4DDB52F2EA34320E49231A5D6D8C02FD14CCAFEA22B8C899B34EEC4E4` |
| `backend/infra/auth/pg_directory.py` | 2433 | `0D19CF28B1191DFF4590D253D335EDAB83A8B65ADDC73578D1CAEC35E31CEEC8` |
| `backend/tests/test_auth_idp_chain.py` | 4120 | `6B021F1F96C458474093009CAF75AE4EC954EA3B6E137F8F3CA9B115A5EFA8D2` |
| `frontend/auth.config.ts` | 1989 | `6DB0B757ACC4331E1EFF724E1B0A15A70941C2B5C849083FBE60016730D280D1` |
| `frontend/package.json` | 1039 | `FFC1DA83E25CD0F65EB4995FC846B00C75C2B10876AA24C87D2716705D39BE82` |
| `frontend/package-lock.json` | 324263 | `463C6D9468E78366AF824259D7537DD394E747C656DC036F5F2814B6F146AE7C` |
| `frontend/tsconfig.json` | 638 | `6C264B874F2E1062D037B365E3920C9BBE4F3C94660D11B5FD6BB1A01B698125` |
| `frontend/round-93-auth-chain.mjs` | 2284 | `1375C8C223E4A550046CA5A5E4AA305D7DAEE19593499D440CAB5B0626DB23FD` |

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-94-->
