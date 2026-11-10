# Codex：P0-1 T1 migration 基础设施终验（round-46）

> 轮次：round-46，归属 Codex（Reviewer）。
> 输入：`from-dsh/round-45-dsh-P0-1-T1回修.md`、`project/` 实际文件、round-44 五个阻断。
> 范围：R44-1~R44-5 逐项终验；本轮未修改 `project/`。

---

## 一、结论

| 项目 | 结果 | 独立证据 |
|---|---|---|
| round-45 文件完整性 | ✅ 通过 | 10 个交付文件字节数与 SHA-256 均和 round-45 一致 |
| R44-1 角色语义 | ❌ 未通过 | 角色切换失败前已提交 schema/ACL 变更；不存在角色也未进入显式存在性门禁 |
| R44-2 同源 URL | ✅ 通过 | 两个断言均读取 `DATABASE_URL`；无效端口均 rc=1 |
| R44-3 offline 关闭 | ✅ 通过 | `alembic upgrade head --sql` 稳定 rc=1，无 SQL 生成物 |
| R44-4 扩展所有权 | ✅ 通过 | 预存保留、迁移创建删除两条路径独立通过 |
| R44-5 依赖复现 | ✅ 通过 | 全新临时 venv 按清单安装后 drill PASS |

**T1 仍暂缓验收，当前只剩 1 个聚焦阻断 R46-1。暂不进入 T2。**

---

## 二、R44-1：角色代码存在，但启动门禁顺序仍未闭合

### 2.1 已确认的正向实现

`env.py` 已包含：

- `pg_roles` 参数化存在性查询；
- `_quote_ident()` 后的 `SET LOCAL ROLE`；
- `SELECT current_user` 与期望角色一致性断言；
- 角色切换放在 Alembic migration transaction 内；
- `MIGRATION_ROLE` 空值门禁。

标准测试库中 `alembic_version` 与 `btree_gist` 的 owner 均为 `dsh_migrator`，说明正常路径下 revision 对象确实由该角色创建。

### 2.2 R46-1：门禁发生在已提交副作用之后

实际执行顺序是：

```text
CREATE SCHEMA IF NOT EXISTS app
GRANT USAGE, CREATE ON SCHEMA app TO <role>
ALTER DEFAULT PRIVILEGES ... TO <role>
SET search_path ...
COMMIT
  ↓
进入 Alembic transaction
  ↓
检查 pg_roles / SET LOCAL ROLE / current_user
```

这意味着角色能否切换、当前角色是否正确，并不是数据库变更前的启动门禁。

Codex 在全新临时数据库中独立构造：

- `cdx46_runner`：非 superuser 的数据库 owner；
- `cdx46_target`：真实存在但未授予 runner 的 NOLOGIN 角色；
- 连接用户为 runner，`MIGRATION_ROLE=cdx46_target`。

执行 `python -m alembic current` 后：

```text
rc=1
psycopg2.errors.InsufficientPrivilege:
permission denied to set role "cdx46_target"
```

失败符合“不可切换角色应拒绝”，但失败后的 catalog 状态为：

```text
app|cdx46_runner|cdx46_runner=UC/cdx46_runner,cdx46_target=UC/cdx46_runner
```

即 `app` schema 已持久存在，且不可切换的目标角色已经获得 `USAGE, CREATE` ACL。迁移返回失败，却留下已提交的 schema 和授权副作用。这与“启动门禁”和“单一事务或明确可恢复分段事务”不一致；round-44 §4.2 要求的分段失败恢复也仍未落地。

此外，`test_role_gate.py` 的不存在角色负例实际错误来自：

```text
GRANT ... TO "ROLE_DOES_NOT_EXIST"
psycopg2.errors.UndefinedObject
```

说明 `_apply_role()` 内的显式 `pg_roles` 存在性检查尚未执行，测试只验证了非零退出码，没有验证稳定门禁位置、错误类别及失败后 catalog 零差异。

### 2.3 聚焦回修要求

R46-1 最小闭合条件：

1. 在任何 `CREATE SCHEMA`、`GRANT`、`ALTER DEFAULT PRIVILEGES` 或 commit 之前，完成角色存在性、可切换性与 `current_user` 检查；
2. 角色门禁失败后，schema、ACL、default privileges、extension、version table 均与执行前一致；
3. 不存在、不可切换、权限不足三类负例分别断言稳定错误和 catalog 零差异，而不只检查 `rc != 0`；
4. 正常角色路径仍证明 revision 对象 owner、`current_user` 和 `MIGRATION_ROLE` 一致；
5. bootstrap 与 revision 若继续分段，需给出可执行恢复策略与失败重跑测试；更直接的做法是避免在门禁前 commit。

自动向任意传入角色授予 schema 权限还会改变“权限不足”负例的语义。建议由部署前置步骤配置角色权限，migration 只做验证；若保留自动授权，则必须限定 bootstrap principal、授权集合和事务回滚边界。

---

## 三、R44-2~R44-5 终验

### 3.1 R44-2 同源 `DATABASE_URL`——通过

两个断言脚本均从环境变量读取 URL，不再包含固定的 5432 测试库连接串。独立负例：

```text
DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:1/definitely_wrong
python scripts/assert_upgrade_head.py     -> rc=1, ASSERT: FAIL
python scripts/assert_downgrade_base.py   -> rc=1, EMPTY-ASSERT: FAIL
```

`t1_migration_drill.py` 的 Alembic 子进程与断言子进程继承同一环境，round-44 的跨库假通过路径已闭合。

### 3.2 R44-3 offline 关闭——通过

独立运行：

```text
python -m alembic upgrade head --sql
```

结果 rc=1，并输出稳定门禁文本 `offline 模式已关闭`。`_expect_offline_rejected.py` 及完整 drill 对该行为均验证通过。

### 3.3 R44-4 `btree_gist` 所有权——通过

隔离、串行运行 `python scripts/test_extension_ownership.py`：

```text
B 预存扩展不携带迁移标记                         PASS
B upgrade 未覆盖预存扩展 COMMENT                  PASS
B downgrade 保留预存扩展                         PASS
A migration 创建后携带 revision 所有权标记        PASS
A downgrade 删除 migration 创建的扩展             PASS
OWNERSHIP-TEST: PASS
```

预存扩展的原始 COMMENT `support for indexing common datatypes in GiST` 被保留；标准 head 状态的扩展 owner 为 `dsh_migrator`，COMMENT 为 `created_by_migration_32f34131a28a`。downgrade 未使用 `CASCADE`。

### 3.4 R44-5 干净依赖复现——通过

在全新临时 venv 中仅执行：

```text
python -m pip install -r requirements.txt
```

解析安装版本：

```text
alembic 1.19.1
SQLAlchemy 2.0.52
psycopg2-binary 2.9.12
```

随后使用该 venv 的 Python 运行 `scripts/t1_migration_drill.py`，upgrade/downgrade/re-upgrade、两类 catalog 断言和 offline 拒绝全部通过，末行 `T1 DRILL: PASS`。

---

## 四、数据库最终状态与交接

终验结束后标准测试库已恢复：

```text
revision  = 32f34131a28a (head)
extension = btree_gist
ext owner = dsh_migrator
ext mark  = created_by_migration_32f34131a28a
```

临时角色与临时数据库已删除；`project/` 核心文件未由 Codex 修改。

建议下一份交接文件：`from-dsh/round-47-dsh-P0-1-T1角色门禁顺序回修.md`。只处理 R46-1；清零后再由 Codex 做最小机械终验。T2 的 60 enum revision 继续等待 T1 通过。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-46-->
