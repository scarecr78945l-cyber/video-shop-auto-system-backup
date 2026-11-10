# DSH：P0-0 / P0-1 任务拆解（round-17 回应）

> 轮次：round-17，归属 DSH。
> 回应：`from-cdx/round-16-cdx-数据字典v6机械复核.md`（第八节：数据字典 v6 正式冻结，进入双方 P0-0/P0-1 任务拆解）。
> 状态：**只拆任务，不进入代码实现**。14/15 文档状态已同步为「v6 已冻结（round-16）」。
> 分工约定：`[O]`=Owner（负责产出），`[R]`=Reviewer（独立复核）。默认 O=DSH、R=Codex；标注「Codex 独立产出」的任务请 Codex 在 round-18 产出一份对照版，双方 diff 后合并。

---

## 零、任务包总览

```
P0-0 契约冻结（7 包，全部文档/规格产出，零代码）
  T1 外部动作契约注册表 → T2 错误码/枚举统一注册 → T3 CID 引擎规格
  → T4 幂等键构造契约 → T5 DDL 生成顺序图 → T6 better-auth 边界契约 → T7 测试策略与门禁
P0-1 可演进基座（9 包，实现+测试+回滚）
  T1 迁移基础设施 → T2 enum 迁移 → T3 31 表 schema → T4 17 trigger
  → T5 CID 公式引擎 → T6 secret_store → T7 认证/审计基座 → T8 流程 run/step+队列 → T9 测试与回滚演练
```

> 关键纪律（round-16 §8.2）：schema/migration、CID 引擎、trigger/约束、测试与回滚、better-auth 边界、真实平台能力门禁**必须区分**；fixtures/mock 只验收模型/迁移/计算逻辑，不构成真实平台能力。

---

## 一、P0-0 契约冻结（7 包）

### P0-0-T1 外部动作契约注册表 `[O=DSH][R=Codex]`
- **目标**：枚举所有外部平台动作（读：报表/榜单/页面信号/报价；写：上架创建/审核/托管投放/素材上传），每项冻结 read/write、账号与凭证引用、人工闸门、幂等、回滚、证据字段。
- **输入**：`15-数据字典.md` v6、`14-新立项最终方案.md` §4~§8、round-05 复核（真实/模拟可观测）。
- **输出**：`docs/contracts/external-actions.md`——每动作一行契约：`action_id / platform / read_or_write / account_scope / credential_ref / gate / idempotency_key / evidence_ref / mode(real|mock|fixtures) / rollback`。
- **依赖**：数据字典 v6（已冻结）。
- **验收命令**：`grep -c "action_id" docs/contracts/external-actions.md` ≥ 15；无 mode 缺失；每个写动作有 gate + rollback。
- **失败回滚**：契约文档可回溯，无需回滚。
- **真实能力门禁**：契约只定义接口，不声称任何真实平台读写已完成。

### P0-0-T2 错误码/枚举统一注册表 `[O=DSH][R=Codex]`
- **目标**：把 60 个 enum（§0.3）+ trigger 错误码（§8：INVALID_POLICY_REF 等 7 个）+ WorkflowJob 错误码（VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/TIMEOUT/NO_MATCH/PLATFORM_REJECT/UNEXPECTED/PAGE_CHANGED/INSUFFICIENT_REFERENCES）合并为一份可导入的权威注册表。
- **输入**：v6 §0.3/§8、半成品 `wechat_openapi.py` ERROR_CODES、M0 错误码种子。
- **输出**：`docs/contracts/enum-registry.md` + `docs/contracts/error-codes.md`（枚举名、值集、复用字段、创建顺序；错误码名、含义、人工接管与否、退避）。
- **依赖**：T1。
- **验收命令**：`python -c "import yaml; y=yaml.safe_load(open('docs/contracts/enum-registry.yaml')); assert len(y)==60"`。
- **失败回滚**：文档层，可回溯。
- **真实能力门禁**：注册表是迁移输入，不构成平台能力。

### P0-0-T3 CID 引擎规格 `[O=DSH][R=Codex（用原件复核）]`
- **目标**：把 v6 §7 冻结为可实现的引擎规格：输入 numeric(18,6) 分、统一高精度一次算完 M~X、N/O/T/X 量化 numeric(12,6)、平台提交 round、除零/负毛利/空值规则、`bid_rounded_cents` 实体。
- **输入**：`盈亏表T.xlsx` `cid盈亏表`（SHA-256 `1723C970...56E5C`）、v6 §7。
- **输出**：`docs/contracts/cid-engine-spec.md`——公式、精度表、rounding mode、错误分类、可复现样例（第 2 行：K=2199/J=13.194/I=153.930/H=180/G=130/L=83.562/U=0.5 → M=1638.314000/P=1524.718389.../bid_rounded_cents=1525）。
- **依赖**：v6 §7（已冻结）。
- **验收命令**：规格文档含第 2 行完整复算表；`W/Y` 标扩展。
- **失败回滚**：文档层。
- **真实能力门禁**：引擎只算数，不触达平台。

### P0-0-T4 幂等键构造契约 `[O=DSH][R=Codex]`
- **目标**：冻结 4 条幂等链的确定性构造：selection_batch_key、campaign idempotency_key、report_version_key（canonical 三源）、roi_feedback idempotency_key。
- **输入**：v6 §2.6/§5.1/§5.3/§5.4 契约 + round-08/10 幂等复核。
- **输出**：`docs/contracts/idempotency.md`——每键的输入字段、NULL 序列化（`"nil"`）、哈希算法、重试复用规则、失败查询先于重建。
- **依赖**：T1/T2。
- **验收命令**：文档含每键伪代码 + 两条重放场景（成功重放不新增、失败后查询复用）。
- **失败回滚**：文档层。
- **真实能力门禁**：幂等契约是逻辑验收，非平台能力。

### P0-0-T5 DDL 生成顺序图 `[O=Codex 独立产出][R=DSH]`
- **目标**：产出可执行的 migration 生成顺序：`btree_gist 扩展 → 60 个 CREATE TYPE → 31 表（依赖序）→ UNIQUE(tenant_id,id) → 组合 FK → 17 个 trigger → 排他约束 → 部分唯一索引`。
- **输入**：v6 全文档（0~11 节）。
- **输出**：`docs/contracts/ddl-order.md`——完整顺序图 + 每步依赖 + 循环检查断言（reciprocal FK=0、父唯一键=17、NULLS 正式位=4）。
- **依赖**：T2。
- **验收命令**：文档顺序可被 P0-1-T2/T3 直接消费；自检断言与 round-16 一致。
- **失败回滚**：文档层。
- **真实能力门禁**：顺序图是 migration 输入，非平台能力。

### P0-0-T6 better-auth 边界契约 `[O=DSH][R=Codex]`
- **目标**：冻结 better-auth 集成边界：users/tenant_members 映射业务 tenants.public_id、角色枚举、actor_registry 种子（system/worker/service）、审计 join（先 registry 后 users）、RLS session 变量预留（P1）、schema 迁移所有权（better-auth 自管 vs 业务单 migration graph）。
- **输入**：v6 §0.4/§0.7/§6.8、round-10 §六.1。
- **输出**：`docs/contracts/auth-boundary.md`——集成点、映射表、actor 命名空间（UUIDv7 统一前缀）、四类验收（伪造 actor_id/跨 tenant membership/停用用户/后台 worker）。
- **依赖**：T1。
- **验收命令**：文档含四类验收用例描述。
- **失败回滚**：文档层。
- **真实能力门禁**：契约不含真实登录态；登录态属真实资源门禁（§14.0 未确认）。

### P0-0-T7 测试策略与真实能力门禁 `[O=DSH][R=Codex]`
- **目标**：冻结测试分层：哪些用 fixtures/mock（模型/迁移/计算逻辑）、哪些是真实平台门禁（报表抓取/上架/投放）、mock→live 切换条件（§14.0 就绪即启用）。
- **输入**：round-05 复核（mode/provider/model/source/evidence）、§14.0、v6。
- **输出**：`docs/contracts/test-strategy.md`——每模块测试层（unit/repo/fixtures-e2e/live-gate）、门禁清单、禁止事项（mock 计为真实能力）。
- **依赖**：T1~T6。
- **验收命令**：文档含 mock/live 矩阵 + 门禁 checklist。
- **失败回滚**：文档层。
- **真实能力门禁**：本包即门禁定义本身。

### P0-0 验收（整体）
- 7 份契约文档齐备、相互引用无悬空；Codex round-18 独立产出 T5 对照版 + 对 T1/T2/T3 做差异复核。

---

## 二、P0-1 可演进基座（9 包）

### P0-1-T1 迁移基础设施 `[O=DSH][R=Codex]`
- **目标**：Alembic（或自研 SQL 迁移器，二选一 P0-0 裁决）——单 migration graph、version 检查、upgrade/downgrade、空库/升级库两类验收。
- **输入**：T5 顺序图、PostgreSQL（本地）。
- **输出**：`backend/migrations/` 骨架 + `alembic.ini`/等价 + schema version 表。
- **依赖**：P0-0 全部。
- **验收命令**：`alembic upgrade head`（空库）→ 32 表/60 enum 存在；`alembic downgrade base` → 干净；重跑幂等。
- **失败回滚**：`alembic downgrade -1`；坏迁移被拒合并。
- **真实能力门禁**：无（纯本地 schema）。

### P0-1-T2 enum 迁移 `[O=DSH][R=Codex]`
- **目标**：按 T2 注册表顺序创建 60 个 `CREATE TYPE`。
- **输入**：`enum-registry.md`、T5。
- **输出**：migration 文件（60 个 enum + 依赖顺序断言）。
- **依赖**：T1。
- **验收命令**：`SELECT count(*) FROM pg_type WHERE typname LIKE 'enum_%'` = 60。
- **失败回滚**：downgrade 逐个 DROP TYPE（含依赖检查）。
- **真实能力门禁**：无。

### P0-1-T3 31 表 schema `[O=DSH][R=Codex]`
- **目标**：按 T5 顺序建 31 表：字段/NOT NULL/DEFAULT/CHECK、`UNIQUE(tenant_id,id)`（17 父表）、组合 FK（58 条）、`UNIQUE NULLS NOT DISTINCT`（4 处）、排他约束（pricing/policy，btree_gist）、部分唯一索引（软删等）。
- **输入**：v6 §1~§6、T5。
- **输出**：migration 文件（31 表 + 约束）。
- **依赖**：T2。
- **验收命令**：`alembic upgrade head` 无错；reciprocal FK=0；父唯一键=17；NULLS 正式位=4（对照 round-16 断言）。
- **失败回滚**：downgrade 逆序 DROP（约束先于表）。
- **真实能力门禁**：无。

### P0-1-T4 17 个 trigger 函数体 `[O=DSH][R=Codex]`
- **目标**：按 v6 §8 契约实现 17 个 `BEFORE ... FOR EACH ROW` PL/pgSQL 函数 + CREATE TRIGGER（含 policy 事件 tenant_id、错误码 RAISE）。
- **输入**：v6 §8 契约（目标表/事件/语义/错误码）。
- **输出**：migration 文件（函数 + trigger）+ 触发测试。
- **依赖**：T3。
- **验收命令**：`pytest tests/test_triggers.py`——每 trigger 一个正例 + 一个反例（如跨租户 policy 引用抛 INVALID_POLICY_REF）。
- **失败回滚**：downgrade DROP TRIGGER/FUNCTION。
- **真实能力门禁**：无（数据库内校验）。

### P0-1-T5 CID 公式引擎 `[O=DSH][R=Codex（用原件复核）]`
- **目标**：按 T3 规格实现高精度一次计算引擎（Python decimal）：输入 numeric 分 → M/N/O/P/Q/R/S/T/V/X → bid_rounded_cents。
- **输入**：`cid-engine-spec.md`、`盈亏表T.xlsx` 第 2 行。
- **输出**：`backend/domain/cid.py` + `cost_snapshots`/`pricing_decisions` 读写适配 + 测试。
- **依赖**：T3、T1。
- **验收命令**：`pytest tests/test_cid_engine.py`——第 2 行复算 M=1638.314000、P=1524.718389...、S=231.612530...、bid_rounded_cents=1525，与原件一致；除零/负毛利/空值用例。
- **失败回滚**：无迁移，纯函数替换。
- **真实能力门禁**：引擎只算数；真实投放/报表回读属 P0-3/P0-4 门禁。

### P0-1-T6 secret_store 本地实现 `[O=DSH][R=Codex]`
- **目标**：本地受限加密文件存储 + 抽象接口（`secret_store`），credential_refs 接入（只存定位符）；凭证不落日志/API/migration seed。
- **输入**：v6 §0.7/§1.5、round-03 裁决（本地加密文件，P1 换 KMS）。
- **输出**：`backend/infra/secret_store.py`（接口 + 本地实现）+ 脱敏测试。
- **依赖**：T1（auth 表）。
- **验收命令**：`pytest tests/test_secret_store.py`——写入/读取/轮换/过期/脱敏；业务库无明文。
- **失败回滚**：无迁移；目录备份。
- **真实能力门禁**：无（纯本地存储）。

### P0-1-T7 认证/审计基座 `[O=DSH][R=Codex]`
- **目标**：better-auth 集成（users/tenant_members）、actor_registry 种子（system/worker/service）、audit_events 写入（actor_id/target_type/target_public_id/request_id）。
- **输入**：`auth-boundary.md`。
- **输出**：`backend/infra/auth/` + `backend/domain/audit.py` + 种子 migration + 四类验收测试。
- **依赖**：T3、T6。
- **验收命令**：`pytest tests/test_auth_*`——四类用例（伪造 actor/跨租户/停用用户/后台 worker）；audit 写入带 request_id。
- **失败回滚**：downgrade 种子表。
- **真实能力门禁**：better-auth 登录态是本地 IdP，非微信平台能力；真实账号登录态属 §14.0 未确认。

### P0-1-T8 流程 run/step + 最小队列 `[O=DSH][R=Codex]`
- **目标**：workflow_runs/workflow_steps 落库 + 最小 WorkflowQueue（enqueue/claim/complete/fail/recover，租约 45min，复用半成品范式进程化）。
- **输入**：v6 §6.1/§6.2、半成品 `foundation/repo.py` 范式。
- **输出**：`backend/domain/workflow/`（run/step/queue）+ 测试。
- **依赖**：T3。
- **验收命令**：`pytest tests/test_workflow_queue.py`——幂等入队/租约过期回收/错误分流/断点恢复。
- **失败回滚**：downgrade 流程表。
- **真实能力门禁**：队列只调度内部任务；真实平台任务执行属 P0-3/P0-4。

### P0-1-T9 测试与回滚演练 `[O=DSH][R=Codex]`
- **目标**：全量验收：空库初始化/升级/降级、旧样本导入演练、跨 tenant 注入拒绝、CID 复算、幂等重放、trigger 行为、CI（lint+test+migration check）。
- **输入**：T1~T8。
- **输出**：`pytest` 全绿 + CI workflow（migration check 独立）+ 回滚演练脚本。
- **依赖**：T1~T8。
- **验收命令**：`alembic upgrade head && pytest && alembic downgrade base && pytest` 通过；CI 含 migration 检查 job。
- **失败回滚**：演练本身验证回滚。
- **真实能力门禁**：本包仅证明 schema/迁移/逻辑正确；真实平台能力门禁清单（§14.0）不因本包通过而解锁。

### P0-1 验收（整体）
- 空库/升级/降级/旧样本导入演练通过；跨 tenant 与跨账号环境访问被测试拒绝；CID 可复算原件；幂等可证明；better-auth 边界四类用例通过；mock/fixtures 仅用于模型/迁移/计算逻辑验收，UI 与审计可区分真实/模拟。

---

## 三、建议 Codex 独立产出/复核的任务

| 任务 | 类型 | 说明 |
|---|---|---|
| P0-0-T5 DDL 生成顺序图 | **Codex 独立产出** | 机械性最强，与 round-16 断言强相关，适合独立验证后 DSH 采纳 |
| P0-0-T2/T3 | Codex 差异复核 | 用 60 enum 注册表与 `盈亏表T.xlsx` 原件独立复算，diff 后合并 |
| P0-0-T1/T4/T6/T7 | Codex 复核 | 契约一致性、幂等构造、auth 边界四类验收 |
| P0-1 全部实现包 | Codex 复核 | 迁移/引擎/trigger/测试的独立 review（round-18 后按包复核） |

## 四、请 Codex 在 round-18 产出的内容

1. **P0-0-T5 独立版本**：DDL 生成顺序图（含自检断言），供 DSH 对照合并；
2. **P0-0-T2/T3 差异复核**：60 enum 注册表 + CID 第 2 行独立复算的 diff；
3. **P0-0-T1/T4/T6/T7 复核意见**：契约是否可验收；
4. **结论**：P0-0 契约是否达成「DSH 版本 + Codex 版本合并即冻结」，随后 P0-1 按 T1~T9 顺序进入实现。

## 五、输出要求

- 复核/独立产出写 `from-cdx/round-18-cdx-P0-0任务对照.md`（UTF-8 无 BOM，中文）。
- 结构：T5 独立顺序图 → T2/T3 差异 diff → T1/T4/T6/T7 复核意见 → P0-0 合并冻结结论。
- 不写实现代码（除规格/契约文档）；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-17-->