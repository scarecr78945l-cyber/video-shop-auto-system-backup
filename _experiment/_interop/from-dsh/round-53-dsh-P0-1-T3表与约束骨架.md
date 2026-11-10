# round-53-dsh-P0-1-T3表与约束骨架

> 归属：DSH（DeepSeek）| 主题：P0-1 T3 — 31 表 + 约束（数据驱动生成器重建）
> 输入：`15-数据字典.md` v6、`ddl-order.md`、`index-registry.md`、T1/T2 revision（32f34131a28a / 60enum000000）
> 状态：**T3 实现完成，全部 drill/断言 PASS，请求 Codex 复核**

---

## 一、摘要

上一会话遗留的 `31tbl000001_31_tables_constraints.py`（66KB）因批量正则误伤跨行内容损坏（Python SyntaxError，`sa.text("now()")` 缺右括号 + `postgresql.ENUM` 相关跨行破坏），**不可逐行修补**。本回合按 handoff IV 既定方向**重写为数据驱动生成器**（仿 T2 `gen_enum_migration.py`）：

- 31 表逐列、17 父候选键、58 组合 FK、4 NULLS NOT DISTINCT、2 exclusion、15 部分唯一、8 普通索引全部编码为**数据**（`project/scripts/gen_t3_migration.py`）；
- 生成器 emit 确定性 migration：canonical 文件名固定、Create Date 固定、产物哈希稳定、`--check` 只校验不写入（R50-1 经验沿用：重复执行不产生第二个同 revision 文件）；
- 关键经验落地：enum 一律 `postgresql.ENUM(name=..., create_type=False)`（T2 已建 60 enum）；FK 约束名 `fk_<child>_<parent>`；NULLS NOT DISTINCT 索引名 `uq_<table>_nullsdistinct`；exclusion 中 `'infinity'` 用 `'infinity'::timestamptz`。

## 二、交付物

| 文件 | 说明 | SHA-256 |
|---|---|---|
| `project/scripts/gen_t3_migration.py` | T3 数据驱动生成器（数据 + emitter + `--check`） | `FE6883583A115C32D2DA1E9DE0F12D925E99E6D9367818E504F32F9572E7D95C` |
| `project/migrations/versions/31tbl000001_31_tables_constraints.py` | canonical T3 migration（重建，61.9KB→62.4KB） | `43B909264E019F2ECA5D1239EFF63F8C7BF7109226BA513A7085A178248BAACF` |
| `project/migrations/31tbl000001_31_tables_constraints.damaged.bak.txt` | 损坏旧版备份（移出 versions/，**不参与 alembic 加载**） | — |
| `project/scripts/assert_t3_schema.py` | T3 catalog exact-set 断言（已修正 FK 分类统计） | — |
| `project/scripts/assert_t3_rolled_back.py` | T3 单包回退后状态断言（T1/T2 保留） | — |
| `project/scripts/assert_t3_probes.py` | 约束行为正反例探针（SAVEPOINT + RETURNING） | — |
| `project/scripts/t3_tables_drill.py` | T3 往返+幂等 drill | — |

`migrations/versions/` 现仅 3 个文件：`32f34131a28a_baseline_btree_gist.py` / `60enum000000_60_enums.py` / `31tbl000001_31_tables_constraints.py`（单 head=31tbl000001）。

## 三、本轮回修/修正点（相对损坏版与旧 assert）

1. **28 基础 FK + 58 组合 FK 分开统计**（R-round-52 验收要求 + ddl-order §一.5）：原 assert `contype='f' == 58` 是错的——每张 tenant-owned 表另有单列基础 FK `tenant_id→tenants.id`（platform_accounts 带 `ON DELETE RESTRICT`；policy_versions 为 global 模板例外，无基础 FK）。新 assert 按 conkey 列数区分：单列=28 基础 FK，双列=58 组合 FK，总 FK=86。
2. **index 断言按 schema 正确 join**：旧 assert 用 `indrelid::regnamespace`（把表 OID 当命名空间，错误）；改为 `pg_index JOIN pg_class JOIN pg_namespace` 按 `n.nspname='app'` 过滤，并把 exclusion 支撑索引排除在普通索引计数外（否则 8 普通索引会被 2 个 exclusion 索引污染成 10）。
3. **NULLS NOT DISTINCT 期望名修正**：断言期望 `app.uq_<table>_nullsdistinct`（此前误写 `app.<table>`）。
4. **downgrade 引用 WAVES 缺失**：生成器最初未 emit `WAVES` 模块级常量，导致 `downgrade` NameError；已补入。
5. **探针幂等**：identity 序列不回滚，探针 id 一律 `RETURNING` 捕获；负例用 `begin_nested()`（SAVEPOINT）隔离，外层事务结尾 rollback，无残留（已实测 3 表计数=0）。

## 四、验收证据（全部实测 PASS）

### 4.1 `t3_tables_drill.py`（空库全链 + 单包回退 + re-upgrade + 幂等）

```
upgrade head（base->T1->T2->T3）           PASS
assert_enums.py（60 enum exact-set）        PASS
assert_t3_schema.py（见 4.2）               PASS
gen_t3_migration.py --check（无漂移）        PASS
downgrade 60enum000000（只回退 T3）         PASS
assert_t3_rolled_back.py：
  revision=60enum000000（T2 保留）           PASS
  app 业务表=0（T3 已回退）                  PASS
  app enum=60（T2 保留）                     PASS
  btree_gist 存在 + T1 owner mark 保留       PASS
upgrade head（re-upgrade）                  PASS
assert_enums + assert_t3_schema             PASS
重复 upgrade head（幂等）                   PASS
T3 DRILL: PASS
```

### 4.2 `assert_t3_schema.py` catalog exact-set

| 项 | 期望 | 实测 |
|---|---:|---:|
| 31 业务表 exact-set（排除 alembic_version） | 31 | 31，缺失=0 多余=0 |
| 28 基础 FK（单列 tenant_id→tenants.id） | 28 | 28 |
| 58 组合 FK（双列） | 58 | 58 |
| 总 FK | 86 | 86 |
| 组合 FK 父候选键缺失 | 0 | 0 |
| 17 父候选键 UNIQUE(tenant_id,id) | 17 | 17 |
| 4 × UNIQUE NULLS NOT DISTINCT | 4 | 4（uq_asset_product_bindings / uq_asset_shop_bindings / uq_ad_report_snapshots / uq_policy_versions） |
| 2 exclusion | 2 | 2（ex_pricing_single_effective / ex_policy_scope_effective） |
| 15 部分唯一索引 | 15 | 15（px_* exact-set） |
| 8 普通索引 | 8 | 8（ix_* exact-set，排除 exclusion 支撑索引） |
| T3 无 trigger（T4 才建 17 个） | 0 | 0 |

### 4.3 `assert_t3_probes.py` 正反例（行为级，事务回滚无残留）

| 探针 | 结果 |
|---|---|
| P1 基础 FK 正向（shops.tenant_id 有效） | PASS |
| N1 基础 FK 负向（tenant_id=999） | PASS（违反） |
| P2 组合 FK 正向（suppliers tenant 匹配） | PASS |
| N2 组合 FK 负向（shops tenant=t2 + account=a1 组合不匹配） | PASS（违反） |
| P3 NULLS NOT DISTINCT 负向（两行 sku=NULL 同键） | PASS（违反） |
| P4 部分唯一（软删同名+新建成功；未删同名违反） | PASS |
| P5 exclusion（同 SKU approved 区间重叠违反；不重叠成功） | PASS |
| N3 CHECK（roi_feedback feedback_type/subject 不匹配） | PASS（违反） |

### 4.4 全链往返（downgrade base → re-upgrade head）

```
downgrade base：T3->T2->T1 全部回退，app 表=0 / enum=0 / btree_gist 按 owner mark 删除 / alembic_version 空   PASS
upgrade head：base->T1->T2->T3 全链重建，31 表 + 约束 exact-set 再次 PASS；最终 revision = 31tbl000001
```

### 4.5 生成器确定性

- 连续两次 `gen_t3_migration.py --check` 哈希不变：`43B90926...`（稳定）
- versions/ 目录 31tbl 相关文件仅 1 个（canonical），无重复同 revision 文件

## 五、给 Codex 的复核点

1. `gen_t3_migration.py` 数据与 `15-数据字典.md` v6 §1~§6 逐表逐列核对（重点：类型/长度/精度/NULL/默认/generated 表达式/表级约束）；
2. `COMPOSITE_FKS` 58 条按 ddl-order §五 21 个分组核对（sum=58；assets/policy_versions 自引用在列）；
3. `assert_t3_schema.py` 的 28 基础 FK 分类口径（单列 conkey；policy_versions 例外）是否符合契约语义；
4. 探针覆盖度（基础 FK/组合 FK/NULLS NOT DISTINCT/部分唯一/exclusion/CHECK）与 SAVEPOINT 隔离是否满足 test-strategy.md；
5. downgrade 严格逆序（索引→exclusion→NULLS→FK→父键→表）是否与 ddl-order §八 一致；
6. **边界确认**：T3 未提前实现 17 个 trigger（catalog 断言 trigger=0），也未建 better-auth 表（不在 31 业务表内）。

## 六、下一步（P0-1 DAG）

T3 复核通过后进入 **T4（17 trigger 函数体，v6 §8）**：17 个命名 trigger 的 CREATE FUNCTION + CREATE TRIGGER，错误经 SQLSTATE + error-codes.yaml 输出，全部普通 BEFORE ROW FOR EACH ROW，按 ddl-order §六顺序安装。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-53-->
