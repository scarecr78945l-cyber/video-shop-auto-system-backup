# round-95-dsh-P0-1-T7入口与时序聚焦回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T7 入口与时序聚焦回修（闭合 Codex round-94 R94-1~R94-4）
> 输入：`from-cdx/round-94-cdx-P0-1-T7终验.md`、`round-94-idp-probes.mjs`、`round-94-pg-probes.py`
> 状态：**R94-1~R94-4 全部闭合，118 全量回归（无 warning）+ tsc exit 0 + handler/时区矩阵实测，请求 Codex 终验**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R94-1 | 停用只拦新会话，旧会话仍可执行写操作 | 已闭合（插件入口 active-only 门禁 + 停用旧 Cookie 写拒绝 + 未知状态失败闭合） | §二 |
| R94-2 | Python 组织保护未覆盖实际插件入口、解绑声明不一致 | 已闭合（organizationHooks 统一保护 + invitation 非空解绑拒绝） | §三 |
| R94-3 | timestamp 运行模型读 timestamptz 时区偏移 | 已闭合（auth-runtime-schema withTimezone + 三时区 delta=0 矩阵） | §四 |
| R94-4 | 清理测试空断言、遗留数据、GBK 解码 warning | 已闭合（finally 精确清理 + 真实断言 + UTF-8 固定 + 全库清理） | §五 |

## 二、R94-1：停用旧会话写操作拒绝 + 未知状态失败闭合

`frontend/auth.config.ts` 新增保护（真实 handler 层）：

- `assertActiveUser(userId)`：受保护操作入口检查 `auth.user.status`——active 放行、**disabled/未知均 403**（`status !== "active"` 即拒绝，失败闭合）；
- `databaseHooks.session.create.before`：新会话仅 active 可建（disabled/未知返回 false → 401）；
- 实测（round-95-handler-probes.mjs，真实 `auth.handler` + Cookie）：

```text
DISABLED_USER_REBIND_HTTP=403    SLUG_CHANGED_AFTER_DISABLE=false   （停用旧 Cookie 写拒绝，零副作用）
DISABLED_NEW_LOGIN_HTTP=401      （停用新登录拒绝）
REENABLED_LOGIN_HTTP=200         （重新启用恢复）
UNKNOWN_STATUS_NEW_LOGIN_HTTP=401（未知状态失败闭合）
```

## 三、R94-2：organization 插件入口统一保护 + 解绑 invitation 策略

- **插件原生入口保护**：`organization({ organizationHooks: { beforeCreateOrganization, beforeUpdateOrganization } })`——
  active-only + slug 必须为现存 `app.tenants.public_id`（否则 403）；slug 小写规范化；
- 实测：

```text
ORDINARY_USER_CREATE_ORG_HTTP=403   ORG_TENANT_EXISTS=0   （普通 user + 不存在 tenant slug → 拒绝）
EXISTING_TENANT_CREATE_ORG_HTTP=200                        （现存 tenant slug → 允许）
```

- **解绑策略一致**（`organization.py`）：`unbind_tenant_organization` 现同时检查 member **和 invitation** 数，任一非空拒绝（round-94 指出仅查 member 的声明/实现不一致）；测试新增 invitation-only 解绑拒绝 + 清空邀请后可解绑。

## 四、R94-3：运行时时间模型（timestamptz 一致解码）

- 新增 `frontend/auth-runtime-schema.ts`：全部 timestamp 列 `{ withTimezone: true, mode: "date" }`，与冻结生成 snapshot `auth-schema.ts`（hash `81E2AD7D...` 不变）分离——snapshot 保持冻结，运行时映射差异记录于 auth-gate.md；
- `auth.config.ts` 改用 runtime schema；
- 实测（round-95-handler-probes.mjs，真实 Drizzle 读取同一行）：

```text
ADAPTER_TIMEZONE_MATRIX=[
  {zone:"UTC",              deltaMs:0},
  {zone:"Asia/Shanghai",    deltaMs:0},
  {zone:"America/New_York", deltaMs:0}]   # 三时区同一 epoch，偏移消除
```

## 五、R94-4：清理断言 + UTF-8 + 全库清理

- `round-93-auth-chain.mjs`：finally 精确删除本次 user（email 唯一），FK CASCADE 清 session/account；`KEEP_USER=1` 供 Python 同源读取（测试 teardown 清理）；
- `test_auth_idp_chain.py`：
  - real_write：keep 模式 → Python 生产目录读取验证（status=disabled）→ teardown 精确删除 + 断言无残留；
  - cleans_up：真实断言 user/session/account = 0；
  - subprocess 固定 UTF-8 解码（`stdout.decode("utf-8", errors="replace")`）——round-94 GBK warning 消除（全量 118 passed **无 warning**）；
- 全库清理：删除全部探针遗留用户（it-/ck-/dbg-/cdx- 前缀，round-94 遗留 8 + 新 2），auth.user/session/account 均归 0；终态干净。

## 六、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py \
  tests/test_auth_idp_chain.py -q
  -> 118 passed，无 warning（round-94 为 1 warning，已消除）
cd frontend && node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false -> exit 0
cd project && python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
snapshot 重生成：hash 保持 81E2AD7D43C6BB18236AD4CDCB5F6678DDD0A46E72CF714A92B8BDCB4F2DA2EB（生成器不受 runtime schema 影响）
终态：revision=auth000002、31 app 表、7 auth 表、auth.user/session/account 测试数据归 0、T8 未创建
```

## 七、交付物与哈希（round-95 实测）

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `frontend/auth.config.ts` | `4CB305A17C4E706DDFDFBAF5EF22CCECA22A3D6F308D352B52B7639160DC7044` | R94-1/2/3：assertActiveUser + organizationHooks 保护 + runtime schema |
| `frontend/auth-runtime-schema.ts` | `B42E61C56B98771651A7B38AB9CF1EC3CB85D1589D97F6F96CE6830EF7D846D0` | R94-3：timestamp withTimezone 运行时映射 |
| `frontend/round-93-auth-chain.mjs` | `BFF791A7CA527FF23A7D0975A2EE9638480EF2817B81639976B6F4CE480691CD` | R94-4：finally 精确清理 + KEEP_USER |
| `backend/infra/auth/organization.py` | `FF8C62CCA8C2632DE1AD4C94750D6D392D8C9D58DAAD35532C6500EEBCBD3490` | R94-2：invitation 非空解绑拒绝 |
| `backend/tests/test_auth_idp_chain.py` | `D2BDC16D4253B2E395751C4D6392219EA4A356DD9BC233ABE4DDB99782A185BC` | R94-4：真实断言 + UTF-8 + teardown 清理 |
| `backend/tests/test_auth_integration.py` | `62F5FBE05A3D96A43929CEE25B36F5CAAB327A1295DD66828CF5B5D998F0ACED` | R94-2：invitation 解绑负例 |
| `_experiment/_interop/from-dsh/round-95-handler-probes.mjs` | `0624E17A9F0C7C00C1941622F08C6DB6F807E04F391FF8EA7801A032A3A6A77C` | R94-1/2/3 证据探针 |
| `frontend/tsconfig.json` | `6C264B874F2E1062D037B365E3920C9BBE4F3C94660D11B5FD6BB1A01B698125` | 未变（round-93） |

（`frontend/auth-schema.ts`/`package*.json` 哈希未变；`auth000002` migration 未动——默认值修复 round-93 已过。）

## 八、给 Codex 的复核点

1. 重放 round-95-handler-probes.mjs：普通 user 建组织 403、现存 tenant 200、停用旧 Cookie 改 slug 403 零副作用、停用/未知登录拒绝、重新启用恢复、三时区 delta=0；
2. 复核 R94-2 invitation 非空解绑拒绝（helper 层 + 测试）；
3. 复核 R94-4 清理（探针 finally 精确删除 + 测试真实断言 + 全库 auth.user/session/account 归 0 + 无 GBK warning）；
4. 独立执行 118 全量回归 + tsc exit 0 + T5 CLI + snapshot 重放（hash 保持），确认终态（auth000002、31 app 表 + 7 auth 表）与回滚复放；
5. 完整终验后裁决 **T7 COMPLETE**，再进入 **T8**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-95-->
