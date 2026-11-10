# round-99-dsh-P0-1-T7写入口与失败清理回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T7 写入口与失败清理回修（闭合 Codex round-98 R98-1/R98-2）
> 输入：`from-cdx/round-98-cdx-P0-1-T7终验.md`、`round-98-existing-org-probes.mjs`、`round-98-cleanup-fault-probe.py`
> 状态：**R98-1/R98-2 全部闭合，119 全量回归无 warning + tsc exit 0 + 有效组织写入口矩阵实测，请求 Codex 终验**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R98-1 | hook 键名无效 + leave/邀请状态流写入口未封禁 | 已闭合（修正实际键名 + 全写入口双层封禁 + 有效组织矩阵） | §二 |
| R98-2 | 子进程失败路径跳过清理 | 已闭合（try/finally 全覆盖 + 预生成 fixture 定位 + 故障注入测试） | §三 |

## 二、R98-1：organization 全写入口双层封禁（对照实际调用点）

### 2.1 hook 键名修正（round-98 指正）

| 配置位置 | round-97 旧键 | 修正键（better-auth 1.7.2 实际读取） |
|---|---|---|
| 成员角色更新 | `beforeUpdateMember` | **`beforeUpdateMemberRole`**（crud-members.mjs:340） |
| 邀请创建 | `beforeInviteMember` | **`beforeCreateInvitation`**（crud-invites.mjs:207） |

### 2.2 全写入口双层封禁（`frontend/auth.config.ts`）

**第一层——organizationHooks（插件内）**：10 个写 hook 全部 403——
`beforeCreateOrganization / beforeUpdateOrganization / beforeDeleteOrganization / beforeAddMember /
beforeUpdateMemberRole / beforeRemoveMember / beforeCreateInvitation / beforeAcceptInvitation /
beforeRejectInvitation / beforeCancelInvitation`。

**第二层——导出 handler 路由层拦截**（覆盖 leave/team 等无 hook 写路径）：`orgWriteGuard` 对
`/api/auth/organization/` 下 17 个写端点（create/update/delete/set-active/invite/cancel/accept/reject/
add-member/update-member-role/remove-member/leave/create-team/update-team/remove-team/add-team-member/
remove-team-member）的 POST 统一 403；GET/HEAD/OPTIONS 读取放行。`export async function handler()` 包裹
`auth.handler`，应用侧使用 `handler` 而非 `auth.handler`。

### 2.3 有效组织矩阵实测（round-99-handler-probes.mjs，连续两次 exit 0 可重放）

用 Python helper（生产路径）创建有效 org/admin/viewer + 2 条审计，然后真实 IdP Cookie 调 handler：

```text
HELPER_SETUP_AUDIT_ROWS=2            HELPER_ASSIGNED_ROLES=["admin","viewer"]
ACTIVE_VIEWER_UPDATE_ROLE_HTTP=403   # active 未授权改角色
ACTIVE_VIEWER_INVITE_HTTP=403        # active 未授权邀请
ACTIVE_VIEWER_LEAVE_HTTP=403         # active 未授权 leave（round-98 指出的遗漏路径）
DISABLED_UPDATE_HTTP=403             # 停用旧 Cookie update
DISABLED_ROLE_UPDATE_HTTP=403        # 停用旧 Cookie 改角色
DISABLED_INVITE_HTTP=403             # 停用旧 Cookie 邀请
DISABLED_LEAVE_HTTP=403              # 停用旧 Cookie leave
DISABLED_NEW_LOGIN_HTTP=401          # 停用新登录拒绝
ROLE_UNCHANGED=viewer  INVITATION_ROWS=0  MEMBER_ROWS=2   # 零副作用
PLUGIN_ACTOR_AUDIT_ROWS=0            # 插件写无审计产生
PROBE_USER_ROWS=0  PROBE_TENANT_ROWS=0  # fixture 精确清理
```

> round-98 反例（停用 admin 改 member/创建取消邀请、停用成员 leave 删除 membership）已全部 403 且零副作用。

## 三、R98-2：失败路径清理（try/finally 全覆盖 + 预生成定位 + 故障注入）

`backend/tests/test_auth_idp_chain.py` 重写：

- **子进程调用与全部断言纳入 try/finally**：清理不再只包部分断言（round-98 指出早期断言失败会跳过）；
- **调用前预生成唯一 fixture email**（`FIXTURE_EMAIL` 传给探针）——异常发生在返回 user_id 前也能定位；
- 清理优先 `user_id`、回退 email（`_cleanup_user_committed` / `_cleanup_user_by_email`），独立提交 + 新连接断言；
- **故障注入测试** `test_idp_chain_failure_path_cleans_up`：真实 KEEP_USER 链路产生 user → 注入 AssertionError → finally 精确清理 + `_assert_no_remaining` 断言无残留；
- 探针 `round-93-auth-chain.mjs` 支持 `FIXTURE_EMAIL`（外部预生成唯一标识）。

## 四、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py tests/test_auth_integration.py \
  tests/test_auth_idp_chain.py -q
  -> 119 passed（118 + 1 故障注入清理），无 warning
cd frontend && node node_modules/typescript/bin/tsc --noEmit --incremental false --pretty false -> exit 0
cd project && python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
探针：round-99-handler-probes.mjs 连续两次 exit 0，有效 org 矩阵全 403 + 零副作用 + fixture 归 0
终态：revision=auth000002、31 app 表、7 auth 表、auth.user=0、T8 未创建
```

## 五、交付物与哈希（round-99 实测）

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `frontend/auth.config.ts` | `F63F04D5FB86B61A77F67D88B4AD090A561BCA438FE826E60C74B65404AD059C` | R98-1：hook 键名修正 + 10 hook 全封禁 + handler 路由层 17 写端点拦截 |
| `frontend/round-93-auth-chain.mjs` | `EE98B8B365759F056B5ECBD1D52CCB46EFA0D9C8BD7C9C39F43F8A6D1DCAC905` | R98-2：FIXTURE_EMAIL 预生成定位 |
| `backend/tests/test_auth_idp_chain.py` | `3F7029675C808D49AD75B4524D9BEC2A87DBA50724990825C177FF026004BBD6` | R98-2：try/finally 全覆盖 + 故障注入 + email 回退清理 |
| `docs/contracts/auth-gate.md` | `723422CACAD5F5CB9A2904A716A4A4031A3DC5A03700F9804B871ABEBB048AC4` | 全入口双层封禁结论同步 |
| `_experiment/_interop/from-dsh/round-99-handler-probes.mjs` | `6B9BCE5C33FA041CC4FFCD4D032E4FB03939C9924373DAAE38381D2761F6A01D` | R98-1 有效组织矩阵证据（可重放） |

（`auth-runtime-schema.ts`/`organization.py`/`test_auth_integration.py` 哈希未变——时区/helper/迁移已通过项保持。）

## 六、给 Codex 的复核点

1. 重放 round-99-handler-probes.mjs（连续两次）：有效 org/admin/viewer 上 active/disabled 全写入口 403（含 leave/邀请状态流）、零副作用、审计不产生、fixture 归 0；
2. 复核 hook 键名对照安装包实际调用点（beforeUpdateMemberRole/beforeCreateInvitation 等 10 键）+ handler 路由层 17 写端点；
3. 复核 R98-2：try/finally 全覆盖、FIXTURE_EMAIL 预生成定位、故障注入清理断言；
4. 独立执行 119 全量回归 + tsc exit 0 + T5 CLI，确认终态（auth000002、31 app 表 + 7 auth 表、auth.user=0）与回滚复放；
5. 完整终验后裁决 **T7 COMPLETE**，再进入 **T8**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-99-->
