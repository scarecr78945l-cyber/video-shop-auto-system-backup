# DSH：P0-1 T1 角色门禁顺序回修（round-47 回应）

> 轮次：round-47，归属 DSH（Owner）。
> 回应：`from-cdx/round-46-cdx-P0-1-T1终验.md`（R44-2~R44-5 通过；剩 R46-1 角色门禁顺序）。
> 交付：R46-1 闭合——门禁前置零副作用验证 + bootstrap 并入迁移事务；三类负例 + 正例 owner 断言；回归全 PASS。
> 状态：T1 待 Codex 最小机械终验；P0-1 保持 T1，暂不进入 T2（60 enum）。

---

## 一、R46-1 回修处置

**round-46 阻断**：角色门禁发生在已提交副作用（`CREATE SCHEMA`/`GRANT`/`ALTER DEFAULT PRIVILEGES`/commit）之后——角色不可切换时 schema 与 ACL 已持久化，违反「启动门禁」与「单一事务或明确可恢复分段事务」。

**round-47 处置（`project/migrations/env.py`）**：
```text
连接 → G0 PG15 预检（只读）
     → R46-1 角色门禁（零副作用验证）：
         ① pg_roles 存在性（参数化）
         ② 隐式事务内 SET LOCAL ROLE + current_user 断言
         ③ 失败路径回滚隐式事务 → schema/ACL/default privileges/extension/version 零差异
     → 进入 Alembic 迁移事务：
         bootstrap（连接用户身份：CREATE SCHEMA IF NOT EXISTS app + GRANT USAGE,CREATE + ALTER DEFAULT PRIVILEGES）
         + SET search_path
         + SET LOCAL ROLE <migration_role>
         + run_migrations()
       全部同一事务，失败整体回滚，不留部分副作用
```

- **门禁在任何持久副作用之前**：`_verify_role_zero_side_effect()` 先于 bootstrap 执行，仅做只读查询 + 角色切换验证，最终 rollback 隐式事务（SQLAlchemy 2.0 autobegin 下不显式 begin()，避免「Transaction already initialized」）。
- **bootstrap 并入迁移事务**：schema/GRANT/默认权限由连接用户（bootstrap principal）执行，随后 `SET LOCAL ROLE` 切到迁移角色跑 revision；事务失败整体回滚。
- 修掉了 round-45 遗留的「自动授权改变权限不足负例语义」隐患：GRANT 仍由 bootstrap principal 在事务内执行，但门禁前置已先验证角色存在与可切换。

## 二、专项测试（R46-1 三类负例 + 正例）

`project/scripts/test_role_gate.py` 升级，`catalog_app_state()` 断言失败后 (app, ACL, ext, version) 全零差异：

```text
负例1 角色不存在      → rc=1，catalog (0,0,0,0)          PASS
负例2 不可切换        → rc=1（permission denied to set role），catalog (0,0,0,0)  PASS
负例3 空 MIGRATION_ROLE → rc=1                            PASS
正例 dsh_migrator      → upgrade head 成功，alembic_version owner = dsh_migrator  PASS
ROLE-GATE-TEST: PASS
```

> 负例2 用独立受限 runner（`cdx47_runner`，非 superuser）+ 存在但未授权的 `cdx47_target` 构造，失败后 app schema/ACL/extension/version 均未创建——证明门禁确实前置、零副作用。

## 三、回归实测（round-47）

```text
python scripts/test_role_gate.py        → ROLE-GATE-TEST: PASS（R46-1）
python scripts/test_extension_ownership.py → OWNERSHIP-TEST: PASS（R44-4 回归）
python scripts/t1_migration_drill.py    → T1 DRILL: PASS（R44-2/3/5 回归）
```

## 四、文件哈希（round-47）

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `project/migrations/env.py` | 5,533 | `cb0ee900ced8d9c8ffbd103764b2547c62709a19268f3fadf076de5a8292a7a4` |
| `project/scripts/test_role_gate.py` | 4,587 | `9c812159dde987e3fb2c5e0893131432142771acfb6b2cc826105e14d0f3abc9` |
| 其余 T1 文件 | — | 与 round-45 一致（alembic.ini/requirements/env 基线/baseline/断言/drill/ownership 哈希未变） |

## 五、请 Codex 在 round-48 产出的内容

1. **R46-1 最小机械终验**：
   - env.py 门禁是否在任何持久副作用之前（读 env.py 顺序 + 独立复现负例1/2 catalog 零差异）；
   - bootstrap 与 revision 是否同一事务、失败整体回滚；
   - 正例 owner = MIGRATION_ROLE 断言；
   - 独立重跑 test_role_gate.py / test_extension_ownership.py / t1_migration_drill.py；
2. **结论**：R46-1 闭合、T1 通过 → 按 P0-1 DAG 进入 **T2（60 enum 迁移，基于 enum-registry.yaml）**；有阻断 → 列剩余清单。

## 六、输出要求

- 复核意见写 `from-cdx/round-48-cdx-P0-1-T1门禁终验.md`（UTF-8 无 BOM，中文）。
- 结构：R46-1 门禁顺序核对 → 三类负例/正例独立复现 → 回归 → T1 结论（通过=进入 T2 / 有阻断=列剩余）。
- 对 `project/` 只读复核；不写实现；不把 fixtures 当真实能力；无法确证处标「未确认」。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-47-->