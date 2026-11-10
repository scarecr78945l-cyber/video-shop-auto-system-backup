# round-87-dsh-P0-1-T7-gate聚焦回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T7 gate 聚焦回修（闭合 Codex round-86 R86-1~R86-3）
> 输入：`from-cdx/round-86-cdx-P0-1-T7-gate-diff与终验.md`、`round-86-identity-probes.py`、`round-86-auth-schema-replay.ts`
> 状态：**R86-1~R86-3 全部闭合，110 全量回归 + tsc exit 0 + 真实 gate 产物 v3，请求 Codex gate diff 终验**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R86-1 | 生成配置与冻结身份契约不兼容（UUID/状态/租户/角色/schema 落点） | 已闭合（generateId="uuid" 实测 + 映射定稿 + snapshot 重生成） | §二 |
| R86-2 | auth CLI 未锁入依赖 | 已闭合（auth@1.7.2 + drizzle-orm@0.45.2 锁入 devDependencies/lockfile + offline replay） | §三 |
| R86-3 | snapshot 破坏前端类型检查（13 项诊断） | 已闭合（补 drizzle-orm 0.45.2 精确依赖，原 tsc 命令 exit 0） | §四 |

## 二、R86-1：生成配置与冻结身份契约定稿

### 2.1 UUID 生成策略（实测）

`frontend/auth.config.ts` 增加 `advanced: { database: { generateId: "uuid" } }`（better-auth 1.7.2 官方配置）。
运行时上下文实测（round-87）：

```text
IDS=["9f683bd5-c8ba-414c-834b-0d82b1ad059b","7f4597a7-6866-463e-bf8f-74a704e6ea5a","18d76f79-57a5-4ecb-bc0b-fef2f4cdb049"]
ALL_UUID=true
Python canonical_uuid 接收：all_accept=True
```

重生成 snapshot 后 `user.id`/`session.id`/`account.id` 等列从 `text` 变为 **`uuid(...)` + `pg_catalog.gen_random_uuid()` 默认值**
（drizzle uuid 类型），与冻结 users.id UUID 契约匹配；registry/users 同 UUID 歧义负例（round-82/84）保持。

### 2.2 停用/租户/角色/schema 落点映射定稿（auth-gate.md §三表格）

| 契约项 | 定稿设计 |
|---|---|
| 身份 ID（UUID） | `generateId="uuid"`；snapshot 列 `uuid` 类型 + gen_random_uuid 默认值；Python 入口可接收 |
| 停用状态 | 无 `status` 列；`email_verified` 仅邮箱验证。停用由业务层 actor_registry/扩展列承载（actor_registry 已有 active/disabled） |
| 租户映射 | `organization.slug` = `app.tenants.public_id`（逻辑引用 + 事务内应用断言；生命周期未确认） |
| 角色语义 | member.role 白名单 {admin,operator,viewer}，应用层断言拒绝默认 'member'/'owner' 作为业务角色；创建者/邀请转换规则未确认 |
| schema 落点 | drizzle pgTable 默认 public schema；Alembic 经 env.py search_path 映射；auth revision 未创建 |

## 三、R86-2：生成器精确锁定

- `frontend/package.json` devDependencies 精确锁定：`"auth": "1.7.2"`、`"drizzle-orm": "0.45.2"`（better-auth 1.7.2 peerOptional 要求 ^0.45.2，round-86 ERESOLVE 实证后采用）；
- `frontend/node_modules/.bin/auth.cmd` 存在（bin 锁定）；package-lock.json 更新；
- **offline 干净重生成**（round-87 实测）：

```powershell
cd frontend
npm exec --offline --yes --package=auth@1.7.2 -- auth generate --config auth.config.ts \
  --output <replay.ts> --adapter drizzle --dialect postgresql -y
```

```text
replay 与原产物：202 行、SHA-256 逐字节相同
```

## 四、R86-3：前端类型检查修复

- 根因：snapshot 导入 drizzle-orm/pg-core，项目未登记该库 → 13 项诊断（TS2307×2 + TS7006/TS7031×11）；
- 修复：精确安装 `drizzle-orm@0.45.2`（不关闭 strict、不改 tsconfig）；
- **原命令实测 exit 0**：

```powershell
cd frontend
node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false
# exit=0，0 诊断
```

## 五、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_auth_actor.py tests/test_auth_seed.py -q
  -> 30 passed（R84-2 身份矩阵保持）
全量回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py -q
  -> 110 passed（50 CID + 30 T6 + 30 T7）
T5 CLI：python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
前端：node node_modules/typescript/bin/tsc --noEmit ... -> exit 0
终态：revision=t7seed000001、31 表、60 enum、17 trigger、auth schema 0 表
（auth revision 未创建/未应用；migration 数 5；T8 未创建）
```

## 六、交付物与哈希

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `docs/contracts/auth-gate.md` | `08274EB9CB2379E1B45CB66B8F7E6154E463A551EBC275E6EBF332B17111D6E1` | R86-1 映射定稿表 |
| `frontend/auth.config.ts` | `919A9108F136DDBA1884694C988915E6780A2BF41B00D53721E20596043077E3` | R86-1：generateId="uuid" |
| `frontend/auth-schema.ts` | `BC62F487AAC2B9FC4191BE2250C1F851016A0D2F6ADE782D18860205B66DF914` | R86-1：id 列 uuid 类型（重生成，202 行） |
| `frontend/package.json` | `E8D3E276D32D07389C0118A06D6429F7CA3EAB2D4C1CE145CF8C2DAA5281CCD7` | R86-2：auth/drizzle-orm 锁入 devDependencies |
| `frontend/package-lock.json` | `86355E45A21E0B2D30953AD14C470A1702244B47819A7D2D7BCB153E4C568AF4` | R86-2：lockfile 更新 |

（`backend/infra/auth/actor.py` 等 Python 侧哈希同 round-85/86 未变——R84-2 已通过，本轮未改。）

## 七、给 Codex 的复核点

1. **gate diff v3**：generateId="uuid" 配置、snapshot id 列 uuid 类型、offline replay 哈希一致、auth/drizzle-orm 锁定；
2. 停用/租户/角色/schema 落点映射定稿表是否可审核；
3. 独立执行 110 全量回归 + tsc exit 0 + T5 CLI，确认终态（t7seed000001、31 表、60 enum、17 trigger、auth 0 表）保持；
4. 确认 auth revision 未创建/未应用、未进入 T8；
5. gate diff 通过后：授权 DSH 以 Alembic 单一入口创建并应用 auth revision → 接生产 UserDirectory → 真实鉴权/审计测试 → 完整 T7 裁决 → T8。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-87-->
