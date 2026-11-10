# auth-boundary.md — P0-0 批 C 契约：better-auth 身份边界

> 来源：round-18 §六.1（auth 契约四类验收）+ round-19 §六.1（冻结）+ round-20 §七（版本/插件/snapshot gate、迁移所有权、actor 双来源）。
> 用途：P0-1 T7（认证/审计基座）的唯一身份契约；真实微信登录态不属本包（§14.0 资源未确认）。

---

## 一、身份边界总览（冻结）

- **身份源**：better-auth（自托管 IdP）提供 `users`、`sessions`、`tenant_members`；
- **actor 双来源**：`actor_registry`（本地注册 system/worker/service）+ better-auth `users`（user 类 actor）；
- **业务表 actor_id**：`uuid`，不建跨外部 schema DB FK；应用层校验 + 审计 join；
- **真实微信登录态**：不属本包，属 §14.0 资源门禁（P0-3/P0-4）。

---

## 二、版本/插件/schema snapshot gate（round-20 §七，硬门禁）

better-auth 版本/插件集合当前**未确认**（`frontend/package.json` 无依赖）。P0-1 启动前的硬 gate：

```text
选择并锁定 better-auth version/plugins
→ 生成并哈希 auth schema snapshot（锁定生成器版本/生成哈希）
→ Codex diff 通过
→ P0-1 migration graph 才允许包含/应用 auth revision
```

- 在 gate 前，P0-1 可搭 migration 工具骨架，但**不创建 auth 表、不宣称 auth/audit 包完成**；
- 运行时禁止另一套工具自行改表（Alembic 为唯一部署入口）。

---

## 三、迁移所有权（冻结）

- better-auth 生成 schema snapshot（插件集合 + 生成器版本/哈希）；
- **Alembic 为唯一部署入口**应用该 snapshot；运行时禁止另一套工具自行改表；
- **三类对象分开 exact-set 统计**：
  - 31 张业务表（`app` schema，ddl-order W0~W8）；
  - `alembic_version`（迁移元数据）；
  - better-auth 表（auth schema，如 users/sessions/tenant_members）；
- 禁止用"32 表"等含混计数覆盖三类对象。

---

## 四、数据模型映射（冻结）

| better-auth 表 | 字段 | 与业务关系 |
|---|---|---|
| users | id uuid, email, status(active/disabled) | 业务 `actor_id` 引用；不建 DB FK |
| sessions | 由 better-auth 管理 | 认证会话 |
| tenant_members | user_id, tenant_public_id, role(admin/operator/viewer) | `tenant_public_id` → 业务 `tenants.public_id` 逻辑引用 |

- **ID 类型**：users.id 需 uuid；确认 better-auth adapter 可生成/保存（P0-1 gate 验证）；
- **废除"UUIDv7 前缀"表述**：改为「UUID 类型 + 生成策略/namespace 互斥 + collision test」。

---

## 五、actor 双来源唯一命中（冻结）

- `actor_registry` 只登记 `system/worker/service`（含 stable UUID）；
- user 类 actor 走 better-auth `users`；
- **写审计前验证恰好命中一个来源**（0 或 2 都拒绝），避免 registry/users 同 UUID 歧义；
- 审计 join 顺序：先 registry 后 users。

---

## 六、租户成员与权限（冻结）

- `tenant_members.tenant_public_id → tenants.public_id` 逻辑引用；
- `active/disabled` 状态、角色值 `admin/operator/viewer`；
- 跨 tenant membership 拒绝：用户不可在未授权 tenant 下操作；
- 后台 worker 租户上下文：worker 任务须显式声明所属 tenant（经 workflow_run/任务 scope）；
- 外部 schema 不建 DB FK 时，用**事务内应用断言 + 审计证据**补足。

---

## 七、RLS 与审计（冻结）

- **P0**：组合 FK + 应用断言（不使用 DB 级 RLS 作为隔离手段）；
- **P1 可选增强**：RLS session 变量（`app.current_tenant_id`/`app.current_actor_id`）——P0 不依赖；
- 审计写入：`audit_events` 带 actor_id / target_type / target_public_id / request_id（v6 §6.4）；
- request_id 贯通：前端/API/worker 同一请求链路复用。

---

## 八、验收（四类 + 四补项，round-18/20 冻结）

**四类必过**：
1. 伪造 actor_id 被拒绝；
2. 跨 tenant membership 被拒绝；
3. 停用用户被拒绝；
4. 后台 worker 带正确租户上下文可执行。

**四补项**：
5. 双命中 actor（registry+users 同 UUID）被拒绝；
6. 未知 tenant_public_id 被拒绝；
7. role 越权被拒绝；
8. request_id 贯通断言。

---

## 九、变更规则

- better-auth 版本/插件变更：先过 §二 gate（重新生成/哈希 snapshot + Codex diff）；
- 新增 actor 类型：更新 `actor_registry` 种子 + 本表，不经静默。
