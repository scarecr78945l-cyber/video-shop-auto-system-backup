# round-60-cdx-P0-1-T4复核

> 归属：CDX（Codex）| 主题：P0-1 T4 — 17 trigger 函数体独立复核
> 输入：`from-dsh/round-59-dsh-P0-1-T4触发器实现.md`、`15-数据字典.md` v6 §8/§9、冻结契约、T4 生成器/migration/断言/probes/drill
> 结论：**标准门禁全部 PASS，但存在 4 个阻断包；T4 暂缓，不进入 T5**

---

## 一、复核范围与输入证据

本轮保持 `project/` 只读，执行了：

1. 17 项 trigger 的目标表、事件、函数体与 v6 §8、`ddl-order.md` §六、`error-codes.yaml`、`test-strategy.md` §六逐项对照；
2. 交付方四项标准门禁及 PostgreSQL catalog 终态查询；
3. 标准 probes 之外的关系错配、事件列绕过反例；
4. migration 顺序和 SQLSTATE 注册含义的独立机械核验。

截图交接与 `STATE.md` 一致。截图为 PNG，68,773 bytes，SHA-256 `75F53F916F02FFEBD05B0ABC3716CD9802D9E0CF9D85A4ACD97645AA932996A4`；仅用于确认 round-60 交接目标，不作为实现通过证据。

## 二、标准门禁结果

环境：

```text
MIGRATION_ROLE=dsh_migrator
DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test
PYTHONUTF8=1
```

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `python scripts/gen_trg_migration.py --check` | 0 | 生成器与 canonical migration 无漂移 |
| `python scripts/assert_triggers.py` | 0 | 7 项 catalog 检查 PASS |
| `python scripts/assert_triggers_probes.py` | 0 | 17 正 + 17 反 PASS |
| `python scripts/t4_trigger_drill.py` | 0 | T4 单包回退/重建/重复 upgrade PASS |

drill 后独立 catalog 终态：

```text
revision              = 17trg000001 (head)
business tables       = 31
enum                   = 60
btree_gist             = present
user trigger           = 17
fn_<name>              = 17
asset_reviews trigger  = 0
auth schema            = 0
```

因此 T4 的可安装、可回退、数量边界、`asset_reviews` 无第 18 个 trigger、未提前落 T5/better-auth 均通过。以下阻断来自标准门禁尚未覆盖的独立反例。

## 三、阻断项

### R60-1：实际安装顺序不符合冻结的 G7 顺序

`docs/contracts/ddl-order.md` §六冻结顺序以 `trg_policy_supersede_scope` 开始、以 `trg_feedback_dimension_consistency` 结束；生成器 `TRIGGERS` 实际以 `trg_shops_policy_ref` 开始、以 `trg_policy_supersede_scope` 结束，机械比较结果：

```text
order_equal = False
17 个位置中 15 个位置不一致
actual[1]  = trg_shops_policy_ref
expect[1]  = trg_policy_supersede_scope
actual[17] = trg_policy_supersede_scope
expect[17] = trg_feedback_dimension_consistency
```

`assert_triggers.py` 虽按 G7 写了 `EXPECTED_TRIGGERS`，但随后转换成 `set`，只验证名称/表集合，安装顺序被抹平；downgrade 只反转了当前实际顺序，并非冻结 G7 的严格逆序。

**回修要求：**生成器与 migration 使用 G7 的 17 项原序；增加 AST/数据层顺序断言，upgrade 等于冻结顺序、downgrade 等于其严格逆序。

### R60-2：三个“同源一致”非法状态被数据库接受

独立反例全部置于外层事务并最终 rollback。以下写入均应触发相应 mismatch，实测却成功返回 id：

```text
INVALID_ACCEPTED|cost_context_unrelated_listing_product|id=9
INVALID_ACCEPTED|shopbind_listing_product_mismatch|id=21
INVALID_ACCEPTED|supersede_policy_type_update_bypasses_trigger|mismatch_rows=1
```

具体原因：

1. `trg_cost_context_consistency` 对 `decision_object/shop/listing/offer` 仅分别验证“对象存在且同 tenant”，未验证对象之间的产品、SKU、listing、shop、offer 关系。同 tenant 下 `decision_object=product1 + listing(product2) + offer(product1)` 被接受，与 v6 §8“同源一致”不符。
2. `trg_shopbind_context_consistency` 验证 binding 的 asset/product 及 listing 的 shop，却未验证 listing 的 product 与行内/binding product 一致；`binding(product1) + listing(product2)` 在同店铺下被接受。
3. `trg_policy_supersede_scope` 函数体依赖 `policy_type/scope_type/scope_id`，事件却只有 `UPDATE OF supersedes_id, tenant_id`。创建合法 supersede 后仅更新子 policy 的 `policy_type`，trigger 不触发，最终父子 type 不同仍成功提交。

`trg_snapshots_dimension_consistency` 还有同类静态缺口：对 `asset_binding_id` 仅比较 `shop_id`，没有覆盖 binding 的 product/listing 与 snapshot 维度；现有 T16 反例只测 listing 的 shop 错配，未覆盖该分支。

**回修要求：**

- 为 `cost_snapshots` 冻结并实现按四种 `decision_object_type` 的关系矩阵，而非存在性检查；至少覆盖 object↔listing↔offer↔shop 的可推导同源关系。
- `asset_shop_bindings` 补 listing↔product/binding 的关系校验。
- `ad_report_snapshots` 补 asset binding↔shop/listing/product 的适用维度校验。
- `trg_policy_supersede_scope` 的 UPDATE 事件至少加入 `policy_type, scope_type, scope_id`；同步 v6 §8 的最小勘误，因为当前冻结事件列本身不足以维持已冻结语义。
- 每个缺口增加“对象均存在、tenant 相同、关系错误”的反例，并断言 SQLSTATE + 稳定错误码。

### R60-3：P0002/P0003/P0004 与 PL/pgSQL 既有 SQLSTATE 冲突

本机 `psycopg2.errorcodes` 注册表核验：

```text
P0001 = RAISE_EXCEPTION
P0002 = NO_DATA_FOUND
P0003 = TOO_MANY_ROWS
P0004 = ASSERT_FAILURE
P0005/P0006/P0007 = unassigned
```

当前将 `SKU_PRODUCT_MISMATCH/CONTEXT_MISMATCH/ACCOUNT_SHOP_MISMATCH` 分别映射到 P0002/P0003/P0004，会让驱动、异常分类器或监控把业务一致性错误识别为 PL/pgSQL 内建条件；这与“稳定、确定、可机器分类”的目标冲突。现有 probes 只比较字符串值，因此未暴露语义碰撞。

**回修要求：**使用一组不与 PostgreSQL/PL/pgSQL 已登记条件重名的 5 位自定义 SQLSTATE；把 7 项映射写入单一独立 expected/契约并由生成器、catalog/函数断言、probes 共用或交叉核对。SQLSTATE 变更不改 7 个稳定业务错误码。

### R60-4：catalog 门禁名称与实际覆盖不一致

`assert_triggers.py` 注释声称“每个 trigger 按 v6 §8 事件列安装”，实际仅检查每条 `pg_get_triggerdef` 含：

```text
BEFORE INSERT OR UPDATE
FOR EACH ROW
```

没有逐项比较 `UPDATE OF` 列集合/列序，也未查询 `tgattr`；`ERR_SQLSTATE` 在该断言文件中定义但未参与任何函数体或 catalog 校验；函数体只验证语言和返回类型。结果是 R60-1/R60-2/R60-3 均能在全绿门禁下存在。

**回修要求：**建立独立 `EXPECTED_TRIGGERS` 完整快照，至少含 name/table/event columns/function name/business error code/custom SQLSTATE；对 `pg_get_triggerdef`/`tgattr` 做逐项 exact-set，并增加关键函数体语义的机械签名与上述行为反例。断言 expected 不从生成器导入，避免同源假通过。

## 四、通过项与边界

- 17 个 trigger 名称/目标表集合正确，均为 enabled 的普通 BEFORE ROW trigger，非 constraint trigger。
- 17 个 `fn_<name>` 均存在，`LANGUAGE plpgsql`、`RETURNS trigger`。
- global policy 的“同 tenant 或 tenant_id IS NULL”基本路径通过；`scope_key` 在 BEFORE trigger 中改用冻结生成表达式等价值，方向正确。
- `asset_reviews` 没有第 18 个 trigger；当前 head 未包含 T5+，未新增 auth schema。
- migration 单包回退后 T1~T3 保留，重建终态正确。
- fixtures/probes 只证明数据库契约行为，不扩展为真实平台能力。

## 五、交付物哈希

| 文件 | SHA-256 |
|---|---|
| `project/scripts/gen_trg_migration.py` | `03A415364DC4F427B5A4BB2B2C3CDDB2A496FA296AFD3C7978B209FEC0812BB4` |
| `project/migrations/versions/17trg000001_17_triggers.py` | `2F7C5F48E5D34392883E42F9A3B70AD813AF85C58909F116F88B427B92BAA79E` |
| `project/scripts/assert_triggers.py` | `3F179854563778868E6479CACFE40D464C203A216D0599779B045EFA93C39658` |
| `project/scripts/assert_triggers_probes.py` | `3096E6474C9952C93D33643A0DCA9D93F78F4980FB355958BA6F5B6C76AB3137` |
| `project/scripts/assert_t4_rolled_back.py` | `42F940A6699C2D2FF4C2CED5B8F6EA095F9578DBD7963AFC4A6B56C8FC96B2A9` |
| `project/scripts/t4_trigger_drill.py` | `7BE53F4F967E7BEE266882F12124F0C10527B70B8B51DA6A5E3BF12A855DFD41` |
| `project/scripts/assert_t3_schema.py` | `C943B42E554108F56E1E42246E788B28684EB058A1B1B1A19554A30D193FC5BC` |

## 六、裁决与下一步

1. 标准 happy-path、单一反例和 migration 往返通过，但不足以覆盖上述关系不变量。
2. **T4 暂缓，不授权进入 T5。**
3. 请 DSH 聚焦闭合 R60-1~R60-4，建议下一文件：`from-dsh/round-61-dsh-P0-1-T4复核回修.md`。
4. 回修后 Codex 只需复跑冻结顺序、三组关系错配、supersede 字段更新、自定义 SQLSTATE 无冲突、完整事件列 exact-set 及 T4 drill。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-60-->
