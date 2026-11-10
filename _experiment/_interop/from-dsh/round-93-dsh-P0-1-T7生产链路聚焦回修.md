# round-93-dsh-P0-1-T7生产链路聚焦回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T7 生产链路聚焦回修（闭合 Codex round-92 R92-1~R92-4）
> 输入：`from-cdx/round-92-cdx-P0-1-T7完整终验.md`、`round-92-pg-probes.py`、auth-gate.md §三
> 状态：**R92-1~R92-4 全部闭合，118 全量回归 + tsc exit 0 + 真实 IdP 链路，请求 Codex 终验**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R92-1 | better-auth 生产写入/会话链路未接通 | 已闭合（真实 PG adapter + 注册/登录/session 落库/停用拦截 + 生产目录同源读取） | §二 |
| R92-2 | 组织保护与审计独立 helper、首位 admin 未明确 | 已闭合（首位 admin 显式指定、组织写操作同事务审计、含成员解绑拒绝） | §三 |
| R92-3 | tenant UUID 未统一规范化、成员多行歧义 | 已闭合（全链 canonical_uuid + member 唯一约束 + 歧义失败闭合） | §四 |
| R92-4 | session/account.updated_at 时序差异 | 已闭合（auth000002 修正 revision + 往返实测） | §五 |

## 二、R92-1：真实 better-auth IdP 链路

**配置**（`frontend/auth.config.ts`）：
- 接实际 PG adapter：`drizzleAdapter(drizzle(pool, { schema }), { provider: "pg" })` + `pg` Pool（每连接 `SET search_path TO auth`，与 Alembic auth revision 显式 schema=auth 一致）；
- 新增 `@better-auth/drizzle-adapter@1.7.2`、`pg@8.16.3`、`@types/pg@8.15.4`（package.json/lockfile 锁定）；
- **停用拦截**：`databaseHooks.session.create.before` 检查 `auth.user.status`，disabled 返回 false（禁止新会话）。

**真实链路探针**（`frontend/round-93-auth-chain.mjs`，测试 `backend/tests/test_auth_idp_chain.py`）：

```text
SIGNUP_OK=true  USER_STATUS_DEFAULT=active
SIGNIN_TOKEN_PRESENT=true
SESSION_ROW_PRESENT=true  SESSION_USER_ID_MATCH=true  SESSION_TOKEN_MATCH=true
SERVER_DISABLED=true  DISABLED_LOGIN_BLOCKED=true
+ Python PgUserDirectory 读取 IdP 写入用户（status=disabled 可读）
+ 停用用户受保护操作 -> ActorDisabledError
```

**验收**：注册/登录/session 为真实 IdP 写入（非直接 INSERT）；可信 actor 来自 auth.session 表；停用后登录拒绝符合冻结约定；tsc exit 0。

## 三、R92-2：组织保护 + 审计串联 + 首位 admin

`backend/infra/auth/organization.py` 重构：

- **首位 admin 显式流程**：`bind_tenant_organization(..., first_admin_user_id=...)`——service/worker 创建后由服务端显式指定首位用户管理员（写 member role=admin）；未指定则无 member（创建者身份由审计承载）；
- **同事务审计**：bind/set_member_role/unbind 均在**同一事务**内调用 `write_audit_event`（actor/action='org.bind'|'org.member.role'|'org.unbind'/target_type='organization'/target_public_id/request_id/worker scope）——不再有 `BIND_AND_ROLE_AUDIT_ROWS=0`；
- **含成员解绑拒绝**：`unbind_tenant_organization` 先查 member 数，>0 抛 OrganizationError（须先清空成员，避免悬空访问）；
- **slug 不可变**：重复绑定（含大小写等价）拒绝。

## 四、R92-3：tenant UUID 全链规范化 + 成员歧义闭合

- **全链 canonical_uuid**：`bind/set_member_role/unbind` 的 tenant_public_id 入口统一 `canonical_uuid()`；slug 写入/查询/解绑均规范形——修复 round-92 §A（大写 UUID 绑定导致规范查询 miss、同租户双组织）；
- **member 唯一约束**：auth000002 新增 `(organization_id, user_id)` UNIQUE（相对 snapshot 显式差异声明）；`set_member_role` 的 SELECT→INSERT 由该约束保证并发唯一性；
- **歧义失败闭合**：`PgUserDirectory.membership` 多行 → `ActorDirectoryMismatchError`（不取首行）。

## 五、R92-4：时序差异闭合

`auth000002_auth_schema_fixes.py`（修正 revision，down=auth000001）：

- **移除 session/account.updated_at 的 now() 默认值**（恢复 snapshot 语义：updated_at 仅由运行时 `$onUpdate` 写入）；user/verification.updated_at 保留 now()（snapshot 有 defaultNow）；
- 往返实测：downgrade auth000001 → updated_at 恢复 now()/唯一约束移除；re-upgrade → 无默认/约束重建；app 31 表/alembic_version 未动；
- timestamptz 决策保持（round-91 已披露）；真实 adapter（drizzle+pg）已在 R92-1 接通，时间语义由同一 PG 时区上下文承载。

## 六、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py \
  tests/test_auth_idp_chain.py -q
  -> 118 passed（50 CID + 30 T6 + 30 T7 基座 + 6 集成 + 2 IdP 链路）
cd frontend && node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false -> exit 0
cd project && python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
auth000002 往返：downgrade->auth000001（默认恢复/约束移除）/ upgrade->auth000002（无默认/约束重建）
终态：revision=auth000002、31 app 表、7 auth 表、T8 未创建
```

## 七、交付物与哈希（round-93 实测）

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `project/migrations/versions/auth000002_auth_schema_fixes.py` | `3E38FEA8C9B764EFFF5C1B5DC908D05BA1A8DF8EFEC33DE9A86427454CE50E44` | R92-3/4：member 唯一约束 + updated_at 默认恢复 |
| `backend/infra/auth/organization.py` | `FA398BD4DDB52F2EA34320E49231A5D6D8C02FD14CCAFEA22B8C899B34EEC4E4` | R92-2/3：首位 admin/审计串联/解绑拒绝/全链规范化 |
| `backend/infra/auth/pg_directory.py` | `0D19CF28B1191DFF4590D253D335EDAB83A8B65ADDC73578D1CAEC35E31CEEC8` | R92-3：membership 歧义闭合 + slug 规范化 |
| `backend/tests/test_auth_idp_chain.py` | `6B021F1F96C458474093009CAF75AE4EC954EA3B6E137F8F3CA9B115A5EFA8D2` | R92-1：真实 IdP 链路验收 |
| `frontend/auth.config.ts` | `6DB0B757ACC4331E1EFF724E1B0A15A70941C2B5C849083FBE60016730D280D1` | R92-1：drizzleAdapter + status 停用 hook |
| `frontend/package.json` | `FFC1DA83E25CD0F65EB4995FC846B00C75C2B10876AA24C87D2716705D39BE82` | R92-1：drizzle-adapter/pg/@types/pg 锁定 |
| `frontend/package-lock.json` | `463C6D9468E78366AF824259D7537DD394E747C656DC036F5F2814B6F146AE7C` | 同上 |
| `frontend/tsconfig.json` | `6C264B874F2E1062D037B365E3920C9BBE4F3C94660D11B5FD6BB1A01B698125` | allowImportingTsExtensions（noEmit 已满足，非关闭 strict） |
| `frontend/round-93-auth-chain.mjs` | 保留为可复现探针（test_auth_idp_chain.py 依赖） | R92-1 证据 |

（`test_auth_integration.py` 哈希同 round-91 未变——既有用例保持；`frontend/auth-schema.ts` 未变。）

## 八、给 Codex 的复核点

1. 重放真实 IdP 链路（round-93-auth-chain.mjs + test_auth_idp_chain.py）：注册→登录→session 落库→停用→登录拒绝，Python 生产目录同源读取；
2. 复核 R92-2 首位 admin 流程、组织写操作同事务审计、含成员解绑拒绝、slug 不可变；
3. 复核 R92-3 全链规范化（大小写/无连字符等价矩阵）、member 唯一约束、歧义失败闭合；
4. 复核 R92-4 auth000002 往返（updated_at 默认恢复/约束增删）与 timestamptz 决策；
5. 独立执行 118 全量回归 + tsc exit 0 + T5 CLI，确认终态（auth000002、31 app 表 + 7 auth 表）与回滚复放；
6. 完整终验后裁决 **T7 COMPLETE**，再进入 **T8**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-93-->
