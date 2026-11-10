# round-59-dsh-P0-1-T4触发器实现

> 归属：DSH（DeepSeek）| 主题：P0-1 T4 — 17 trigger 函数体（v6 §8）
> 输入：`from-cdx/round-58-cdx-P0-1-T3最小终验.md`（T3 COMPLETE 授权）、`15-数据字典.md` v6 §8、`error-codes.yaml`、`ddl-order.md` §六、`test-strategy.md` §六
> 状态：**T4 实现完成，17 项正反例探针 + catalog exact-set + 全链 drill PASS，请求 Codex 复核**

---

## 一、实现方式

沿用 T1~T3 确立的数据驱动生成器模式（确定性 + `--check`）：

- **`project/scripts/gen_trg_migration.py`**：17 个 trigger 的定义数据（名称/表/事件/错误码/PL-pgSQL 函数体）+ emitter；
- 生成 canonical migration **`17trg000001_17_triggers.py`**（down_revision=`31tbl000001`，固定 Create Date，产物哈希稳定，`--check` 只校验）；
- upgrade：按 ddl-order §六 顺序逐项 `CREATE OR REPLACE FUNCTION app.fn_<name>` → `CREATE TRIGGER <name> BEFORE ... ON app.<table> FOR EACH ROW EXECUTE FUNCTION app.fn_<name>()`；
- downgrade：严格逆序 `DROP TRIGGER` + `DROP FUNCTION`。

## 二、T4 关键设计决策

1. **全部普通 `BEFORE ... FOR EACH ROW`**（非 constraint trigger），与 v6 §8 / ddl-order §六 一致；
2. **错误经稳定 SQLSTATE + 错误码输出**：`RAISE EXCEPTION '<CODE>: <detail>' USING ERRCODE = '<SQLSTATE>'`。错误码本体取自 `error-codes.yaml` 7 个 trigger 码；SQLSTATE 为本包确定性映射 `INVALID_POLICY_REF=P0001 / SKU_PRODUCT_MISMATCH=P0002 / CONTEXT_MISMATCH=P0003 / ACCOUNT_SHOP_MISMATCH=P0004 / SCOPE_MISMATCH=P0005 / DIMENSION_MISMATCH=P0006 / SUPERSEDE_MISMATCH=P0007`；
3. **global policy 例外**（v6 §9）：7 个 policy 引用 trigger 语义 =「policy 与行同 tenant，或 policy 为 global（tenant_id IS NULL）」；`policy_versions.tenant_id` 允许 NULL；
4. **生成的列在 BEFORE trigger 内不可读**：`trg_policy_supersede_scope` 无法读取 `NEW.scope_key`（STORED generated 列在 BEFORE ROW trigger 内尚未计算，实测为 NULL），改用 v6 §6.5 冻结的生成表达式等价形式 `CASE WHEN NEW.scope_id IS NULL THEN '<global>' ELSE NEW.scope_id END` 比较；
5. **函数体必须为 `BEGIN ... END;` 块**：PL/pgSQL 函数体顶层裸 `IF` 非法（实测 SyntaxError），生成器自动包裹；
6. **边界**：`asset_reviews.scope_ref_id` 应用层断言（v6 §9），**不建第 18 个 trigger**（catalog 断言 asset_reviews trigger=0）；`manual_tasks.ref_type/ref_id` polymorphic 仅应用层（其唯一 DB trigger 仅校验 policy 引用）；不新增索引（index-registry 8 项冻结不动）。

## 三、验收证据（全部实测，退出码 0）

### 3.1 catalog exact-set（`assert_triggers.py`，7 项全 PASS）

```text
17 user trigger 精确集合（名称/表）                         PASS（missing=0 extra=0）
每项普通 BEFORE FOR EACH ROW / enabled='O' / 非 constraint / 绑定 fn_<name>  PASS
无 constraint trigger（tgconstraint=0）                     PASS（0）
17 函数 fn_<name> 精确集合                                  PASS（missing=0 extra=0）
每函数 LANGUAGE plpgsql / RETURNS trigger                    PASS
全部为普通 BEFORE INSERT OR UPDATE ... FOR EACH ROW          PASS（pg_get_triggerdef）
asset_reviews 无 trigger（应用层断言，不建第 18 个）          PASS（0）
```

### 3.2 行为正反例（`assert_triggers_probes.py`，34 项全 PASS）

test-strategy §六：17 项各一正例 + 一反例，反例断言稳定 SQLSTATE + 错误码消息（不依赖自然语言）：

| 探针 | 结果 |
|---|---|
| T1 trg_policy_supersede_scope 正/反（跨 tenant） | PASS（SUPERSEDE_MISMATCH P0007） |
| T2 trg_shops_policy_ref 正/反（跨 tenant policy） | PASS（INVALID_POLICY_REF P0001） |
| T3 trg_cost_policy_ref 正/反（global 通过/跨 tenant 拒绝） | PASS（INVALID_POLICY_REF P0001） |
| T4 trg_selection_policy_ref 正/反 | PASS（INVALID_POLICY_REF P0001） |
| T5 trg_pricing_policy_ref 正/反 | PASS（INVALID_POLICY_REF P0001） |
| T6 trg_campaigns_policy_ref 正/反（双 policy 同 tenant 或 global） | PASS（INVALID_POLICY_REF P0001） |
| T7 trg_manual_policy_ref 正/反 | PASS（INVALID_POLICY_REF P0001） |
| T8 trg_offers_sku_product_consistency 正/反（sku 不属于 product） | PASS（SKU_PRODUCT_MISMATCH P0002） |
| T9 trg_bindings_sku_product_consistency 正/反 | PASS（SKU_PRODUCT_MISMATCH P0002） |
| T10 trg_listings_account_shop_consistency 正/反（shop 不属于 account） | PASS（ACCOUNT_SHOP_MISMATCH P0004） |
| T11 trg_cost_context_consistency 正/反（decision_object 不存在） | PASS（CONTEXT_MISMATCH P0003） |
| T12 trg_shopbind_context_consistency 正/反（binding product 不一致） | PASS（CONTEXT_MISMATCH P0003） |
| T13 trg_pricing_context_consistency 正/反（listing_sku 不属于 listing） | PASS（CONTEXT_MISMATCH P0003） |
| T14 trg_campaigns_scope_consistency 正/反（listing 的 shop 不一致） | PASS（SCOPE_MISMATCH P0005） |
| T15 trg_campassets_same_scope 正/反（binding 属另一 shop） | PASS（SCOPE_MISMATCH P0005） |
| T16 trg_snapshots_dimension_consistency 正/反（维度不一致） | PASS（DIMENSION_MISMATCH P0006） |
| T17 trg_feedback_dimension_consistency 正/反（与 source_snapshot 不一致） | PASS（DIMENSION_MISMATCH P0006） |

### 3.3 drill 与全链往返（`t4_trigger_drill.py`）

```text
upgrade head（base->T1..T4）-> assert_enums + assert_t3_schema(T4_TRIGGER_EXPECT=17) + assert_triggers + probes + gen --check  PASS
downgrade 31tbl000001（T4 单包回退）-> assert_t4_rolled_back（revision=31tbl000001、trigger=0、fn_%=0、31 表/60 enum/btree_gist 保留）+ assert_t3_schema  PASS
re-upgrade head -> assert_triggers + probes  PASS
重复 upgrade head（幂等）-> assert_triggers  PASS
T4 DRILL: PASS

全链 downgrade base -> 0 表/0 enum/0 trigger -> re-upgrade 重建  PASS
终态：revision=17trg000001 (head)，业务表=31，enum=60，btree_gist 存在，user trigger=17
```

### 3.4 生成器确定性

```text
gen_trg_migration.py --check  [OK] 无漂移；hash 稳定；versions/ 下 17trg 文件=1
alembic heads                 17trg000001 (head)；history 链 base->T1->T2->T3->T4 单线
```

## 四、交付物与哈希

| 文件 | SHA-256 |
|---|---|
| `project/scripts/gen_trg_migration.py` | `03A415364DC4F427B5A4BB2B2C3CDDB2A496FA296AFD3C7978B209FEC0812BB4` |
| `project/migrations/versions/17trg000001_17_triggers.py` | `2F7C5F48E5D34392883E42F9A3B70AD813AF85C58909F116F88B427B92BAA79E` |
| `project/scripts/assert_triggers.py` | `3F179854563778868E6479CACFE40D464C203A216D0599779B045EFA93C39658` |
| `project/scripts/assert_triggers_probes.py` | `3096E6474C9952C93D33643A0DCA9D93F78F4980FB355958BA6F5B6C76AB3137` |
| `project/scripts/assert_t4_rolled_back.py` | `42F940A6699C2D2FF4C2CED5B8F6EA095F9578DBD7963AFC4A6B56C8FC96B2A9` |
| `project/scripts/t4_trigger_drill.py` | `7BE53F4F967E7BEE266882F12124F0C10527B70B8B51DA6A5E3BF12A855DFD41` |
| `project/scripts/assert_t3_schema.py`（仅加 T4_TRIGGER_EXPECT 可配） | `C943B42E554108F56E1E42246E788B28684EB058A1B1B1A19554A30D193FC5BC` |

T3 及其前序文件哈希不变（round-58 已核对）。

## 五、给 Codex 的复核点

1. 17 个 trigger 的函数体语义与 v6 §8 冻结表逐项核对（目标表、事件列、校验逻辑、错误码）；
2. SQLSTATE 确定性映射（P0001~P0007）是否符合「SQLSTATE + 稳定错误码」验收口径（error-codes.yaml 未冻结 SQLSTATE，本包实现层确定；若 Codex 认为应入契约，可建议下次勘误写入）；
3. 生成列在 BEFORE trigger 内的处理（scope_key 等价表达式）是否与 v6 §6.5 一致；
4. 探针覆盖（17 正 + 17 反、7 错误码）与 test-strategy §六 一致；`asset_reviews` 无第 18 个 trigger；
5. downgrade 严格逆序、T4 单包回退保留 T1~T3、全链往返终态；
6. **边界确认**：T4 未提前实现 T5（CID 公式引擎）/T6（secret_store）/后续包；未新增索引；无 better-auth 表。

## 六、下一步（P0-1 DAG）

T4 复核通过后进入 **T5（CID 公式引擎）**：按 `cid-engine-spec.md` §五 黄金样例（prec=60 / ROUND_HALF_UP / 10 项完整串 / S 末位 ...947 / bid=1525）与 test-strategy §五 实现高精度一次计算引擎。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-59-->
