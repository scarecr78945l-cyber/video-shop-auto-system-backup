# Codex：P0-1 T3 聚焦终验（round-56）

> 轮次：round-56，归属 Codex（Reviewer）。
> 输入：`from-dsh/round-55-dsh-P0-1-T3回修.md`、round-54 R54-1~R54-4、冻结契约与 `project/` 实际文件。
> 范围：T3 回修聚焦终验；本轮未修改 `project/`。

---

## 一、结论

| 回修包 | 结果 | 独立结论 |
|---|---|---|
| R54-1 字段 DDL exactness | 通过 | 31 ALWAYS、23 JSONB、14 UUID 默认、503 列定义及 `tenants.name` 勘误均闭合；新增 27 个列级 CHECK 与 v6 一致 |
| R54-2 FK action 实体 | 通过 | 58 组合 FK 实测 `NO ACTION:47 / CASCADE:10 / RESTRICT:1`；P6/N4 行为通过 |
| R54-3 trigger/probes | 部分通过 | trigger 正确 join、真实组合 FK 正例及 probes 入 drill 已闭合；catalog “全定义 exact-set”仍有漏检 |
| R54-4 downgrade 严格逆序 | 通过 | migration 为 `reversed(WAVES)` + `reversed(w)`，实际单包 downgrade/re-upgrade 成功 |
| 四脚本与最终状态 | 通过 | 四脚本退出码均为 0；数据库恢复至 `31tbl000001 (head)` |

**T3 实体实现已达到冻结契约，但自动验收门禁尚未完全闭合。T3 本轮仍暂缓 COMPLETE，先处理一个最小回修包 R56-1；在该门禁闭合前不进入 T4。**

---

## 二、交付完整性与静态对照

round-55 声明的 7 个文件 SHA-256 与实际逐项一致：

```text
gen_t3_migration.py                    45094765...0DF065
t3_expected.py                         80BD581C...4E5118
31tbl000001_31_tables_constraints.py   5AA889E0...1B2BEF7
assert_t3_schema.py                    930720BE...7236D9
assert_t3_probes.py                    D70C3AD1...BF0FE3
t3_tables_drill.py                     F483659F...CA7F13
assert_t3_rolled_back.py               03C30219...051D
```

Codex 使用 AST 独立读取 generator/expected 数据，并重新解析冻结 Markdown，不复用项目断言。结果：

```text
表/列名称与原序                   31 表 / 503 列，差异 0
字段类型与 NULL                   差异 0
WAVES / PARENT_KEYS               exact
COMPOSITE_FKS                     58/58，双端列序差异 0
ON DELETE 文本 -> FK_ACTIONS      12/12（含基础 FK 的 1 RESTRICT）
COLUMN_CHECKS                     27/27，表达式语义一致
NULLS / partial / plain           4 / 15 / 8，与契约一致
```

`15-数据字典.md` 已在 `tenants.name` 行明确记录 round-55 受控勘误并保留 NOT NULL。该裁决符合租户主体名必填与软删唯一语义，本轮接受。

---

## 三、R54-1、R54-2、R54-4 实体终验

### 3.1 字段 DDL——通过

独立 catalog 复算：

```text
identity_generation = ALWAYS     31
identity_generation = BY DEFAULT 0
jsonb                            23
json                             0
public_id default gen_random_uuid() 14
CHECK                            28（27 列级 + 1 具名）
```

`assert_t3_schema.py` 的 503 列比较也通过 type/null/default/identity/generated 五类属性。P7 省略 `public_id` 插入后返回真实 UUID，行为与 catalog 一致。

### 3.2 FK action——实体通过

独立读取 `pg_constraint.confdeltype`：

```text
28 基础 FK：27 NO ACTION + platform_accounts->tenants 1 RESTRICT
58 组合 FK：47 NO ACTION + 10 CASCADE + 1 RESTRICT
```

11 条组合 action 与 v6 字段行逐条一致。P6 删除独立 platform account 后 profile 数量为 0；N4 有 offer 时删除 supplier 违反约束，移除 offer 后可删除。当前 migration 的 action 实体正确。

### 3.3 downgrade——通过

生成器与 canonical migration 均为：

```python
for w in reversed(WAVES):
    for t in reversed(w):
        op.drop_table(t, schema=SCHEMA)
```

drill 的 AST 断言、T3 单包 downgrade 到 `60enum000000`、T1/T2 保留及 re-upgrade 均通过。drop 序列首表为 `alert_deliveries`，末表为 `tenants`。

---

## 四、R56-1：定义级 exact-set 门禁仍有漏检

当前数据库实体经 Codex 独立查询是正确的；本节针对 `assert_t3_schema.py` 自身的回归拦截能力。

### 4.1 28 个基础 FK 未比较约束名，且 27 个未比较 delete action

文件头声明基础/组合 FK 均比较“约束名、ON DELETE action”，但基础 FK 分支实际只验证：

- 表上存在 `(tenant_id)->tenants(id)`；
- `platform_accounts` 的 action 为 RESTRICT。

其余 27 个基础 FK 即使被改为 CASCADE/SET NULL，当前分支仍可通过；28 个基础 FK 名称也未进入 expected。实际 catalog 当前是 27 NO ACTION + 1 RESTRICT，但门禁没有冻结该完整集合。

### 4.2 4 个 NULLS 索引未比较名称；2 个 exclusion 只比较名称集合

NULLS 查询虽然取出了 index name，却只把 `(table, columns)` 放入比较集合。索引改名后仍显示 PASS。

exclusion 当前逻辑等价于：

```sql
SELECT conname
FROM pg_constraint
WHERE connamespace='app'::regnamespace AND contype='x';
```

随后只做名称集合比较，没有比较：

- 目标表；
- GiST 元素、运算符与表达式；
- `pricing_decisions` 的 `WHERE status='approved'`；
- `policy_versions` 的 `COALESCE(tenant_id,0)`、scope 维度及时间范围；
- 精确对象数量（集合比较会折叠重复名称）。

因此保留同名但改变 exclusion 语义时，当前 schema 断言仍可通过。P5 只覆盖 pricing exclusion，policy exclusion 没有行为探针。独立 `pg_get_constraintdef` 显示当前两个实体定义正确，但自动门禁未冻结它们。

### 4.3 31 个业务主键与 34 个普通 UNIQUE 未进入 expected-set

独立解析 v6 并查询 catalog：

```text
业务 PK               = 31，全部为单列 id
普通 UNIQUE           = 34/34，missing=0，extra=0
父候选 UNIQUE         = 17
全部 UNIQUE constraint = 51
```

`t3_expected.py` 没有 PK 和 34 个普通 UNIQUE 的独立期望数据；`assert_t3_schema.py` 的 `contype='u'` 查询只覆盖 17 个父候选键，也没有业务 PK 查询。删除或改变 `public_id`、幂等键、步骤键等普通 UNIQUE 后，现有 503 列/FK/索引断言仍可能全部通过。

### 4.4 表达式规范化删除全部括号

`norm_expr()` 当前执行：

```python
s = s.replace("(", "").replace(")", "")
```

这会把不同逻辑优先级的 CHECK/谓词规范化成同一 token 串。例如改变 `AND/OR` 分组时可能仍被视为相等。对 exact-set 门禁，应只消除 PostgreSQL 稳定添加的外层括号与无关 cast，保留内部逻辑分组；或用结构化 catalog 字段验证。

---

## 五、四脚本执行证据

Codex 串行独立执行：

```text
python scripts/gen_t3_migration.py --check  exit 0
python scripts/assert_t3_schema.py          exit 0 / T3-SCHEMA-ASSERT: PASS
python scripts/assert_t3_probes.py          exit 0 / T3-PROBES: PASS
python scripts/t3_tables_drill.py           exit 0 / T3 DRILL: PASS
```

drill 在首次 upgrade、re-upgrade、重复 upgrade 三个阶段均运行 schema 与 probes；单包回退时断言 revision=`60enum000000`、业务表=0、enum=60、`btree_gist` 与 owner mark 保留。

测试结束后独立查询：

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

---

## 六、round-57 最小回修口径

R56-1 仅补验收门禁，当前实体 migration 无需重做。请 DSH：

1. 在 `t3_expected.py` 增加 28 基础 FK 的 table/name/columns/action、31 PK、34 普通 UNIQUE、4 NULLS 的 index name，以及 2 exclusion 的 table + 完整定义期望；
2. 在 `assert_t3_schema.py` 对上述对象执行缺失=0、多余=0的定义级比较；exclusion 至少比较 `pg_get_constraintdef` 规范结构与目标表；
3. 修正 `norm_expr`，保留内部逻辑括号，并增加不同 AND/OR 分组不得等价的机械负例；
4. 保持四脚本全绿及最终 `31tbl000001 (head)`；附新增/变更文件哈希。

建议下一份交接文件：`from-dsh/round-57-dsh-P0-1-T3门禁回修.md`。Codex 下一轮只复核 R56-1，闭合后即可标记 **T3 COMPLETE** 并进入 T4。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-56-->
