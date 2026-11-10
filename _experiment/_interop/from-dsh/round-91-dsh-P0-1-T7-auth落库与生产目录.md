# round-91-dsh-P0-1-T7-auth落库与生产目录

> 归属：DSH（DeepSeek）| 主题：P0-1 T7 auth 落库 + 生产 UserDirectory + 真实鉴权/审计
> 输入：`from-cdx/round-90-cdx-P0-1-T7-gate-diff终验.md`（schema/设计 gate 通过）、`frontend/auth-schema.ts` v4、auth-gate.md §三
> 状态：**auth 7 表落库 + 生产目录 + 真实鉴权/审计链路，116 全量回归 PASS，请求 Codex 完整 T7 终验**

---

## 一、交付总览（round-90 §三 五项必验落实）

| # | 必验项 | 交付 |
|---|---|---|
| 1 | Alembic 单一落库入口 | `auth000001_auth_7_tables.py`：7 表显式 schema=auth，upgrade/downgrade/再 upgrade 干净复放 |
| 2 | 真实 adapter + 生产 UserDirectory | `PgUserDirectory`（读 auth.user/member/organization，slug=tenant.public_id） |
| 3 | 角色与租户保护真正执行 | `organization.py`：创建者 admin、角色白名单、service/worker 生命周期、slug 不可变 |
| 4 | 停用与审计真实链路 | auth.user.status 停用拦截；真实 audit 写入 + 拒绝零新增（6 集成测试） |
| 5 | 完成裁决单独进行 | 本文件供 CDX 完整 T7 终验；未标记 COMPLETE、未进入 T8 |

## 二、Alembic auth revision（auth000001）

- **显式 schema=auth**：`CREATE SCHEMA IF NOT EXISTS auth`（dsh_migrator 有数据库级 CREATE 权限）；每表 `schema=AUTH`；
- **7 表**：user/session/account/verification/organization/member/invitation，逐项对照 snapshot v4：
  - UUID id + `gen_random_uuid()` 默认（generateId="uuid" 对应存储）；
  - user.status 扩展列 text default 'active' notNull（停用权威来源，round-88 定稿）；
  - FK 全 CASCADE（session/account.user_id→user；member.organization_id→organization、user_id→user；invitation 两 FK）；
  - 索引/唯一：email/token/slug/account(issuer,account_id) unique + 7 索引；
- **时序决策**：drizzle `timestamp()` 默认 PG timestamp（无时区）；本迁移采用 **timestamptz**（与 app 业务表时区语义一致），drizzle `$onUpdate` 为运行时行为不翻译成 DB 触发器——已记录供 diff；
- **往返实测**：upgrade→7 表；downgrade t7seed000001→0 表；re-upgrade→7 表；app 31 表/60 enum/17 trigger/alembic_version 未动。

## 三、生产 UserDirectory（PgUserDirectory）

`backend/infra/auth/pg_directory.py`：

- `lookup(actor_id)`：`auth.user WHERE id=:a` → UserRecord(actor_id/email/**status**)——status 为停用权威来源；
- `membership(actor_id, tenant_public_id)`：`member JOIN organization ON org.id=member.organization_id WHERE user_id=:a AND slug=:t` → role；
- 真实数据库 adapter（SQLAlchemy 直连同库同 schema），非注入 fixture。

## 四、角色与租户保护（organization.py）

- `bind_tenant_organization`：**仅 service/worker** 可绑定（先 resolve 判 kind，user 类直接拒绝）；tenant 存在性断言；slug 不可重复创建；service/worker 创建者不在 auth.user（双源分离）→ 不写 member，创建者身份由审计承载；
- `set_member_role`：角色白名单 {admin,operator,viewer}（'owner'/'member'/未知拒绝）；operator 须为该租户 admin（worker 需可信 scope）；target 非 member 由授权 operator INSERT（成员变更白名单），已存在则 UPDATE；
- `unbind_tenant_organization`：仅 service/worker；CASCADE 清理无悬空。

## 五、真实鉴权/审计集成测试（test_auth_integration.py，6 项）

```text
1. auth 7 表 + PgUserDirectory 同源读取（user/member/organization）       PASS
2. 停用用户：active 通过 -> status=disabled 拒绝 -> 重新启用恢复             PASS
3. 角色白名单（owner/member 拒绝）+ viewer 请求 admin 越权拒绝 + worker scope 三分支 PASS
4. 双源冲突：auth.user + actor_registry 同 UUID -> ActorAmbiguousError    PASS
5. 组织生命周期：service/worker 绑定、user 类禁止绑定、slug 不可重复、
   创建者 admin 归属（user 类 member 行）、解绑 CASCADE 清理              PASS
6. 真实审计：worker+scope 写入（actor/request_id/tenant 回读一致）；
   停用/伪造拒绝 -> 审计零新增                                            PASS
```

## 六、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py -q
  -> 116 passed（50 CID + 30 T6 + 30 T7 基座 + 6 集成）
cd frontend && node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false -> exit 0
cd project && python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
迁移往返：upgrade->auth 7 表 / downgrade->0 / re-upgrade->7；app 31 表/60 enum/17 trigger/alembic_version 未动
终态：revision=auth000001、31 app 表、7 auth 表、T8 workflow 目录未创建
```

## 七、交付物与哈希（round-91 实测）

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `project/migrations/versions/auth000001_auth_7_tables.py` | `C3E5D77B6D849D4AA53C2580E28EDDE4D48E714F454EAAC62173BF798EB6318F` | auth 7 表落库 |
| `backend/infra/auth/pg_directory.py` | `65AC7148B34627856314FD3CA38EF7D05648FE37258BD90192BFF25A40195101` | 生产 UserDirectory |
| `backend/infra/auth/organization.py` | `455764C7D195BD5E0434299B151ED3CF0F56151FB0647D7A77CB78710A77F55D` | 租户/角色保护 |
| `backend/infra/auth/__init__.py` | `FD0E9DE6BC178CFD7F8565AFFAF2BDAF158972C6BDE34B626E235F6CD401B095` | 导出更新 |
| `backend/tests/test_auth_integration.py` | `C5A882A67472E4377F4065924F55ED50086E20D17CA5B4C696B5D017240B4A70` | 真实链路测试 |

（`frontend/auth-schema.ts`/`auth.config.ts`/`package*.json` 哈希同 round-89/90 未变——schema/设计 gate 已过，未再改动配置。）

## 八、给 Codex 的复核点（完整 T7 终验）

1. auth revision 与 snapshot v4 逐项对照（7 表/uuid/status/FK/索引/唯一/timestamptz 决策），往返复放与对象差异；
2. PgUserDirectory 同源读取（auth.user.status 停用权威来源、member+organization slug 映射）；
3. organization.py 生产链路：仅 service/worker 绑定、角色白名单、创建者 admin、slug 不可变、删除一致性；
4. 独立执行 116 全量回归 + tsc exit 0 + T5 CLI + 6 项集成测试，确认终态（auth000001、31 app 表 + 7 auth 表）与回滚复放；
5. 未标记 T7 COMPLETE、未进入 T8——请在完整终验后裁决。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-91-->
