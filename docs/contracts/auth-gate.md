# auth-gate.md — better-auth version/plugins/schema snapshot gate 交付

> 来源：auth-boundary.md §二（round-20 §七 硬门禁）；round-82 R82-1；round-84 R84-1；round-87 R86-1；
> round-89 R88-1/R88-2；round-95 R94-3；round-97 R96-1/R96-2 同步。
> 状态：**gate 已通过（round-90），auth revision 已应用（round-91/93）**；本文件为**当前有效清单**（round-97 同步）。
> 历史内容（round-85/87/89 版本）仅存档，不再作为当前依据。

---

## 一、gate 流程（auth-boundary §二 冻结）

```text
① 选择并锁定 better-auth version/plugins   <- 已完成（round-85 起，§二）
② 生成并哈希 auth schema snapshot           <- 已完成（§四，hash 81E2AD7D...，round-90 通过）
③ Codex diff 通过                          <- 已完成（round-90）
④ P0-1 migration graph 应用 auth revision   <- 已完成（auth000001 round-91、auth000002 round-93）
```

## 二、锁定版本与插件（当前有效清单，round-97）

| 项 | 锁定值 | 证据 |
|---|---|---|
| better-auth（运行时） | `1.7.2` | `frontend/package.json` dependencies `"better-auth": "1.7.2"`；lockfile 含 `@better-auth/core 1.7.2` |
| auth CLI（生成器） | `1.7.2` | devDependencies `"auth": "1.7.2"`；`node_modules/.bin/auth.cmd` |
| @better-auth/drizzle-adapter | `1.7.2` | devDependencies（round-93 R92-1 接入真实 PG adapter） |
| pg / @types/pg | `8.16.3` / `8.15.4` | devDependencies（round-93） |
| drizzle-orm | `0.45.2` | devDependencies（snapshot 依赖） |
| 运行时完整性 | `sha512-gKapKBEvYIGcMxi74RjQ7EbFLiqyQt58vdoJmL1qAlWSkY1Bc2Vqshl524/3u1NxauiOU03M/Ebh762Brmac9A==` | `npm view better-auth@1.7.2 dist.integrity` |
| 认证 | `emailAndPassword: { enabled: true }`（内建） | `frontend/auth.config.ts` |
| 插件 | `organization()` + **organizationHooks 全写入口禁用**（round-97 R96-1；round-99 R98-1 修正键名） + **导出 handler 路由层统一拦截**（含 leave 等无 hook 路径） | `frontend/auth.config.ts` |
| 适配器 | drizzleAdapter（pg）+ node-postgres，search_path=auth | `frontend/auth.config.ts` |

## 三、身份/状态/租户/角色/schema 映射定稿（round-89 + round-97）

| 契约项 | 定稿设计（当前有效） |
|---|---|
| 身份 ID | `generateId="uuid"`；snapshot 7 表 id 及显式 FK 列 uuid 类型；Python canonical_uuid 可接收 |
| 用户停用 | 权威来源 `auth.user.status` 扩展列（text default 'active'，input:false）；**新会话仅 active 可建**（round-95 R94-1）；**受保护操作入口 active-only**（round-97 R96-1） |
| 租户绑定 | `organization.slug = app.tenants.public_id`（canonical_uuid 全链）；**组织生命周期统一由 Python helper 管理（service/worker 专属 + 角色白名单 + 不可变绑定 + 事务审计）**；organization 插件全部原生写入口禁用——**双层**：organizationHooks 全写 hook 403（键名对照 1.7.2 实际调用点：beforeCreateOrganization/beforeUpdateOrganization/beforeDeleteOrganization/beforeAddMember/beforeUpdateMemberRole/beforeRemoveMember/beforeCreateInvitation/beforeAcceptInvitation/beforeRejectInvitation/beforeCancelInvitation）+ 导出 handler 路由层拦截 leave/team 等无 hook 写路径（round-99 R98-1 实测有效 org/member/invitation 上 active/disabled 全 403、零副作用） |
| 角色语义 | member.role 白名单 {admin,operator,viewer}；首位 admin 由服务端显式分配（first_admin_user_id）；'member'/'owner'/未知拒绝 |
| schema 落点 | auth revision 显式 schema=auth（auth000001/2）；alembic_version 留 app schema；三类对象分开统计（31 app 表 / alembic 元数据 / 7 auth 表） |

## 四、schema snapshot 与运行时 schema（round-97 同步）

- **生成 snapshot**（冻结）：`frontend/auth-schema.ts`，hash `81E2AD7D43C6BB18236AD4CDCB5F6678DDD0A46E72CF714A92B8BDCB4F2DA2EB`（round-90 通过后未变）；
- **运行时 schema**（round-95 R94-3）：`frontend/auth-runtime-schema.ts`——全部 timestamp 列 `{ withTimezone:true, mode:"date" }`（timestamptz 解码一致，消除时区偏移）；与生成 snapshot 分离，hash `B42E61C56B98771651A7B38AB9CF1EC3CB85D1589D97F6F96CE6830EF7D846D0`；
  - 差异说明：runtime schema 在 snapshot 基础上：(a) timestamp 加 withTimezone；(b) updated_at 声明 defaultNow（snapshot 的 user/verification 有 DB 默认，session/account 无——运行时 $onUpdate 由 better-auth 维护，DB 默认语义经 auth000002 对齐）；(c) 关系集合等价；
- **已应用 Alembic revision**：`auth000001`（7 表落库）+ `auth000002`（member 唯一约束 + session/account.updated_at 默认移除）；head=auth000002。

## 五、gate 通过后边界（round-97 重申）

- auth schema 7 表已部署（user/session/account/verification/organization/member/invitation）；
- actor_registry（app schema）与 audit_events（app schema）为真实业务表；组织写操作同事务审计（round-93 R92-2）；
- organization 插件原生写入口**禁用**（round-97 R96-1），组织生命周期仅经 Python helper；
- 完整 T7 双源校验依赖 UserDirectory（R82-2）；auth revision 已应用，无 T8 workflow 目录。

## 六、Codex 复核点（round-97）

1. §二依赖清单（含 drizzle-adapter/pg/@types/pg）与 package.json/lockfile 哈希一致；
2. §四 snapshot hash 81E2AD7D...（round-90 冻结）与 runtime schema hash B42E61C5... 分离说明可审核；
3. §三映射定稿（service/worker 生命周期、全入口禁用、active-only）与 auth.config.ts/organization.py 一致；
4. 已应用 revision（auth000001/2，head=auth000002）与迁移往返复放；
5. gate 复核通过后进入完整 T7 终验。

## 七、历史清单（已失效，仅存档）

- round-85 v2（187 行/text id/76D5BAB1）；round-87 v3（202 行/uuid/BC62F487）；round-89 v4（203 行/status 列/81E2AD7D）；
- round-89 时代「auth revision 未创建/未应用」状态已过时（round-91 已应用）。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-97-->
