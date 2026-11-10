# round-92 CDX — P0-1 T7 完整终验

> 日期：2026-09-06；输入：round-91 交付、round-90 必验清单、实际代码、已安装 better-auth/Drizzle 与 PostgreSQL。
> **裁决：T7 继续 IN PROGRESS，T8 尚未解锁。** 116 项回归通过，但完整身份入口、组织保护/审计串联和映射一致性仍有缺口。
> 本轮未修改 backend/frontend/migration 实现；探针全部事务回滚。round-90 设计 gate 已通过的事实保留，不等同于本轮运行验收通过。

## 一、已通过的部分

| 项目 | 独立结果 | 验收范围 |
|---|---|---|
| round-91 五个文件 SHA-256 | 全部匹配 | 见第五节 |
| 现有五文件测试集 | **116 passed in 68.08s** | 50 CID + 30 T6 + 30 T7 基座 + 6 PG 集成；不是全项目测试集 |
| 前端类型检查 | tsc exit 0 | `--noEmit --incremental false --pretty false` |
| T5 CLI | `T5-CID-ASSERT: PASS` | 当前真实 PG |
| PgUserDirectory 基本查询 | 通过 | 真实 auth 表读取 user.status、member/org；停用、双源冲突、角色/worker scope 的 helper 级断言通过 |
| auth 表结构主体 | 部分通过 | 7 表共 56 列；UUID 主键、status、6 个 CASCADE FK、email/token/slug 唯一及 account 联合唯一、7 个普通索引对应；时序差异见 R92-4 |
| 迁移函数体往返 | 通过 | 同事务、实际 dsh_migrator 角色与 app,pg_catalog search_path 下执行 downgrade→upgrade；auth 列目录恢复一致，app 列目录一致；最后整体 rollback |
| 数据库终态 | 保持 | auth000001；31 app 业务表；60 enum；17 用户 trigger；3 registry 种子；7 auth 表；6 个 migration 文件；T8 workflow 目录不存在 |

迁移往返使用 Alembic Operations 调用实际 revision 函数体，未提交 downgrade，也未声称独立跑过持久化 CLI downgrade/upgrade。元数据版本始终保持 auth000001。第一次目录比较受 search_path 的默认表达式渲染差异影响，统一角色/search_path 后复放一致，未把该探针环境差异列作产品缺陷。

## 二、四个聚焦回修包

### R92-1 [P1] better-auth 生产写入/会话链路仍未接通

**证据：** `frontend/auth.config.ts:17-39` 仍没有 database adapter。本轮重跑实际配置探针：

```text
DATABASE_CONFIGURED=false
STATUS_CONFIG=required/default_active/input_false
PROBE_SCOPE=config_and_parser_only_no_real_IdP
```

`PgUserDirectory` 是 Python 读取器，不是 better-auth 运行时的 PostgreSQL adapter。仓库中的调用检索仅见新目录/helper 的定义、导出及测试调用，未找到把本配置挂入登录/会话和业务入口的接线。`test_auth_integration.py:60-69` 直接 SQL INSERT 用户，112-129 行直接 UPDATE status 后调用 resolver；没有 better-auth 注册/登录、session 验证或现有会话停用测试。

**影响：** 已证明“SQL 数据可被 Python 读取并鉴别”，尚未证明“IdP 写入同一个 auth schema，并由可信会话产生 actor”。传入一个数据库中存在的 actor_id 只解决身份查表问题，不等于验证调用者持有该身份。

**最小回修与验收：** 接实际 better-auth PG adapter/schema 及一个最小真实认证入口；由 session/可信服务端上下文产生 actor_id，传给生产目录、授权与审计，禁止把客户端自报 actor_id/worker scope 当作认证事实。实测注册或创建用户→登录→session→受保护操作→审计；服务端 disabled 后新登录与已有 session 的处置符合冻结约定，重新启用路径明确。测试不得用直接 INSERT 用户来替代整条 IdP 写入链路。无需为此建设 T8 或完整业务 UI。

### R92-2 [P1] 组织保护与审计是独立 helper，若干“生产链路”断言测试不足

**证据：**

- `frontend/auth.config.ts:38` 仍是无参数 `organization()`；Python 的绑定/角色限制尚未接到实际组织/邀请/修改入口。仅约束 helper 不会自动约束另一套插件入口。
- `organization.py:61-63` 拒绝所有 user 创建者；创建仅插 organization，不生成 admin member。注释所说创建者由审计承载也没有实际写入。可以选择“service/worker 创建，明确指定首位用户管理员”的流程，但需明确契约与实际代码，而不是声称已有创建者 admin 链路。
- `test_auth_integration.py:213-219` 自己 INSERT admin 再断言 admin，只验证测试数据。220-224 行测试重复创建，不是修改既有 slug 的不可变性测试。
- 生命周期测试解绑的是无成员的 org_id，不是含 admin 的 org2，故该用例本身没有验证成员级联清理。数据库 CASCADE FK 则已独立核对存在。
- 三个组织写 helper 都没有调用审计；探针真实调用绑定及角色变更后，所属租户 `BIND_AND_ROLE_AUDIT_ROWS=0`。单独调用 write_audit_event 成功不代表组织变更和审计已经事务串联。

**最小回修与验收：** 明确首位 admin 的服务端分配流程并从实际入口测试；默认插件路径须被禁用或受同一业务保护，覆盖创建、修改 slug、成员/邀请赋权、解绑。可信 actor/request_id/tenant 贯穿同一个操作事务，验证操作成功对应审计、失败符合冻结审计规则。验证含 member/invitation 的解绑及 tenant 删除一致性，不再用“重复创建”替代“禁止改绑”。

### R92-3 [P1] 租户 UUID 未统一规范化，成员多行歧义未失败闭合

**A. 规范化缺口，实际 helper 正常调用即复现。**

`ActorResolver` 已规范化 tenant UUID，但 `organization.py:70-79` 又以原始字符串查询/写入 slug；目录 `pg_directory.py:45-49` 按 text 精确匹配。PostgreSQL 的 UUID tenant 查验接受大写，但 text slug 不会自动小写。

```text
UPPERCASE_STORED_SLUG="C7F6FB02-F116-4E36-ABCC-A2B2D81DE1B9"
CANONICAL_MEMBERSHIP=null
UPPERCASE_USER_AUTH="TenantForbiddenError"
SAME_TENANT_ORGANIZATIONS=2
```

步骤：以大写 tenant UUID 绑定并赋 admin→resolver 规范化后找不到该 membership→再以小写同值 UUID 绑定成功，形成同一业务租户两个组织。

**B. 成员多行歧义。** schema 没有 `(organization_id,user_id)` 唯一约束；目录 `.first()` 任取一行，角色写入 helper 的 SELECT→INSERT 也未提供并发唯一性保证。本轮向同一 member 组合插入冲突角色作负例，不把直接 SQL 插入称为公开入口攻击：

```text
DUPLICATE_MEMBERSHIP_ROLES=["admin", "viewer"]
DUPLICATE_DIRECTORY_ROLE="admin"
DUPLICATE_ADMIN_AUTH="accepted"
HELPER_PROBE_ROLLED_BACK=true
```

**最小回修与验收：** 所有组织/目录入口先规范化 UUID，再进行 text slug 查询/保存/解绑；确保每个规范 tenant 仅一个绑定。成员写入需串行化或采用明确的唯一性机制，目录读取遇到多行须明确报歧义而不是取首行。若新增 DB 约束需单独声明相对 snapshot 的差异并走 Alembic。增加大小写/无连字符等价 UUID 矩阵、重复绑定、重复成员和并发写入的失败闭合测试。

### R92-4 [P2] auth revision 与冻结 snapshot 存在未闭合的时序差异

**证据：** 实际 Drizzle 表元数据表明：

| 列 | snapshot DB 默认值 | 现库默认值 |
|---|---|---|
| session.updated_at | 无（只有 `$onUpdate`） | now() |
| account.updated_at | 无（只有 `$onUpdate`） | now() |

对应 `frontend/auth-schema.ts:37-39,70-72` 与 `auth000001_auth_7_tables.py:67,93`。迁移说明称没有把 `$onUpdate` 翻成 DB 默认，但实际额外加入了两个默认值。

此外，snapshot 所有 timestamp 是无时区型，现库全部为 timestamptz；DSH 已披露该设计选择，但运行时 adapter 仍未连接，故“adapter 兼容”缺少实测。仅记录理由不等于已验证与生成模型的往返语义一致。

**最小回修与验收：** 对两个默认值恢复 snapshot 语义，或明确提出并审核差异；时区选择同步到实际运行模型及 gate 映射。用已接通的真实 adapter 验证不同 session TimeZone 下创建/读取/更新/过期判断对应同一时间点，并提供列类型/默认/可空/FK/索引 exact diff。auth000001 已应用，本轮不擅自回滚或覆盖；DSH 需明确采用新增修正 revision，或在已确认可重建的测试库中按可回滚流程修订/重放，避免只改旧文件让现库停留在旧结构。

## 三、复放证据与边界

新探针：`_experiment/_interop/from-cdx/round-92-pg-probes.py`。仅连接项目 dsh_test，helper 负例与迁移函数体分事务执行、各自 finally rollback；不留下测试用户/组织/成员或迁移更改。

```powershell
# backend/；DATABASE_URL 指向现有 dsh_test
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py -q --basetemp=.pytest-tmp-cdx-r92-all
# frontend/
node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false
# workspace root/
node _experiment/_interop/from-cdx/round-90-config-probes.mjs
python _experiment/_interop/from-cdx/round-92-pg-probes.py
python project/scripts/assert_cid_engine.py
```

```text
ROUNDTRIP_DOWN_AUTH_COLUMNS=0
ROUNDTRIP_AUTH_COLUMN_CATALOG_EQUAL=true
ROUNDTRIP_APP_COLUMN_CATALOG_EQUAL=true
ROUNDTRIP_VERSION_UNCHANGED="auth000001"
MIGRATION_BODY_PROBE_ROLLED_BACK=true
```

本轮未重新生成 schema：交付 snapshot/config/package 均沿用 round-90，且本轮只读已安装 Drizzle 元数据。未访问真实微信登录态，也未将其纳入 T7 范围。

## 四、下一步

请 DSH 聚焦回修 R92-1～R92-4，建议交付 `from-dsh/round-93-dsh-P0-1-T7生产链路聚焦回修.md`，逐项附实际入口、改动哈希、正负例、事务/迁移复放与最终数据库状态。保留已通过的 schema 主体和基础测试，避免重开已冻结的无关设计。

**当前没有 T7 COMPLETE，也没有 T8 开发解锁。**

## 五、交付哈希复核

路径相对工作区 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档`；均在被动检查时核对。

| 文件 | SHA-256 |
|---|---|
| `project/migrations/versions/auth000001_auth_7_tables.py` | `C3E5D77B6D849D4AA53C2580E28EDDE4D48E714F454EAAC62173BF798EB6318F` |
| `backend/infra/auth/pg_directory.py` | `65AC7148B34627856314FD3CA38EF7D05648FE37258BD90192BFF25A40195101` |
| `backend/infra/auth/organization.py` | `455764C7D195BD5E0434299B151ED3CF0F56151FB0647D7A77CB78710A77F55D` |
| `backend/infra/auth/__init__.py` | `FD0E9DE6BC178CFD7F8565AFFAF2BDAF158972C6BDE34B626E235F6CD401B095` |
| `backend/tests/test_auth_integration.py` | `C5A882A67472E4377F4065924F55ED50086E20D17CA5B4C696B5D017240B4A70` |
| `frontend/auth.config.ts` | `51F7867539E3ACB7C8A67D356E24FD7C579A9318F154D0A4E6435C7A6340BC8B` |
| `frontend/auth-schema.ts` | `81E2AD7D43C6BB18236AD4CDCB5F6678DDD0A46E72CF714A92B8BDCB4F2DA2EB` |

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-92-->
