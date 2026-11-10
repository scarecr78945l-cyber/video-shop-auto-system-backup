# Codex：P0-1 T2 枚举迁移复核（round-50）

> 轮次：round-50，归属 Codex（Reviewer）。
> 输入：`from-dsh/round-49-dsh-P0-1-T2枚举迁移.md`、`project/` 实际文件、冻结的 `docs/contracts/enum-registry.yaml`。
> 范围：生成器、migration、catalog 断言与 T2 drill；本轮未修改 `project/`。

---

## 一、结论

| 验收面 | 结果 | 独立证据 |
|---|---|---|
| round-49 文件完整性 | ✅ 通过 | 5 个新增文件字节数及 SHA-256 均与交接声明一致 |
| registry → generator → `_ENUMS` | ✅ 通过 | 三方均为 60 个唯一名称、267 个 labels，名称/值集/原序完全一致 |
| migration upgrade/downgrade | ✅ 通过 | down_revision 正确；upgrade 正序、downgrade `reversed(_ENUMS)`；T2 单步回退实测通过 |
| `assert_enums.py` exact-set | ✅ 通过 | `app` schema enum=60，无缺失/多余，所有 label 顺序一致 |
| `t2_enum_drill.py` 表面执行 | ⚠️ 部分通过 | 脚本输出 `T2 DRILL: PASS`，但回退目标写成 `base`，同时卸载了已通过的 T1 |
| 生成器可复现性 | ❌ 未通过 | 再次执行会按当前分钟新建第二个同 revision 文件，破坏单一 Alembic graph |

**T2 暂缓验收，不进入 T3。当前剩余两个阻断：R50-1 生成器非幂等、R50-2 drill 回退边界错误。**

---

## 二、生成器与 migration 一致性

Codex 使用 PyYAML 独立解析 registry，并用 Python AST 读取 migration 的 `_ENUMS`，未复用项目中的正则解析器。结果：

```text
registry declared count = 60
registry actual entries = 60
unique enum names       = 60
generator parse entries = 60
generator == registry   = true
migration _ENUMS        = 60
migration == registry   = true
enum_error_code present = false
total labels            = 267
down_revision           = 32f34131a28a
```

当前已生成 migration 的内容与冻结 registry 完全一致。

### upgrade/downgrade 静态方向

- upgrade 遍历 `_ENUMS` 原序并执行 `CREATE TYPE`；
- downgrade 遍历 `reversed(_ENUMS)` 并执行 `DROP TYPE`；
- `env.py` 在同一事务中将 `search_path` 设置为 `app, pg_catalog`，故未限定 schema 的类型 DDL 实际落入 `app`；
- migration 不包含 `enum_error_code`。

### T2 单步回退实测

Codex 独立执行：

```text
python -m alembic downgrade 32f34131a28a
```

结果：

```text
revision   = 32f34131a28a
app enum   = 0
btree_gist = present
owner mark = created_by_migration_32f34131a28a
```

随后 `upgrade head` 恢复 `60enum000000 (head)`。说明 T2 migration 自身的正向与逆向实现可执行，并保持 T1 基线。

---

## 三、catalog exact-set 断言——通过

独立运行 `python scripts/assert_enums.py`：

```text
registry entries=60                         PASS
app schema enum 数量=60                    PASS
无缺失 enum                                PASS
无多余 enum                                PASS
每 enum label 顺序与 registry 一致          PASS
ENUM-ASSERT: PASS
```

查询限定 `pg_namespace.nspname='app'` 与 `pg_type.typtype='e'`，并按 `pg_enum.enumsortorder` 比较 label 原序，满足 schema + 类型名 + label 顺序 exact-set。项目断言与独立 PyYAML/AST 复算结论一致。

---

## 四、剩余阻断

### R50-1：生成器再次执行会产生重复 revision 文件

`gen_enum_migration.py` 使用运行时 UTC 分钟生成文件名：

```python
now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
rev = "60enum000000"
fname = f"{now}_{rev}_60_enums.py"
```

仓库中现有文件为：

```text
20260903_1200_60enum000000_60_enums.py
```

复核时按生成器逻辑计算的新输出为：

```text
20260903_1209_60enum000000_60_enums.py
```

两者路径不同但 revision 都是 `60enum000000`。因此 round-49 给出的复现命令 `python scripts/gen_enum_migration.py` 现在会新增第二个同 revision 文件，而不是验证或稳定重建当前产物；Alembic graph 将出现重复 revision。生成内容中的 `Create Date` 也取当前时刻，导致相同输入无法得到相同文件哈希。

**回修验收**：固定单一 canonical 输出路径和稳定内容，或提供无写入的 `--check` 模式；连续执行两次后版本目录仍只有一个 `60enum000000`，文件哈希不变，`alembic heads` 仅返回一个 head。已有产物与 registry 漂移时应稳定失败或受控覆盖，不得静默增加 revision 文件。

### R50-2：T2 drill 使用 `downgrade base`，越过包边界卸载 T1

`t2_enum_drill.py` 当前执行：

```python
alembic("downgrade", "base")
```

这会依次执行：

```text
60enum000000 -> 32f34131a28a   # T2
32f34131a28a -> base           # T1 baseline
```

因此 drill 的“downgrade 后 enum=0”是在 T1 也被卸载后的状态得到。`assert_enums_empty.py` 只检查 enum 数量，没有断言 revision 仍为 `32f34131a28a`、`btree_gist` 仍存在，无法守住 T2 单包回退边界。round-49 将该步骤描述为“T2 逆序回退到 baseline”，与脚本实际命令不一致。

**回修验收**：T2 drill 回退目标改为 `32f34131a28a`（或等价单步回退），并机械断言：

```text
current revision = 32f34131a28a
app enum count   = 0
btree_gist       = present
T1 owner mark    = retained
```

之后 re-upgrade 到 `60enum000000` 并重跑 exact-set。全链 downgrade base 可留给独立的总链回滚测试，不应替代 T2 包级回退。

---

## 五、drill 实际结果与最终状态

独立运行 `python scripts/t2_enum_drill.py` 的现有步骤全部返回成功，末行：

```text
T2 DRILL: PASS
```

该结果确认 60 enum 可创建、全部删除并再次创建，以及重复 `upgrade head` 不新增类型；由于 R50-2，它尚未证明“只回退 T2 且保留 T1”。

测试结束后数据库已恢复：

```text
revision       = 60enum000000 (head)
app enum count = 60
btree_gist     = present
```

建议下一份交接文件：`from-dsh/round-51-dsh-P0-1-T2回修.md`。只处理 R50-1/R50-2；两项清零后再做 T2 聚焦终验并决定是否进入 T3。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-50-->
