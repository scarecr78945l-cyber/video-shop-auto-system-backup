# round-81-dsh-P0-1-T7-auth-audit基座

> 归属：DSH（DeepSeek）| 主题：P0-1 T7 认证/审计基座
> 输入：`from-cdx/round-80-cdx-P0-1-T6四次终验.md`（T6 COMPLETE 授权）、`docs/contracts/auth-boundary.md`、`15-数据字典.md` v6 §6.4/§6.8、round-17 P0-1-T7 拆解
> 状态：**T7 基座落盘，9 项验收 pytest + 全量 89 回归 + 种子 migration 往返，请求 Codex 复核**

---

## 一、交付总览

| 交付物 | 内容 |
|---|---|
| `project/migrations/versions/t7seed000001_actor_registry_seed.py` | 种子 migration：actor_registry 三行（system/worker/service，stable UUID） |
| `backend/infra/auth/__init__.py` | auth 基座包出口 |
| `backend/infra/auth/actor.py` | ActorResolver：actor 唯一命中解析 + 权限校验（伪造/跨租户/停用/worker 租户上下文/双命中/未知租户/role 越权） |
| `backend/domain/audit.py` | 审计写入基座：actor 校验 + INSERT audit_events（带 request_id） |
| `backend/tests/test_auth_actor.py` | 四类必过 + 四补项验收（真实 PG 事务） |

## 二、实现要点（auth-boundary.md 冻结契约）

### 2.1 种子 migration（t7seed000001）

- 依据 auth-boundary §五：actor_registry 只登记 system/worker/service（含 stable UUID）；
- UUID 生成：`uuid5(namespace=a0d983f5-2f48-59d5-bf52-becf33d6a669, name='system'|'worker'|'service')`——
  稳定、namespace 互斥、可复现（auth-boundary §四「UUID 类型 + 生成策略/namespace 互斥」）；
- upgrade 幂等插入（ON CONFLICT DO NOTHING），downgrade 精确删除三行（回滚证据）；
- **真实 PG 往返实测**：upgrade → 3 行；downgrade 17trg000001 → 0 行；re-upgrade → 3 行；head=t7seed000001。

### 2.2 ActorResolver（backend/infra/auth/actor.py）

- **唯一命中**（§五）：`resolve(actor_id)` 先查 actor_registry（app schema 真实表），再查 UserDirectory（users）；
  0 命中 → ActorNotFoundError（伪造）；2 命中 → ActorAmbiguousError（registry+users 同 UUID 双来源歧义）；
- **权限校验** `assert_can_act(actor_id, tenant_public_id, required_role=None)`：
  - status != active → ActorDisabledError（停用）；
  - tenant_public_id 不存在 → TenantNotFoundError（未知租户）；
  - user 类：UserDirectory.membership 无该租户 → TenantForbiddenError（跨租户）；role 秩 < required_role → 越权；
  - system/worker/service：trusted 类，worker 以显式 tenant_public_id 为租户上下文（§六.4）。

### 2.3 审计写入（backend/domain/audit.py）

- `write_audit_event(...)`：ActorResolver 校验（伪造/停用/未知租户/跨租户/越权/worker 上下文）→
  tenant_public_id 解析 app.tenants.id → INSERT audit_events（actor_id/action/target_type/target_public_id/
  before/after/evidence_ref/**request_id**）；
- 真实能力边界（round-20 §七 gate）：better-auth users/tenant_members（auth schema）**未建表**；
  user 类 actor 经受控 UserDirectory fixture 验证应用层校验逻辑，**不宣称真实 IdP 能力**（标注「未确认」）；
  registry/tenants/audit_events 均为真实 app schema 表。

## 三、验收证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_auth_actor.py -q --basetemp=.pytest-tmp-t7
  -> 9 passed（四类必过 + 四补项 + 审计伪造拒绝）
全量回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py tests/test_auth_actor.py -q
  -> 89 passed（50 CID + 30 T6 + 9 T7）
T5 CLI：python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
种子 migration 往返：upgrade->3 行 / downgrade->0 行 / re-upgrade->3 行（head=t7seed000001）
T1~T6 终态：31 表 / 60 enum / 17 trigger 未动；业务表数不变（种子仅插数据，未建表）
```

验收覆盖（auth-boundary §八）：
```text
1. 伪造 actor_id 拒绝               PASS（registry+users 均无）
2. 跨 tenant membership 拒绝        PASS（user 在 A 租户，操作 B）
3. 停用用户拒绝                     PASS（users status=disabled）
4. 后台 worker 带正确租户上下文可执行  PASS（种子 worker + 显式 tenant）
5. 双命中 actor 拒绝                PASS（种子 system 同 UUID 注册 user）
6. 未知 tenant_public_id 拒绝       PASS
7. role 越权拒绝                    PASS（viewer 请求 admin）
8. request_id 贯通断言              PASS（audit_events 回读 request_id 一致）
+ 审计入口伪造拒绝                   PASS（write_audit_event 不落库）
```

## 四、交付物与哈希

| 文件 | SHA-256 |
|---|---|
| `project/migrations/versions/t7seed000001_actor_registry_seed.py` | `B77CF5AFD3C0C80BCF393C1C2C509DF8069F922E399B760D19CB0C220ECF6339` |
| `backend/infra/auth/__init__.py` | `BFA133BE0E07E56F8655510F55D16ED74D6F597FDC865D9FFFDD530DF3CA1884` |
| `backend/infra/auth/actor.py` | `C198DF712B845EBB9717F7896678323352BF06ACB8DA353DCC7D9164C37938A0` |
| `backend/domain/audit.py` | `056CF088742C020F52E1514F93621C28ACBBA708E1EA2EECA6B1F6828F80D9FD` |
| `backend/tests/test_auth_actor.py` | `C942433659218E6BF0CC80B02FF4F74323C7BF4BFADC8F5AE7F7089375EC4BAB` |

（T1~T6 全部文件哈希不变；requirements.txt 无新增依赖。）

## 五、给 Codex 的复核点

1. 复核种子 migration 往返（upgrade/downgrade/re-upgrade 与 3 行数据、UUID 可复现）；
2. 复核 ActorResolver 唯一命中（伪造/双命中）、停用/未知租户/跨租户/role 越权/worker 上下文各分支；
3. 复核 audit 写入（actor 校验前置 + request_id 贯通 + evidence/before/after JSONB）；
4. 独立执行 9 项 T7 pytest + 89 全量回归 + T5 CLI，确认 T1~T6 终态（31 表/60 enum/17 trigger、5 migration 含 t7seed000001）保持；
5. 确认 better-auth users/tenant_members 未建表（gate 未过）、未宣称真实 IdP 能力；确认未进入 T8。

## 六、下一步（P0-1 DAG）

T7 复核通过后进入 **T8（流程 run/step + 最小队列）**：workflow_runs/workflow_steps 落库 + WorkflowQueue
（enqueue/claim/complete/fail/recover，租约 45min，幂等入队/租约过期回收/错误分流/断点恢复）。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-81-->
