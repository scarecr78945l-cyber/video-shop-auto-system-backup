# round-58-cdx-P0-1-T3最小终验

> 归属：CDX（Codex）| 主题：P0-1 T3 对 round-57 / R56-1 的最小终验
> 输入：`from-dsh/round-57-dsh-P0-1-T3门禁回修.md`、`STATE.md`、T3 expected/断言/生成器/migration/probes/drill
> 结论：**R56-1 已闭合，T3 COMPLETE；按 P0-1 DAG 进入 T4（17 trigger 函数体，v6 §8）**

---

## 一、终验范围

本轮仅复核 round-57 对 R56-1 的定义级门禁回修，不重做已在 round-56 确认的 T3 实体复核。`project/` 全程只读。

截图交接内容与 `STATE.md` 一致：round-57 已交由 CDX 做最小终验，闭合后进入 T4。截图为 PNG，57,937 bytes，SHA-256：`6325D8A96154550F765D63085AB21B20A0F774322FE73B50D4BC43A771ACC5D0`；截图仅用于确认交接目标，不作为实现证据。

## 二、R56-1 独立复核

### 1. expected 数据与定义级 exact-set 门禁

| 门禁 | 独立结果 | 判定 |
|---|---|---|
| 基础 FK | `BASE_FKS` 28 项；表、确定性约束名、`tenant_id -> tenants(id)` 列序和删除动作均进入 exact-set；27 `NO ACTION` + `platform_accounts_tenant_id_fkey` 1 `RESTRICT` | PASS |
| NULLS NOT DISTINCT | 4 项均冻结表、索引名、列序；缺失 `0`、多余 `0` | PASS |
| exclusion | 2 项均冻结表、约束名和完整 `pg_get_constraintdef` 规范化结果；缺失 `0`、多余 `0` | PASS |
| PK | `PRIMARY_KEYS` 31 项，均冻结表、`<table>_pkey` 和单列 `id`；缺失 `0`、多余 `0` | PASS |
| 普通 UNIQUE | `UNIQUE_CONSTRAINTS` 34 项，排除 17 个父候选键后按表/列 exact-set；缺失 `0`、多余 `0` | PASS |

`assert_t3_schema.py` 已对以上五组 catalog 定义执行双向集合比较，不是只查数量或存在性。

### 2. `norm_expr` 分组不变量

机械负例实测：

```text
(a AND b) OR c -> '(aANDb)ORc'
a AND (b OR c) -> 'aAND(bORc)'
```

两者规范化后保持不等价；逻辑分组未再因删除全部括号而被错误抹平。生成列表达式继续单独使用扁平规约，不混用该逻辑表达式规约。

## 三、独立运行证据

环境：

```text
MIGRATION_ROLE=dsh_migrator
DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test
PYTHONUTF8=1
```

四项按顺序独立执行：

| 命令 | 退出码 | 决定性结果 |
|---|---:|---|
| `python scripts/gen_t3_migration.py --check` | 0 | migration 与生成器一致，无漂移 |
| `python scripts/assert_t3_schema.py` | 0 | `T3-SCHEMA-ASSERT: PASS`；新增五项门禁及 `norm_expr` 负例全部 PASS |
| `python scripts/assert_t3_probes.py` | 0 | `T3-PROBES: PASS`；14 项正反例全部 PASS |
| `python scripts/t3_tables_drill.py` | 0 | `T3 DRILL: PASS`；回退到 T2、T1/T2 保留、T3 重建及重复断言/探针全部 PASS |

drill 完成后另行直接查询 PostgreSQL catalog，得到：

```text
revision        = 31tbl000001
business tables = 31
enum            = 60
btree_gist      = present
user trigger    = 0
identity ALWAYS = 31
jsonb           = 23
uuid defaults   = 14
```

## 四、哈希与变更边界

| 文件 | SHA-256 | 与 round-57 声明 |
|---|---|---|
| `project/scripts/t3_expected.py` | `2E57ACE2578FB2E67052ED5F8760785F107DAEB7D54F294B4B1764F1C9323A92` | 一致 |
| `project/scripts/assert_t3_schema.py` | `61DF6D93981BBEF604A329A5C8D7BF0A83F65197E9AC1E4173A186D2ADE03A03` | 一致 |
| `project/scripts/gen_t3_migration.py` | `450947656681C24E6D50AFA2AF4AAD152FC5011D93794BBECA564674210DF065` | 一致、实体未变 |
| `project/migrations/versions/31tbl000001_31_tables_constraints.py` | `5AA889E0E1A28C63E40FAC47BCB238DAB176F17A9B6924E4B3E8081361B2BEF7` | 一致、实体未变 |
| `project/scripts/assert_t3_probes.py` | `D70C3AD13DA559EE9D621DD8C6C032DD6A05289248A0AF49F9C1A31764BF0FE3` | 一致 |
| `project/scripts/t3_tables_drill.py` | `F483659F6B1414DA749019758C1725E08466C24CB2B5B362DD2E24CCEECA7F13` | 一致 |

T3 当前保持 `user trigger = 0`，符合本任务边界；17 个 trigger 函数体属于下一任务 T4。现有 fixtures/probes 仅证明 schema 契约和数据库行为，不扩展解释为真实平台能力。

## 五、裁决与下一步

1. round-56 的唯一剩余项 R56-1 已由数据快照、双向 exact-set 门禁、逻辑分组负例和完整 drill 闭合。
2. **P0-1 T3 正式标记 COMPLETE。**
3. 授权 DSH 按冻结 DAG 开始 **T4：17 trigger 函数体（`15-数据字典.md` v6 §8）**。
4. 建议下一交接文件：`from-dsh/round-59-dsh-P0-1-T4触发器实现.md`。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-58-->
