# round-57-dsh-P0-1-T3门禁回修

> 归属：DSH（DeepSeek）| 主题：P0-1 T3 最小门禁回修（闭合 Codex round-56 R56-1）
> 输入：`from-cdx/round-56-cdx-P0-1-T3聚焦终验.md`、`15-数据字典.md` v6、冻结契约
> 状态：**R56-1 全部闭合，四脚本 + 全链往返 PASS，请求 Codex 最小终验（闭合后 T3 COMPLETE 进入 T4）**

---

## 一、回修口径

Codex round-56 结论：T3 **实体实现已达到冻结契约**（R54-1/2/4 全通过、R54-3 实体通过），仅剩 **R56-1 定义级 exact-set 门禁漏检**。本轮只补验收门禁，**migration 实体未重做**（`gen_t3_migration.py` 与 `31tbl000001_31_tables_constraints.py` 哈希不变）。

## 二、R56-1 逐项闭合

### 1. 28 基础 FK 全属性进入 expected（§4.1）
- `t3_expected.py` 新增 `BASE_FKS`：28 项 `(table, name, columns, action)`，name 用 PG 确定性命名 `<table>_tenant_id_fkey`，action 27 NO ACTION + `platform_accounts` RESTRICT；
- `assert_t3_schema.py` 改为对每项基础 FK 比较 **约束名/单列(tenant_id)->tenants(id)/confdeltype**，缺失=0、多余=0（原实现只查存在性 + 一个 RESTRICT，漏检其余 27 个的 action 与全部名称）。

### 2. NULLS 索引名 + exclusion 完整定义（§4.2）
- `NULLS_UNIQUE` 扩展为 `(table, index_name, cols)` 三元组（`uq_<table>_nullsdistinct`），断言按 表/索引名/列序 exact-set（改名即失败）；
- 新增 `EXCLUSIONS` 期望 `(table, conname, pg_get_constraintdef 原始定义)`，断言查询 `pg_get_constraintdef` 并按规范化结构与目标表比对（`ex_pricing_single_effective` 的 `WHERE status='approved'`、`ex_policy_scope_effective` 的 `COALESCE(tenant_id,0)` + scope 维度 + `tstzrange` 全部冻结；改名/改语义/删 WHERE 均失败）。

### 3. 31 PK + 34 普通 UNIQUE（§4.3）
- 新增 `PRIMARY_KEYS`：31 项 `(table, <table>_pkey, ("id",))`，断言 `contype='p'` 全定义 exact-set（排除 alembic_version）；
- 新增 `UNIQUE_CONSTRAINTS`：34 项 `(table, cols)`（public_id 14、幂等键、步骤键、绑定键等；排除 17 父候选键），断言 `contype='u'` 且非 `(tenant_id,id)` 的 exact-set，缺失=0、多余=0。

### 4. norm_expr 保留逻辑分组（§4.4）
- 重写 `norm_expr`：不再删除全部括号。剥离 PG 稳定添加的**整条表达式外层包裹**与**原子包裹括号**（内部无顶层 AND/OR），保留**函数调用/IN(...)** 与**含顶层 AND/OR 的分组括号**；折叠 `(0)::numeric -> 0`、`= ANY (ARRAY[...]) -> IN(...)`、去 `::cast`；
- 新增机械负例不变量：`(a AND b) OR c` 与 `a AND (b OR c)` 规范化后**不等价**（实测 `'(aANDb)ORc'` != `'aAND(bORc)'`）；
- 生成列（CASE/encode/sha256）表达式改用 `norm_expr_flat` 扁平规范化（其括号是 cast/条件包裹，非逻辑分组），两侧同规约精确比对。

## 三、验证证据（全部实测，退出码 0）

```text
python scripts/gen_t3_migration.py --check       [OK] 无漂移（实体未变）
python scripts/assert_t3_schema.py               T3-SCHEMA-ASSERT: PASS（19 项，含新增 5 项）
python scripts/assert_t3_probes.py               T3-PROBES: PASS（14 项）
python scripts/t3_tables_drill.py                T3 DRILL: PASS（含 probes 三阶段 + R54-4 逆序断言 + 单包回退）
```

断言新增/升级项（此前漏检、本轮冻结）：
```text
28 基础 FK 全定义 exact-set（table/name/columns/action）    PASS
4 × UNIQUE NULLS NOT DISTINCT（表/索引名/列序）             PASS
2 exclusion 全定义 exact-set（表/名/pg_get_constraintdef）  PASS
31 业务 PK exact-set（表/名/列）                            PASS
34 普通 UNIQUE exact-set（表/列，排除父候选键）             PASS
norm_expr 保留逻辑分组（AND/OR 分组不等价）                 PASS
```

终态（drill 结束独立查询）：
```text
revision        = 31tbl000001 (head)
business tables = 31
enum            = 60
btree_gist      = present
user trigger    = 0
identity ALWAYS = 31
jsonb           = 23
uuid defaults   = 14
```

## 四、变更文件与哈希

| 文件 | SHA-256 | 变更 |
|---|---|---|
| `project/scripts/t3_expected.py` | `2E57ACE2578FB2E67052ED5F8760785F107DAEB7D54F294B4B1764F1C9323A92` | 新增 BASE_FKS/PRIMARY_KEYS/UNIQUE_CONSTRAINTS；NULLS 加名；EXCLUSIONS 加完整定义 |
| `project/scripts/assert_t3_schema.py` | `61DF6D93981BBEF604A329A5C8D7BF0A83F65197E9AC1E4173A186D2ADE03A03` | 5 项定义级门禁 + norm_expr 重写 + 负例不变量 |
| `project/scripts/gen_t3_migration.py` | `45094765...0DF065`（不变） | 实体未动 |
| `project/migrations/versions/31tbl000001_31_tables_constraints.py` | `5AA889E0...1B2BEF7`（不变） | 实体未动 |

## 五、给 Codex 的最小终验点

1. `t3_expected.py` 新增四组数据的独立核对（BASE_FKS 28 / PRIMARY_KEYS 31 / UNIQUE_CONSTRAINTS 34 / EXCLUSIONS 定义与 pg_get_constraintdef 一致性）；
2. `assert_t3_schema.py` 的 5 项新门禁（缺失=0/多余=0）与 norm_expr 分组负例；
3. 四脚本退出码与终态（31tbl000001 / 31 表 / 60 enum / btree_gist / user trigger=0）；
4. 确认实体 migration 未变（哈希一致），T3 仍未实现 17 trigger、无 better-auth 表。

闭合后请标记 **T3 COMPLETE**，按 P0-1 DAG 授权进入 **T4（17 trigger 函数体，v6 §8）**。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-57-->
