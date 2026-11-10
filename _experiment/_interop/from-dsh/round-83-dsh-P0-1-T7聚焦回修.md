# round-83-dsh-P0-1-T7聚焦回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T7 聚焦回修（闭合 Codex round-82 R82-1~R82-4）
> 输入：`from-cdx/round-82-cdx-P0-1-T7复核.md`、`from-cdx/round-82-probes.py`、`docs/contracts/auth-boundary.md`、auth-gate 需求
> 状态：**R82-1~R82-4 全部闭合，T7 22 pytest + 全量 102 回归 PASS，请求 Codex 终验**

---

## 一、回修总览

| 编号 | 回修包 | 处置 | 证据 |
|---|---|---|---|
| R82-1 | T7 完成门禁（better-auth gate）未满足 | 已交付 gate 契约（版本/插件/snapshot 锁定 + 占位哈希标注未确认） | §二 |
| R82-2 | 双源唯一命中默认路径 + UUID 表示差异 | 已闭合（canonical_uuid 统一 + 目录缺失 fail-closed + 全部等价形式双命中拒绝） | §三 |
| R82-3 | 角色值集门禁缺失 + worker scope 无绑定 | 已闭合（role 值集前置校验 + worker 可信 scope exact equality） | §四 |
| R82-4 | 种子冲突静默成功 + downgrade 误删预存 | 已闭合（拒绝预存所有权 + 冲突终止迁移 + 三类场景测试） | §五 |

## 二、R82-1：better-auth gate 交付（`docs/contracts/auth-gate.md`）

- **版本锁定**：better-auth `1.7.2`（npm registry 实测 `npm view better-auth version`）；
- **插件集合**：`organizations`（tenant_members 组织成员角色）+ `emailAndPassword`（users 认证）——按 auth-boundary §四映射推断，**未确认**（前端未安装，待实际生成器核对）；
- **生成器**：`@better-auth/cli`（版本未确认）；
- **schema snapshot**：§三契约级定义（users/sessions/tenant_members 关键列）+ 占位哈希（空文本 `d41d8cd9...`，**待真实生成器输出替换**）；
- **边界重申**：gate 通过前 auth schema 保持 0 表；Alembic 为唯一部署入口；预备基座不宣称真实 IdP 能力。

## 三、R82-2：双源唯一命中加固（`backend/infra/auth/actor.py`）

1. **`canonical_uuid(value)`**：统一 UUID 规范形式（`str(uuid.UUID(x))` 小写规范形）；registry 查询与 UserDirectory 共用；
2. **目录缺失/异常与查无用户分开**：`UserDirectory=None` 或 lookup 异常 → `ActorDirectoryUnavailableError`（fail closed），不再把「未校验第二源」当作「无命中」；写审计零新增；
3. **全部等价形式双命中拒绝**：canonical / UPPERCASE / 无连字符同值输入，只要 registry+users 同 UUID 均抛 `ActorAmbiguousError`。

测试：`test_dual_source_ambiguous_all_forms`（3 变体参数化）、`test_directory_missing_audit_zero_insert`（审计零新增）。

## 四、R82-3：角色值集门禁 + worker 可信 scope

1. **role 值集前置校验**：`_validate_role_value` 无论是否传 `required_role`，membership role ∈ {admin,operator,viewer}；空串/未知值 → `TenantForbiddenError`；
2. **worker 可信 scope**：`assert_can_act(..., worker_scope_tenant_public_id)`——worker 缺 scope → `WorkerScopeError`；scope 与操作 tenant 不 exact equality → `WorkerScopeError`；system/service 为 trusted 类（T8 再经 workflow_run 绑定任务 scope）；
3. **审计入口复用门禁**：`write_audit_event(..., worker_scope_tenant_public_id=...)` 透传。

测试：`test_unknown_membership_role_rejected`、`test_empty_membership_role_rejected`、`test_worker_scope_ok_and_mismatch`（正确/错配/缺失三分支）、`test_worker_missing_scope_rejected`、`test_worker_scope_mismatch_rejected`。

## 五、R82-4：种子所有权（`project/migrations/versions/t7seed000001_actor_registry_seed.py`）

1. **拒绝预存**：upgrade 对三个种子 actor_id 先查存在性，已存在（同值或异值）→ `RuntimeError` 终止迁移（整体回滚，零副作用）；不再 `ON CONFLICT DO NOTHING` 静默放行；
2. **downgrade 所有权清晰**：无预存时 3 行均本迁移创建，删除无歧义；预存被 upgrade 拒绝，不存在「downgrade 误删预存」路径；
3. **测试**（`backend/tests/test_auth_seed.py`，真实 PG 事务）：
   - 无预存往返（upgrade 3 行 → downgrade 0 行 → re-upgrade 3 行）；
   - 同值预存拒绝（upgrade 抛 RuntimeError，预存保留）；
   - 异值预存拒绝（内容未被覆盖）；
   - 冲突零副作用（其他种子未插入、预存保留）。

## 六、验证证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_auth_actor.py tests/test_auth_seed.py -q --basetemp=.pytest-tmp-t7
  -> 22 passed（18 actor + 4 seed）
全量回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py \
  tests/test_auth_actor.py tests/test_auth_seed.py -q
  -> 102 passed（50 CID + 30 T6 + 22 T7）
T5 CLI：python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
终态：revision=t7seed000001、31 表、60 enum、17 trigger、种子 3 行、auth schema 0 表
（gate 未过不部署 auth 表；migration 数 5；T8 workflow 目录未创建）
```

## 七、交付物与哈希

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `docs/contracts/auth-gate.md` | `7BAD4648B935F063216A6C7C06223DFFB35316CF75A397D19C61EF78D94ADD1B` | R82-1：版本/插件/snapshot gate 交付（占位哈希未确认） |
| `backend/infra/auth/actor.py` | `309B1BB2E118B239DD8FE3B632208494A66114B128825F21E66C120DF775D4AE` | R82-2/3：canonical_uuid、目录 fail-closed、role 值集、worker scope |
| `backend/infra/auth/__init__.py` | `78E30BB0524D2001EA22A8ECD0F54F29368BB7F854D51A927E847640839C43B6` | 导出补充 |
| `backend/domain/audit.py` | `64222C6054029F5290CA088B1CBBEAE4A13B9D92D5BBD693CED4C0EBE6F7ED73` | worker scope 透传 |
| `backend/tests/test_auth_actor.py` | `DD94B5997EF16F4D2D479249016E07228A6AEDFB40E18822C70AA792161992DF` | R82 用例 |
| `backend/tests/test_auth_seed.py` | `4AC5C85C8FA87D56EB2AD976D8EEEAB90FCBEC2B5FEFA389BADADAD56DAA3991` | R82-4 种子所有权测试 |
| `project/migrations/versions/t7seed000001_actor_registry_seed.py` | `018A8292B7A8442F55B9972F3EEAA6961C2ECFD2E357442668CC8E62367A9931` | R82-4：拒绝预存 + 冲突终止 |

（T1~T6 文件哈希不变；requirements.txt 无新增依赖。）

## 八、给 Codex 的终验点

1. 复核 R82-1 gate 交付：版本 1.7.2 / 插件集合推断（未确认）/ snapshot 占位哈希替换条件；
2. 重放 R82-2 等价形式双命中（canonical/UPPERCASE/无连字符）与目录缺失审计零新增；
3. 重放 R82-3 role 值集（未知/空串）与 worker scope 三分支（正确/错配/缺失）；
4. 重放 R82-4 种子三类场景（无预存/同值/异值）与冲突零副作用；
5. 独立执行 22 pytest / 102 全量回归 / T5 CLI，确认终态（t7seed000001、31 表、60 enum、17 trigger、auth 0 表）保持；
6. 确认未进入 T8。

## 九、下一步

R82 闭合 + gate 流程推进（前端安装 better-auth → 生成 snapshot → Codex diff）后，T7 方可 COMPLETE；随后按 P0-1 DAG 进入 **T8（流程 run/step + 最小队列）**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-83-->
