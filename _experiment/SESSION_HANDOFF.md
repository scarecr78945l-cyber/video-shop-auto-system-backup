# 会话交接文档：视频号小店全自动系统（P0-1 开发中）

> 用途：本会话上下文已极长，用户决定**换新会话继续**。新会话（DeepSeek Harness）读取本文件即可无缝接续，无需翻阅历史对话。
> 交接时间：2026-09-03（模拟环境日期）
> 交接人：DSH（上一会话）

---

## 一、项目是什么

**视频号微信小店全自动全流程系统**：自动选品 → 自动上架 → 自动小店投放（商品托管）→ 自动素材优化 → 自动收集素材，五条链路全自动闭环。目标 10-100 店、多主体多账号（先 1 主体多店）、内部中台、本地自托管可演进上云、可复制可交接。

**工作区根**：`E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\`

## 二、已完成的里程碑

| 阶段 | 状态 | 说明 |
|---|---|---|
| **立项定稿** | ✅ 完成 | `14-新立项最终方案.md`（15 章）+ `13-立项定稿.md`；决策栈含：主线串行+旁支并行、闸门=自动质量门禁+自动回修+超限人工强审、素材按店绑定、CID 公式等 |
| **数据字典 v6** | ✅ 冻结 | `15-数据字典.md`（31 表、60 enum、17 trigger、CID v6） |
| **P0-0 契约 9 份** | ✅ 全冻结 | `docs/contracts/`：enum-registry.yaml / error-codes.yaml / cid-engine-spec.md / ddl-order.md / index-registry.md / test-strategy.md / external-actions.yaml / idempotency.md / auth-boundary.md |
| **P0-1 T1 migration 基础设施** | ✅ 通过 | `project/` + Alembic；env.py 实现 business_schema=app、search_path、MIGRATION_ROLE 门禁、PG15 预检、offline 关闭；baseline btree_gist（所有权 COMMENT 标记） |
| **P0-1 T2 60 enum** | ✅ 通过 | `60enum000000_60_enums.py`（down_revision=32f34131a28a）；由 `gen_enum_migration.py` 从 enum-registry.yaml 确定性生成；assert_enums.py 按 app schema+label 顺序 exact-set |
| **P0-1 T3 31 表+约束** | ⚠️ **进行中，卡住** | 见第四节 |

## 三、AI 接力机制（与 Codex）

- 工作区文件接力：`_experiment/_interop/`
  - `STATE.md` — 当前轮到谁、规则、历史轮次表
  - `from-dsh/` — DSH（DeepSeek）只写这里
  - `from-cdx/` — Codex 只写这里
- 轮次：已到 round-52（Codex T2 回修终验通过，授权进入 T3）；**round-53 应由 DSH 产出 T3**
- 每轮：DSH 产文件 → 用户把路径给 Codex → Codex 复核产文件 → 用户把路径给 DSH → 循环
- 单向所有权；对 `project/`、`docs/contracts/` 只读复核，DSH 是 Owner
- 红线：mock/fixtures 不算真实能力；无法确证标「未确认」

## 四、P0-1 T3 当前卡点（新会话首要任务）

**目标**：31 业务表 schema + 17 父候选键 + 58 组合 FK + 4 NULLS NOT DISTINCT + 2 exclusion + 15 部分唯一 + 8 普通索引，按 ddl-order.md W0~W8 顺序。

**卡点**：
- `project/migrations/versions/31tbl000001_31_tables_constraints.py`（66KB）**当前损坏**（Python SyntaxError），因上一会话用批量正则改 `sa.Enum` 时误伤跨行内容，**不可逐行修补**。
- 正确修法（已确定方向）：**重写为数据驱动生成器**（仿照 T2 的 `gen_enum_migration.py` 模式）——31 表列定义作为数据，生成器 emit migration，确保确定性、可复核、可 `--check`。
- 关键经验（已踩过）：
  1. `sa.Enum(...)` 在 Alembic `op.create_table` 里会触发 `CREATE TYPE`，而 T2 已创建全部 60 enum → 必须用 **`postgresql.ENUM(..., create_type=False)`**（实测能抑制，`sa.Enum(create_type=False)` 不行）；
  2. FK 约束名 < 64 字符 → 用 `fk_<child>_<parent>`；
  3. NULLS NOT DISTINCT 索引名 < 64 字符 → `uq_<table>_nullsdistinct`；
  4. exclusion 里 `'infinity'` 需 `'infinity'::timestamptz`。

**T3 数据结构（已在损坏文件里，可提取复用）**：WAVES（9 波次）、PARENT_KEYS（17）、COMPOSITE_FKS（58）、NULLS_UNIQUE（4）、PARTIAL_UNIQUE（15）、PLAIN_INDEXES（8）。31 表逐列定义按 `15-数据字典.md` §1~§6 全量手写（上一会话已完整读取并写入过）。

**T3 验收要求**（Codex round-52 明确）：
- 31 表 W0~W8 顺序；三类对象分开 exact-set（31 业务表 / alembic_version 元数据 / better-auth 表）；
- 17 父键、58 组合 FK、4 NULLS、2 exclusion、15 部分唯一、8 普通索引按 G3~G8；
- catalog 按 schema 限定的名称/定义 exact-set，附正反例与 T3 单包 downgrade/re-upgrade（只回退到 `60enum000000`，保留 T1/T2）；
- 不提前实现 T4 的 17 trigger。

## 五、环境与路径速查

| 项 | 值 |
|---|---|
| Python | 3.13.14（`C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe`） |
| 依赖 | alembic 1.19.1 / SQLAlchemy 2.0.52 / psycopg2-binary 2.9.12；`project/requirements.txt` |
| PostgreSQL | Docker `dsh-pg-test`（postgres:16，Up）；`dsh:dsh@127.0.0.1:5432/dsh_test` |
| 迁移角色 | `dsh_migrator`（LOGIN，GRANT CREATE ON DATABASE） |
| 运行 env | `PYTHONUTF8=1`、`MIGRATION_ROLE=dsh_migrator`、`DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test` |
| 项目目录 | `project/`（alembic.ini、migrations/、scripts/） |
| 现有测试脚本 | `scripts/`：t1_migration_drill.py / t2_enum_drill.py / test_role_gate.py / test_extension_ownership.py / assert_*.py |

## 六、T3 之后的路线（P0-1 剩余包）

T3 通过后按 P0-1 DAG 继续：**T4（17 trigger 函数体，v6 §8）→ T5（CID 公式引擎）→ T6（secret_store）→ T7（auth/audit，待 better-auth 硬 gate）→ T8（workflow run/step+最小队列，隐式租约协议）→ T9（全量测试与回滚演练）**。每包 DSH Owner / Codex Reviewer，先验收再下一包。

## 七、给新会话的启动指令

1. 读本文件 → 读 `_experiment/_interop/STATE.md`（确认轮到 DSH，round-53）
2. 处理 T3：按第四节重写生成器 + 重新生成 migration + 跑 upgrade/assert/单包 downgrade/re-upgrade
3. 产出 `_experiment/_interop/from-dsh/round-53-dsh-P0-1-T3表与约束骨架.md`，更新 STATE.md 轮到 Codex
4. 之后每轮遵循第三节接力机制
