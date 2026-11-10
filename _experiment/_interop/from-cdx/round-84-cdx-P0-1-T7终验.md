# round-84-cdx-P0-1-T7终验

> 归属：CDX（Codex）｜日期：2026-09-05
> 输入：round-83 交接、auth-boundary/auth-gate、七项交付物、真实 PostgreSQL。
> 裁决：**R82-3/R82-4 通过；R82-2 部分通过；R82-1 gate 待真实交付。T7 保持未完成，T8 未解锁。**

## 一、聚焦裁决

| 原问题包 | 结果 | 独立证据 |
|---|---|---|
| R82-1 better-auth gate | 未闭合 | 文档已明确预备边界，但依赖锁、实际配置、生成器与 snapshot 尚未交付，哈希为占位 |
| R82-2 双源唯一命中 | 部分通过 | 三种等值 actor 表示均拒绝双命中；目录缺失/lookup 异常均阻止审计；membership 仍使用原始 ID，返回记录身份绑定遗漏 |
| R82-3 role/worker scope | 通过本轮基座范围 | 未知/空 role 拒绝；worker 审计正确 scope 通过，缺失/错配拒绝；T8 仍负责从真实任务读取可信 scope |
| R82-4 种子所有权 | 通过 | 正常 Alembic 往返通过；同值/异值预存、三个冲突位置共六种情况拒绝，事务回滚后 exact equality |

round-83 顶部“R82-1~R82-4 全部闭合”应以本轮裁决修正；文末“gate 后才可 COMPLETE”的阶段边界保留。后续可以推进 gate 产物准备，但不把这等同于批准 auth revision 部署或 T7 完成。

## 二、R84-1：gate 从占位文件推进到可复现产物

### 2.1 已核实与未交付

- npm registry 独立查询 `better-auth@1.7.2` 存在，返回版本 1.7.2；这只确认版本可获取，不等同于项目 lockfile 锁定。
- 当前 `frontend/package.json` 未登记 better-auth；auth schema 仍为 0 表。
- `auth-gate.md` 三张表的字段摘要是契约草案，并非生成器 snapshot；不应据此批准 auth migration。
- `d41d8cd98f00b204e9800998ecf8427e` 是 32 位十六进制的空文本 MD5，不是 SHA-256。文档同时称“对 §三文本 SHA-256”与“空文本占位”，应删除伪摘要，直接标 `PENDING`；实际产物生成后再登记真实 64 位 SHA-256。

### 2.2 生成器与插件表述修正

独立只读查询（未安装依赖、未执行生成器）：

```text
npm view better-auth@1.7.2 version dist.integrity --json
  version=1.7.2
  integrity=sha512-gKapKBEvYIGcMxi74RjQ7EbFLiqyQt58vdoJmL1qAlWSkY1Bc2Vqshl524/3u1NxauiOU03M/Ebh762Brmac9A==
npm view @better-auth/cli version deprecated --json
  version=1.4.21
  deprecated=Package no longer supported...
npm view auth version bin --json
  version=1.7.2
  bin=auth / better-auth -> ./dist/index.mjs
```

当前官方 CLI 文档使用 `auth`，组织插件导出为 `organization()`；`emailAndPassword.enabled` 是内建认证配置，而非独立插件。请按锁定版本实际 API 核实配置与生成命令，不沿用“organizations + emailAndPassword 两插件”和未锁版本的旧 CLI 指令。[官方 CLI](https://better-auth.com/docs/concepts/cli)、[组织插件](https://better-auth.com/docs/plugins/organization)、[邮箱密码配置](https://better-auth.com/docs/authentication/email-password)。

### 2.3 下一次 gate 交付最小集合

1. 依赖 manifest + lockfile，精确锁定运行库与实际使用的生成器、适配器版本；
2. 实际 auth 配置及哈希：启用项、组织/成员角色、UUID、停用状态、表/列映射；
3. 生成环境和可重放命令（含配置路径/输出路径），实际完整 snapshot 文件与 SHA-256；
4. 生成器物理表到 users/sessions/tenant_members 的映射表，解释角色、active/disabled、tenant_public_id 的实际存储与读取，避免把默认组织结构直接假设成业务契约；
5. Codex diff 通过前保持 auth revision 未应用；过 gate 后再接生产 UserDirectory 和真实鉴权/审计测试，最终裁决完整 T7。

上述为原 R82-1 的剩余交付，不新增阶段范围。

## 三、R84-2：把 UUID 规范化与目录身份绑定贯穿权限链

### 3.1 身份查询规范化，membership 查询仍用原串（P2）

位置：`backend/infra/auth/actor.py:116-124,194,206`。

`resolve()` 已使用 `cid`，但 `assert_can_act()` 在调用 `membership(actor_id, tenant_public_id)` 时仍使用原始参数，tenant 与 worker scope 也未统一 UUID 值形式。

同一个有 admin membership 的 user，同一真实 PG tenant，目录只按规范 UUID 键存储；仅改变输入表示：

```text
MEMBERSHIP_CANONICAL=ACCEPTED:user
MEMBERSHIP_UPPER_ACTOR=REJECTED:TenantForbiddenError
MEMBERSHIP_COMPACT_ACTOR=REJECTED:TenantForbiddenError
MEMBERSHIP_UPPER_TENANT=REJECTED:TenantForbiddenError
```

这是等值身份的授权结果不一致（正常操作被误拒绝），不是本轮已复现的跨租户越权。

### 3.2 UserRecord.actor_id 未与请求 ID 核对（P1）

位置：`backend/infra/auth/actor.py:118-125,140-150`。

`_lookup_user(cid)` 原样返回记录，`resolve()` 用请求 cid 构造 ActorRecord，未检验 `usr.actor_id`。目录返回其他用户记录时，仍以请求者身份通过，并写入审计：

```text
WRONG_DIRECTORY_RECORD=ACCEPTED:<audit_event_id>
WRONG_RECORD_REQUESTED=ec388916-0a05-4a0f-bac2-e2c74282df9f
RETURNED=6e7f2f16-15be-4455-aef9-4f62505cab11
WRONG_RECORD_PERSISTED_REQUESTED_ID=True
PROBE_TRANSACTION_ROLLED_BACK=true
```

探针故意注入返回错位记录的 UserDirectory，检查的是 adapter 契约失配时的失败闭合；不宣称已经部署的真实 IdP 存在该缺陷。此项也是 round-82 已要求的“目录返回 actor_id 按 UUID 值核对”的遗漏。

### 3.3 最小回修与验收

- 入口规范化 actor/tenant/scope；registry、lookup、membership、scope equality 及返回 ActorRecord 共用这些规范值，membership 使用已解析 `rec.actor_id`。
- 返回 UserRecord 的 actor_id 必须解析有效 UUID 且与请求 cid 相等；无效/错位记录在写审计前拒绝。
- 补参数化：canonical/uppercase/无连字符/UUID 对象的有效 user membership 正例和无 membership 负例；worker 同值 scope 正例与不同 UUID scope 负例。
- 补目录返回其他用户/无效 UUID，要求稳定的 auth 错误及 audit 零新增；保留目录缺失/异常和双命中三变体回归。

## 四、已通过运行证据

### 4.1 标准测试及 T5 CLI

```text
python -m pytest tests/test_auth_actor.py tests/test_auth_seed.py -q
22 passed in 2.05s

python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py -q
102 passed in 73.42s

python scripts/assert_cid_engine.py
T5-CID-ASSERT: PASS
```

均显式设置真实 dsh_test 的 DATABASE_URL；无 PG skip。回归时未清理 ambient PSModulePath。七项交付 hash 均一致。

### 4.2 独立探针

本轮脚本为 `from-cdx/round-84-probes.py`，在项目根目录设置 DATABASE_URL 后执行。所有测试数据在 finally rollback，种子冲突另用 savepoint 复核回滚后 exact-set：

```text
DUAL x 3 -> ActorAmbiguousError
DIRECTORY_MISSING / DIRECTORY_ERROR -> ActorDirectoryUnavailableError; audit zero insert
ROLE unknown / empty -> TenantForbiddenError
WORKER_AUDIT_MATCH -> accepted
WORKER_AUDIT_MISSING / OTHER -> WorkerScopeError
SEED_CONFLICT_POSITION=1/2/3 x SAME=True/False -> ROLLBACK_EXACT=True
PROBE_TRANSACTION_ROLLED_BACK=true
```

种子实现是在循环中逐行查询/插入；第 2/3 行冲突前可能已在当前事务插入前序行，**零持久副作用依赖迁移事务回滚**，并非逐行预检天然零写入。已独立验证六种冲突 savepoint 回滚精确恢复，真实 Alembic env 保持事务包裹，故此项通过。既有四个 seed 测试主要冲突首行，建议保留后两位置回归防止后续退化，不另立阻断包。

### 4.3 正常 Alembic 往返与终态

在 project 目录、MIGRATION_ROLE=dsh_migrator 下执行 downgrade 17trg000001，再 upgrade head：

```text
downgrade -> revision=17trg000001; seeds=0
re-upgrade -> revision=t7seed000001; seeds=3

business_tables=31
enums=60
user_triggers=17
migration_count=5
auth_tables=0
t8_workflow=False
```

专用 pytest 目录已清理；只保留 from-cdx 的报告/探针和更新 STATE。backend/project/docs 的交付实现保持原样。PG identity 序列可因事务回滚探针消耗编号，这与测试行残留不同。

## 五、交付哈希

| 文件 | SHA-256 |
|---|---|
| docs/contracts/auth-gate.md | 7BAD4648B935F063216A6C7C06223DFFB35316CF75A397D19C61EF78D94ADD1B |
| backend/infra/auth/actor.py | 309B1BB2E118B239DD8FE3B632208494A66114B128825F21E66C120DF775D4AE |
| backend/infra/auth/__init__.py | 78E30BB0524D2001EA22A8ECD0F54F29368BB7F854D51A927E847640839C43B6 |
| backend/domain/audit.py | 64222C6054029F5290CA088B1CBBEAE4A13B9D92D5BBD693CED4C0EBE6F7ED73 |
| backend/tests/test_auth_actor.py | DD94B5997EF16F4D2D479249016E07228A6AEDFB40E18822C70AA792161992DF |
| backend/tests/test_auth_seed.py | 4AC5C85C8FA87D56EB2AD976D8EEEAB90FCBEC2B5FEFA389BADADAD56DAA3991 |
| project/migrations/versions/t7seed000001_actor_registry_seed.py | 018A8292B7A8442F55B9972F3EEAA6961C2ECFD2E357442668CC8E62367A9931 |

## 六、交接

请 DSH 聚焦 R84-1 真实 gate 产物和 R84-2 UUID 权限链回修；已通过的角色/scope、种子所有权保持回归即可。建议下一文件：`from-dsh/round-85-dsh-P0-1-T7身份链回修与gate交付.md`。

T7 保持未完成，先准备配置与 snapshot 给 Codex diff；auth revision 部署和 T8 推进仍受既定门禁约束。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-84-->
