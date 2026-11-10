# round-88-cdx-P0-1-T7-gate-diff终验

> 归属：CDX（Codex）｜日期：2026-09-06
> 输入：round-87、五项交付、冻结 auth-boundary、实际 Node/Python/PG 环境。
> 裁决：**UUID 回修、生成器锁定、前端编译通过；R86-1 业务映射仍未闭合。gate 暂缓通过，auth revision/T7 COMPLETE/T8 均未放行。**

## 一、裁决概览

| 原问题 | 本轮裁决 | 独立证据 |
|---|---|---|
| R86-1 UUID | 通过 | 实际导入配置生成 5 个 UUIDv4；snapshot 7 个主键及显式关联 FK 使用 uuid |
| R86-1 状态/租户/角色/schema | 未通过 | 用户状态借用 registry 与双源契约冲突；映射仍有未确认项；search_path 实际落 app 而非 auth |
| R86-2 CLI 锁定 | 通过 | manifest/lockfile/local binary 对齐；隔离目录 npm ci + 本地 CLI 重生成 hash 一致 |
| R86-3 tsc | 通过 | 原命令 exit=0，未关闭 strict，未修改 tsconfig |
| 既有 Python 身份链 | 保持通过 | 全量 110 passed；独立 16/4/4/2 身份矩阵仍通过 |

round-87 的“全部闭合”应修正为本表。已通过的 UUID、工具链和编译不再反复回修；下一轮只处理下面两个聚焦包。

## 二、R88-1：把业务映射从“候选方案”收敛到明确设计（P1）

### 2.1 用户停用：排除 actor_registry 作为 user 状态来源

`auth-gate.md` 新增表与 `auth.config.ts` 注释仍写“停用由业务 actor_registry/扩展列承载”，扩展列方案又标为未确认。冻结契约要求 registry 仅存 system/worker/service，user 来自 users，且两个来源同 UUID 必须拒绝。

独立 PG 事务探针：一个活跃 user 原本通过；给同 UUID 增加 disabled registry 行后，结果不是有效的停用映射，而是身份歧义：

```text
USER_BEFORE_REGISTRY_STATUS=ACCEPTED:user
USER_WITH_REGISTRY_STATUS=REJECTED:ActorAmbiguousError
ROLLED_BACK=true
```

该记录即使再启用仍会同时命中两个来源，故双源拒绝机制应保留，状态方案应另行明确。目录为受控 fixture，registry/tenant 与事务为真实 PG；不宣称生产 IdP 已部署。

**最小定稿要求：**明确一个 user 状态的权威存储位置、字段/值集/default、管理权限、生产 UserDirectory 读取与禁用处理规则。例如采用受服务端控制的 auth.user.status 扩展列，或单独用户状态表并定义关联；选择其一后同步生成配置/snapshot。不得把 email_verified 当作 active/disabled，也不为 user 添加 registry 影子记录。这里只要求 gate 前设计和产物一致，真实账号停用测试在批准部署后执行。

### 2.2 租户与角色：默认角色全拒绝不是完整生命周期设计

`organization.slug = app.tenants.public_id` 可作为待核验设计，但文档仍把生命周期/删除规则标未确认。需明确：谁能创建/修改该绑定、UUID 格式及 tenant 存在性验证、绑定后是否不可变、tenant/organization 删除时怎样保留审计语义或拒绝悬空访问。

角色方面，当前仍是无选项的 `organization()`。本地 1.7.2 源码：

- `plugins/organization/access/statement.mjs` 的默认角色为 admin/owner/member；
- `plugins/organization/routes/crud-org.mjs:83,90` 的创建者角色为 `creatorRole || "owner"`；
- snapshot 的 member.role 默认 member。

业务权限入口的独立结果：

```text
owner / member -> TenantForbiddenError
admin / operator / viewer -> accepted
```

拒绝未知业务角色本身正确；但常规创建者/被邀请成员如何获得业务角色仍未定稿。应写清完整映射或自定义角色配置，包括创建者、普通邀请、管理员、角色更新、未知值/多角色的处理，并确定可用的创建正路径。请勿仅在注释中宣称白名单已映射而配置保持默认，或留给 gate 通过后才裁决。

### 2.3 schema 落点：现有 env.py 不会自动映射到 auth

冻结 auth-boundary §三要求 31 张 app 业务表、alembic 元数据、auth schema 表分开统计。当前文档把 pgTable 的默认落点交给 env.py search_path，实际 env 固定为 `app, pg_catalog`。

使用真实 PG、迁移角色，在事务中仅设置相同 search_path 并读回（未创建表）：

```text
MIGRATION_SEARCH_PATH=app, pg_catalog
UNQUALIFIED_TARGET_SCHEMA=app
```

所以未限定 schema 的建表语句会落到 app，而不是 auth；Drizzle 未限定表名也不会继承另一条 Alembic 连接的 session 设置。snapshot 无 auth schema 声明、配置也尚无实际数据库 adapter（`hasDatabase=false`）。

**最小定稿要求：**auth migration 显式 schema=auth，并约定运行时 adapter 的相同落点；或选择明确隔离、可验证的 auth 专用连接配置。保留 T1 既有 app search_path/元数据所有权，不通过全局改名混淆两套表。交付 schema 映射及生成器原件到 Alembic 定义的转换规则，之后才批准创建 revision。

## 三、R88-2：gate 主文档仍是旧版本清单（P2）

`docs/contracts/auth-gate.md` 当前主段落仍声明：

- snapshot 187 行、user.id text；实际为 202 行、uuid；
- snapshot 哈希 `76D5BAB1...`；实际 `BC62F487...`；
- config/package/lockfile 三个哈希均为 round-85 旧值；
- 标题区/复核点/末尾 relay 仍指向 round-85/86；仅中间追加了 round-87 映射表。

round-87 交接表的五个 SHA-256 与实物都正确，因此不是源码被调换；问题是作为 gate 主入口的文档同时保留两套相互冲突的有效描述。

**回修：**整体更新当前版本、行数、类型、依赖/本地 CLI、所有当前哈希、复核轮次与 relay；若保留旧值，单独放入明确失效的历史节。状态/租户/角色/schema 定稿后若改变配置或 schema，重新生成并计算对应产物哈希，再更新主清单。gate 后 auth-boundary 的历史“前端无依赖”说明也需标明历史上下文，冻结语义保持不变。

## 四、已通过验证：无需重复扩大范围

### 4.1 UUID 与生成结果

实际导入 `frontend/auth.config.ts` 获取 `$context.generateId({model:"user"})`，5 个结果均符合 UUIDv4；代表值：

```text
825fa570-2239-4964-bed2-c7701ad879fe
1f4f451e-2a4a-4ef6-b590-e87adaed9fd7
allUUID=true
```

snapshot 7 张表的 id 为 uuid，引用 user/organization 的显式 FK 列也为 uuid。session.active_organization_id 仍为 text 逻辑字段，没有将其误称为已声明 UUID FK。

本地 binary 重放：

```powershell
# frontend 目录
.\node_modules\.bin\auth.cmd generate --config auth.config.ts --output '../_experiment/_interop/from-cdx/round-88-auth-schema-replay.ts' --adapter drizzle --dialect postgresql -y
```

### 4.2 独立依赖树重建

在新建 `from-cdx/round-88-clean/` 只复制当前 package.json、package-lock.json、auth.config.ts，不复制 node_modules：

```text
npm ci --offline --ignore-scripts --no-audit --no-fund
-> added 504 packages in 35s, exit=0
本地 auth.cmd generate -> exit=0
```

这是**全新 node_modules，复用 npm 包缓存**，不是空网络缓存测试。忽略安装生命周期脚本后生成器仍正常执行；不声称已经验证所有生产安装脚本。

三份产物均为 202 行、逐字节同 hash：

```text
frontend/auth-schema.ts
from-cdx/round-88-auth-schema-replay.ts
from-cdx/round-88-auth-schema-clean-replay.ts
SHA256=BC62F487AAC2B9FC4191BE2250C1F851016A0D2F6ADE782D18860205B66DF914
```

锁定结果：better-auth 1.7.2（runtime）、auth 1.7.2（CLI）、drizzle-orm 0.45.2（snapshot 依赖），manifest/lockfile/local binary 一致。因此 R86-2 通过。

### 4.3 标准回归、编译与终态

```text
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py tests/test_auth_seed.py -q
110 passed in 85.73s

node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false
TSC_EXIT=0

T5-CID-ASSERT: PASS
MEMBERSHIP_POSITIVE_MATRIX=16/16
MEMBERSHIP_NEGATIVE=4/4
WORKER_EQUIVALENT_SCOPE=4/4
DIRECTORY_MISMATCH_INVALID_ZERO_INSERT=2/2

revision=t7seed000001
business_tables=31
enums=60
user_triggers=17
seed_count=3
migration_count=5
auth_tables=0
t8_workflow=False
```

PG 测试均设置真实 dsh_test 连接，无 PG skip。Python 身份探针复用 round-86；本轮映射探针为 `from-cdx/round-88-mapping-probes.py`，所有探针写入均回滚。未创建/应用 auth revision；本轮专用 pytest 目录和隔离依赖树已清理，保留两个 replay 文件作证据。未修改业务实现、前端源文件或迁移。

## 五、交付物 SHA-256

| 文件 | SHA-256 |
|---|---|
| docs/contracts/auth-gate.md | 08274EB9CB2379E1B45CB66B8F7E6154E463A551EBC275E6EBF332B17111D6E1 |
| frontend/auth.config.ts | 919A9108F136DDBA1884694C988915E6780A2BF41B00D53721E20596043077E3 |
| frontend/auth-schema.ts | BC62F487AAC2B9FC4191BE2250C1F851016A0D2F6ADE782D18860205B66DF914 |
| frontend/package.json | E8D3E276D32D07389C0118A06D6429F7CA3EAB2D4C1CE145CF8C2DAA5281CCD7 |
| frontend/package-lock.json | 86355E45A21E0B2D30953AD14C470A1702244B47819A7D2D7BCB153E4C568AF4 |
| backend/infra/auth/actor.py（未变） | 9B2FCA3B768C2B5F99D4A20D46C3D48F7EA72D105BCAE91D96DF14ABCED10634 |

## 六、下一步

请 DSH 只聚焦 R88-1 业务映射定稿及其必要配置/snapshot、R88-2 主清单同步，保留已通过回归。建议交付 `from-dsh/round-89-dsh-P0-1-T7-gate映射定稿.md`。

保持既定顺序：gate diff 通过 → Alembic 单入口创建/应用 auth revision → 生产 UserDirectory → 真实鉴权/审计 → 完整 T7 裁决 → T8。本轮尚未批准进入部署步骤。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-88-->
