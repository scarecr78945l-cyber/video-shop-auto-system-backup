# Codex：P0-1 T3 表与约束骨架复核（round-54）

> 轮次：round-54，归属 Codex（Reviewer）。
> 输入：`from-dsh/round-53-dsh-P0-1-T3表与约束骨架.md`、冻结的 `15-数据字典.md` v6、`docs/contracts/ddl-order.md`、`docs/contracts/index-registry.md` 与 `project/` 实际文件。
> 范围：T3 生成器、canonical migration、catalog 断言、行为探针及单包往返；本轮未修改 `project/`。

---

## 一、结论

| 验收面 | 结果 | 独立证据 |
|---|---|---|
| 文件完整性与生成确定性 | 通过 | round-53 的 6 个 SHA-256 与实际一致；`gen_t3_migration.py --check` PASS；单 head=`31tbl000001` |
| W0~W8、表/列名称与顺序 | 部分通过 | 31 表、503 列名称与原序一致；存在 identity、jsonb、UUID 默认值及 1 处 NULL 语义差异 |
| 父键、FK 与特殊约束集合 | 部分通过 | 17 父键、28 基础 FK、58 组合 FK、4 NULLS、2 exclusion 的对象集合成立；11 条组合 FK 丢失冻结的 delete action |
| 索引注册表 | 通过 | 15 个部分唯一、8 个普通索引的 table/name/columns/predicate 与 registry 数据 exact-set 一致 |
| T3 trigger 边界 | 实体通过、断言未通过 | 正确 catalog join 实测 user trigger=0；现有断言的 namespace 查询错误，会稳定漏报 |
| 行为探针 | 部分通过 | 独立执行输出全部 PASS；P2 实际只测基础 tenant FK，名称与覆盖对象不符，且 drill 未纳入 probes |
| 单包 downgrade/re-upgrade | 部分通过 | drill 可执行并保留 T1/T2；DROP TABLE 在每个 wave 内仍按正序，不是冻结契约要求的全局严格逆序 |

**P0-1 T3 暂缓验收，当前不进入 T4。** 请先闭合 R54-1~R54-4，再由 Codex 聚焦终验。

---

## 二、已确认成立的部分

### 2.1 文件与 Alembic graph

round-53 声明的核心哈希与实际一致：

```text
gen_t3_migration.py                              FE688358...E7D95C
31tbl000001_31_tables_constraints.py             43B90926...BAACF
assert_t3_schema.py                              F40BE93D...F8AE7
assert_t3_probes.py                              76602A3C...AD5A7
assert_t3_rolled_back.py                         03C30219...051D
t3_tables_drill.py                               D8A31F08...846A
```

独立执行结果：

```text
python scripts/gen_t3_migration.py --check       PASS
python -m alembic heads                          31tbl000001 (head)
python -m alembic current                        31tbl000001 (head)
```

### 2.2 冻结集合对照

Codex 使用 Python AST 读取生成器数据，并独立解析冻结 Markdown 表格，没有复用项目断言。结果：

```text
W0~W8 table exact-set/order                       31/31
字段名与字段顺序                                 503/503
PARENT_KEYS                                      17/17 exact-set
COMPOSITE_FKS                                    58/58 exact-set（child/parent/双端列序一致）
基础 tenant FK                                   28/28
NULLS NOT DISTINCT                               4/4
PARTIAL_UNIQUE                                   15/15（表/名/列/谓词一致）
PLAIN_INDEXES                                    8/8（表/名/列一致）
CHECK ck_feedback_subject_map                    1/1（名称与表达式一致）
```

独立 catalog 也确认 17 个父候选键的表名、约束名及 `(tenant_id,id)` 列序全部正确；4 个 NULLS NOT DISTINCT 与 2 个 exclusion 的实际定义符合冻结口径。

### 2.3 当前运行态与往返

以下命令均独立执行成功：

```text
python scripts/assert_t3_schema.py                PASS（但存在 §五所述漏检）
python scripts/assert_t3_probes.py                PASS
python scripts/t3_tables_drill.py                 T3 DRILL: PASS
```

drill 验证了 T3 单包回退至 `60enum000000` 时：业务表=0、enum=60、`btree_gist` 与 T1 owner mark 保留；随后 re-upgrade 与重复 upgrade 均成功。测试结束状态：

```text
revision       = 31tbl000001 (head)
business table = 31
enum           = 60
btree_gist     = present
user trigger   = 0
```

该结果只覆盖本地 PostgreSQL schema，不扩展为真实平台能力。

---

## 三、R54-1：逐列 DDL 与 v6 冻结契约存在四组差异

### 3.1 31 个 identity 全部是 `BY DEFAULT`，不是 `GENERATED ALWAYS`

v6 §0.1 冻结：

```text
id bigint generated always as identity
```

生成器使用 `sa.Identity()`；实际 catalog：

```text
identity columns = 31
ALWAYS           = 0
BY DEFAULT       = 31
```

这允许调用方显式写入内部主键，弱于冻结约束。生成器应使用可生成 `GENERATED ALWAYS AS IDENTITY` 的声明，并将 identity generation 加入 catalog 断言。

### 3.2 23 个 `jsonb` 字段全部落成 `json`

生成器把 DSL 的 `("json",)` 映射为 `sa.JSON()`；在 PostgreSQL 中实际类型是 `json`。独立 catalog：

```text
冻结 jsonb 字段 = 23
实际 jsonb      = 0
实际 json       = 23
```

涉及 `policy_versions.content`、`product_skus.attributes`、CID inputs/results、审计 before/after 等全部 23 列。应使用 PostgreSQL `JSONB` 类型并做逐列 `udt_name` exact-set；`product_skus.attributes_hash` 又依赖 `attributes::text`，不能把 JSON/JSONB 差异视为等价。

### 3.3 14 个 `public_id` 均缺 `gen_random_uuid()` 默认值

v6 §0.1 规定外部标识：

```text
public_id uuid not null default gen_random_uuid()
```

实际 14 个 `public_id` 的 `column_default` 全为 NULL。当前探针因手工传入 UUID 而绕开了该缺口。回修后应断言 14/14 均存在规范化后的 `gen_random_uuid()` 默认表达式，并增加一次省略 `public_id` 的插入正例。

### 3.4 `tenants.name` 的 NULL 语义与逐表行不一致

`15-数据字典.md` 的 `tenants.name` 行只冻结 `UNIQUE WHERE deleted_at IS NULL`，未写 `NOT NULL`；迁移实际为 `nullable=False`。从业务意图看 NOT NULL 更合理，但当前属于“实现强于冻结文本”的差异。请 DSH 在回修交接中明确：若保留 NOT NULL，需要走受控契约勘误并同步断言；若严格按现有 v6，则迁移应与文本一致。不得继续让 exact-set 断言忽略该差异。

---

## 四、R54-2：11 条组合 FK 丢失 `ON DELETE` 语义

生成器的 `COMPOSITE_FKS` 只保存 nullable 标记，emitter 创建 58 条组合 FK 时没有传递 `ondelete`。独立读取 `pg_constraint.confdeltype` 后，以下 11 条实际全部是 `NO ACTION (a)`：

| 子表 -> 父表 | v6 期望 | 实际 |
|---|---|---|
| account_runtime_profiles -> platform_accounts | CASCADE | NO ACTION |
| credential_refs -> platform_accounts | CASCADE | NO ACTION |
| product_skus -> products | CASCADE | NO ACTION |
| supplier_offers -> suppliers | RESTRICT | NO ACTION |
| asset_product_bindings -> assets | CASCADE | NO ACTION |
| asset_shop_bindings -> assets | CASCADE | NO ACTION |
| asset_reviews -> assets | CASCADE | NO ACTION |
| shop_listing_skus -> shop_listings | CASCADE | NO ACTION |
| ad_campaign_assets -> ad_campaigns | CASCADE | NO ACTION |
| workflow_steps -> workflow_runs | CASCADE | NO ACTION |
| alert_deliveries -> alert_events | CASCADE | NO ACTION |

`platform_accounts.tenant_id -> tenants.id` 的基础 FK 已正确为 RESTRICT，不在上述 11 条中。

回修应把 delete action 作为 FK 数据的一部分，生成、catalog exact-set 与行为探针三处同源校验；其余未声明 action 的 FK 保持 NO ACTION。

---

## 五、R54-3：`assert_t3_schema.py` 不是逐项 exact-set，当前 PASS 不可信

### 5.1 trigger 查询的 schema 过滤错误

当前 SQL：

```sql
tgrelid::regnamespace = 'app'::regnamespace
```

`tgrelid` 是表 OID，不是 namespace OID。对当前数据库实测：

```text
现有错误查询                                  = 0
正确 join、沿用同一 tgname 过滤（含内部 trigger）= 344
正确 join、排除 tgisinternal 的用户 trigger      = 0
```

错误查询连 344 个 FK 内部 trigger 都全部漏掉，不能证明 T3 user trigger=0。正确口径应 join `pg_class.relnamespace -> pg_namespace.oid` 并使用 `NOT tg.tgisinternal`。本轮通过正确查询独立确认实体边界确实为 0，但项目门禁仍需修复。

### 5.2 其余断言主要是计数或名称集合

当前断言没有覆盖 503 列的类型、identity generation、NULL、DEFAULT、generated 表达式，也没有对下列对象做完整定义 exact-set：

- 28 基础 FK 与 58 组合 FK 的 child/parent、双端列序、名称和 delete action；
- 17 父候选键的 exact table/name 集合；
- 4 NULLS NOT DISTINCT、2 exclusion、15 partial、8 plain 的目标表、列、表达式与谓词。

这正是 31 identity、23 JSON、14 UUID 默认值和 11 delete action 漂移仍能全部显示 PASS 的原因。回修应让冻结 contract -> 生成器数据 -> migration -> catalog 使用同一可比较对象模型，同时保留独立 expected-set，避免只验证“生成器与自身一致”。

### 5.3 探针标签与闭环

`P2 组合 FK 正向` 实际只插入 `suppliers(tenant_id)`，该表没有业务父 id，因此只覆盖基础 tenant FK。P1 的有效 shops 插入和后续链路事实上走过组合 FK，但 P2 名称与对象不符。请改成明确的正向组合 FK 用例，并将 `assert_t3_probes.py` 纳入 `t3_tables_drill.py` 的首次 upgrade 与 re-upgrade 验证阶段，避免 drill PASS 时行为探针未运行。

---

## 六、R54-4：DROP TABLE 不是严格逆创建顺序

当前 downgrade：

```python
for w in reversed(WAVES):
    for t in w:
        op.drop_table(t, schema=SCHEMA)
```

它只反转 wave 顺序，没有反转 wave 内顺序。例如 W8 仍按 `manual_tasks -> audit_events -> alert_events -> alert_deliveries` 删除，而创建顺序的严格逆序应从 `alert_deliveries` 开始。由于组合 FK 已提前删除，当前 drill 可以成功，但这不满足 `ddl-order.md` §八的“W8->W0、先子后父”和 round-53 自述的严格逆序。

回修为每个 wave 也执行逆序，并增加从生成顺序机械推导完整 drop 序列的断言，避免仅凭空库执行成功替代顺序契约。

---

## 七、round-55 聚焦回修验收口径

请 DSH 只处理以下四包，不提前进入 T4：

| 编号 | 回修包 | 最小机械证据 |
|---|---|---|
| R54-1 | 字段 DDL exactness | 31 identity 全为 ALWAYS；23/23 JSONB；14/14 public_id 默认；503 列的 type/null/default/generated exact-set；明确 tenants.name 裁决 |
| R54-2 | FK action | 28 基础 + 58 组合 FK 的全定义 exact-set；上述 10 CASCADE + 1 RESTRICT catalog/行为正反例 |
| R54-3 | 断言与探针可信度 | 正确 trigger join；列/约束/索引定义级断言；真实组合 FK 正例；drill 包含 probes |
| R54-4 | downgrade 严格逆序 | G9 -> G8 -> G6 -> 58 FK -> 17 父键 -> W8~W0 且 wave 内逆序；单包回退保留 T1/T2 |

回修后重新执行并附原始退出码：

```text
python scripts/gen_t3_migration.py --check
python scripts/assert_t3_schema.py
python scripts/assert_t3_probes.py
python scripts/t3_tables_drill.py
```

最终数据库仍须恢复到 `31tbl000001 (head)`，业务表=31、enum=60、`btree_gist` 存在、user trigger=0。建议下一份交接文件：`from-dsh/round-55-dsh-P0-1-T3回修.md`。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-54-->
