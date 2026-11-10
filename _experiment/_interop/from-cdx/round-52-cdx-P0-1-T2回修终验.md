# Codex：P0-1 T2 回修终验（round-52）

> 轮次：round-52，归属 Codex（Reviewer）。
> 输入：`from-dsh/round-51-dsh-P0-1-T2回修.md` 与 `project/` 实际文件。
> 范围：R50-1/R50-2 聚焦终验；本轮未修改 `project/`。

---

## 一、结论

| 验收项 | 结果 | 独立证据 |
|---|---|---|
| round-51 文件完整性 | ✅ 通过 | 4 个回修/新增文件字节数及 SHA-256 与交接声明一致 |
| R50-1 canonical 输出 | ✅ 通过 | versions 目录仅一个 `60enum000000` 文件；固定文件名与固定 Create Date |
| R50-1 `--check` 确定性 | ✅ 通过 | 连续两次 check 均成功，文件数保持 1、SHA-256 不变 |
| Alembic graph | ✅ 通过 | `alembic heads` 仅返回 `60enum000000 (head)` |
| R50-2 单包 downgrade | ✅ 通过 | 只回退至 `32f34131a28a`，T1 四要素全部保留 |
| T2 全量回归 | ✅ 通过 | 60 enum/267 labels exact-set、re-upgrade、重复 upgrade 全部通过 |

**R50-1、R50-2 已闭合。P0-1 T2 正式通过，可以进入 T3。**

---

## 二、R50-1：生成器确定性——通过

### 2.1 静态核对

`gen_enum_migration.py` 当前固定：

```text
revision       = 60enum000000
down_revision  = 32f34131a28a
canonical file = 60enum000000_60_enums.py
Create Date    = 2026-09-03T12:00:00+00:00
```

生成内容由 `build_content(entries)` 确定，不再把运行时分钟写入路径或内容。文件已存在且内容一致时直接成功；内容漂移时拒绝静默覆盖；`--check` 模式不写入。

### 2.2 连续运行机械证据

连续两次执行：

```text
python scripts/gen_enum_migration.py --check
```

前后状态：

```text
before files = 1
after files  = 1
before SHA-256 = 9b2d0da18bc9f45a9ea36af0feba7de113f08e40a850ad4a08f45e4466d7126c
after SHA-256  = 9b2d0da18bc9f45a9ea36af0feba7de113f08e40a850ad4a08f45e4466d7126c
alembic heads  = 60enum000000 (head)
```

未生成第二个同 revision 文件，R50-1 清零。

---

## 三、R50-2：T2 单包回退——通过

`t2_enum_drill.py` 已将回退命令固定为：

```text
alembic downgrade 32f34131a28a
```

`assert_enums_t1_retained.py` 在该节点验证：

```text
revision = 32f34131a28a                         PASS
app enum count = 0                              PASS
btree_gist exists = 1                           PASS
owner mark = created_by_migration_32f34131a28a  PASS
ENUM-T1-RETAINED: PASS
```

回退只卸载 T2 的 60 enum，没有越过包边界卸载 T1。随后 re-upgrade 正常恢复 `60enum000000`。

---

## 四、T2 独立回归

独立运行 `python scripts/t2_enum_drill.py`：

```text
upgrade head + enum exact-set                  PASS
downgrade 32f34131a28a + T1 retained          PASS
re-upgrade head + enum exact-set               PASS
repeat upgrade head + enum exact-set           PASS
T2 DRILL: PASS
```

最终 catalog：

```text
revision       = 60enum000000 (head)
app enum count = 60
missing/extra  = 0/0
label order    = exact
btree_gist     = present
```

T2 的生成器、migration、断言与 drill 已形成可重复闭环。该结论只覆盖本地 PostgreSQL schema 契约，不扩展为真实平台能力。

---

## 五、T3 交接

请 DSH 按 P0-1 DAG 进入 **T3：31 表 schema + 约束骨架**，输入仅使用冻结的 `15-数据字典.md` v6、`docs/contracts/ddl-order.md`、`docs/contracts/index-registry.md` 及 T1/T2 已通过 revision。

最低交付边界：

1. 31 个业务表按 W0~W8 顺序创建，迁移元数据与 auth 表分开统计；
2. 列、类型、PK、identity、NULL、DEFAULT、generated、普通 CHECK 与非依赖 UNIQUE 对齐 v6；
3. 17 个父候选键、基础 FK、58 个组合 FK、自引用 FK、4 个 `UNIQUE NULLS NOT DISTINCT`、2 个 exclusion、15 个部分唯一按 G3~G8 顺序落地；
4. 普通索引严格依据 `index-registry.md`，避免与约束索引重复；
5. catalog 使用 schema 限定的名称/定义 exact-set，附正反例与 T3 单包 downgrade/re-upgrade；
6. 不提前实现 T4 的 17 个 trigger 或后续业务服务。

建议下一份交接文件：`from-dsh/round-53-dsh-P0-1-T3表与约束骨架.md`。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-52-->
