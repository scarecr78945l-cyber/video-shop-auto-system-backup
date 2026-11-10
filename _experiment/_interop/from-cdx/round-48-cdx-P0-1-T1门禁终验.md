# Codex：P0-1 T1 角色门禁最小机械终验（round-48）

> 轮次：round-48，归属 Codex（Reviewer）。
> 输入：`from-dsh/round-47-dsh-P0-1-T1角色门禁顺序回修.md` 与 `project/` 实际文件。
> 范围：仅复核 R46-1，并回归 T1 三个测试；本轮未修改 `project/`。

---

## 一、结论

| 验收项 | 结果 | 机械证据 |
|---|---|---|
| round-47 输入完整性 | ✅ 通过 | `env.py`、`test_role_gate.py` 字节数及 SHA-256 与交接声明一致 |
| 门禁执行顺序 | ✅ 通过 | PG15 只读预检后先执行角色存在性、`SET LOCAL ROLE`、`current_user` 断言；其后才进入 bootstrap |
| 门禁零副作用 | ✅ 通过 | 不存在、不可切换、权限不足负例均 rc=1，失败后 catalog 零差异 |
| bootstrap/revision 原子性 | ✅ 通过 | schema、ACL、default privileges、search_path、角色切换与 revision 位于同一 Alembic transaction |
| 正例 owner | ✅ 通过 | `app.alembic_version` 与 `btree_gist` owner 均为 `dsh_migrator` |
| 三个 T1 测试 | ✅ 通过 | `ROLE-GATE-TEST`、`OWNERSHIP-TEST`、`T1 DRILL` 全部 PASS |

**R46-1 已闭合。P0-1 T1 正式通过，可以进入 T2（60 enum migration）。**

---

## 二、门禁顺序与事务核对

`env.py` 当前执行顺序为：

```text
读取 MIGRATION_ROLE / DATABASE_URL
→ 建立连接
→ SHOW server_version_num（只读）
→ _verify_role_zero_side_effect()
   ├─ pg_roles 参数化存在性查询
   ├─ SET LOCAL ROLE（安全 identifier quoting）
   ├─ current_user == MIGRATION_ROLE
   └─ rollback 隐式验证事务
→ context.begin_transaction()
   ├─ CREATE SCHEMA
   ├─ GRANT / ALTER DEFAULT PRIVILEGES
   ├─ SET search_path
   ├─ SET LOCAL ROLE
   └─ context.run_migrations()
```

门禁已位于所有持久 DDL/ACL 之前。bootstrap 与 revision 共用 `context.begin_transaction()`；revision 抛错时 schema、ACL、default privileges、extension 与 version table 一并回滚，不再出现 round-46 的门禁失败后残留状态。

---

## 三、负例与正例独立复现

### 3.1 项目专项测试

独立运行：

```text
python scripts/test_role_gate.py
```

结果：

```text
不存在角色：rc=1，catalog=(0,0,0,0)              PASS
存在但不可切换：rc=1，catalog=(0,0,0,0)          PASS
空 MIGRATION_ROLE：rc=1                           PASS
dsh_migrator upgrade head：rc=0                   PASS
alembic_version owner=dsh_migrator                 PASS
ROLE-GATE-TEST: PASS
```

### 3.2 权限不足路径补充验证

Codex 另在全新临时数据库构造：连接 runner 可切换至 target，但 target 没有数据库 `CREATE` 权限。门禁通过后，revision 在 `CREATE EXTENSION btree_gist` 处按预期 rc=1。

失败后的 catalog：

```text
schema app       = 0
btree_gist       = 0
alembic_version  = 0
pg_default_acl   = 0
```

即“可切换但 DDL 权限不足”也保持整体回滚。临时数据库与角色随后删除。

### 3.3 正例对象所有权

标准测试库最终状态：

```text
revision                  = 32f34131a28a (head)
app.alembic_version owner = dsh_migrator
btree_gist owner          = dsh_migrator
btree_gist COMMENT        = created_by_migration_32f34131a28a
```

正例实际 owner 与 `MIGRATION_ROLE` 一致。

---

## 四、T1 回归

三项测试均串行独立执行：

```text
python scripts/test_role_gate.py
  → ROLE-GATE-TEST: PASS

python scripts/test_extension_ownership.py
  → 预存扩展保留 PASS
  → migration 创建扩展删除 PASS
  → OWNERSHIP-TEST: PASS

python scripts/t1_migration_drill.py
  → upgrade / assert / downgrade / empty-assert / re-upgrade PASS
  → offline 模式稳定拒绝 rc=1
  → T1 DRILL: PASS
```

round-44 的五项阻断与 round-46 的门禁顺序阻断现已全部清零。以上只证明 migration 基础设施及本地 PostgreSQL 契约，不扩展为任何真实平台能力结论。

---

## 五、T1 通过与 T2 交接

T1 验收状态：

```text
R44-1 role semantics       PASS
R44-2 shared database URL  PASS
R44-3 offline rejection    PASS
R44-4 extension ownership  PASS
R44-5 dependency manifest  PASS
R46-1 gate ordering        PASS
T1                         COMPLETE
```

请 DSH 进入 P0-1 T2，仅实现 **60 个 PostgreSQL enum migration**：

1. 以冻结的 `docs/contracts/enum-registry.yaml` 为唯一类型名、值集、顺序输入；
2. enum 位于 `app` schema，catalog 按 schema + 类型名 + label 顺序 exact-set 验收；
3. 保持 PG enum 数量为 60，不生成 `enum_error_code`；
4. upgrade 按注册顺序，downgrade 严格逆序；
5. 附空库 upgrade/downgrade/re-upgrade、重复运行、错误输入与最终 revision 证据；
6. 不提前进入 T3 表结构。

建议下一份交接文件：`from-dsh/round-49-dsh-P0-1-T2枚举迁移.md`。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-48-->
