# Codex 聚焦终验：数据字典 v4

> 轮次：round-12，归属 CDX。  
> 复核对象：`from-dsh/round-11-dsh-数据字典v3最终回修.md`、`15-数据字典.md` v4、`14-新立项最终方案.md`。  
> CID 证据：`_experiment/_interop/evidence/盈亏表T.xlsx`，SHA-256 `1723C9703CCA9CF5165B6EABDCE5EE2875AEE2630C01AD6336FE027F10256E5C`；仅采用 `cid盈亏表`。  
> 本轮仅做 round-10 四个阻断包的聚焦终验，不拆 P0-0/P0-1，不开发代码。

## 一、终验结论

v4 已落实一部分关键修订：31 表计数成立、合并字段已清零、`attributes_hash` 已成为实体生成列、`btree_gist`/`scope_key` 已写入契约、7 个跨实体校验名称已出现、CID 公式本身与原件一致、`subject_key varchar(128)` 解决了 category 字符串键的类型冲突，14/15 的 actor_registry 与 status/health_state 也已同步。

但本次按实际文档静态生成 DDL 与 Excel 代表行复算后，四个阻断包仍有三包未闭合、一包部分闭合：

1. **DDL 确定性：未通过**；
2. **tenant 组合 FK：未通过**；
3. **CID 精度与持久化：公式通过、存储契约未通过**；
4. **feedback subject：类型方向通过、可执行约束未通过**。

因此 round-12 结论为：**数据字典暂不冻结，暂不进入双方 P0-0/P0-1 任务拆解。** 本轮仅要求 DSH 做契约级最小回修，不扩展业务范围。

## 二、证据基线与静态结果

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `_experiment/_interop/STATE.md` | 3574 | `07DEE474CD3F295ADFF6AC2B1FAACD656AB92D452F1F919C270D5AC82CF6F860` |
| `from-dsh/round-11-dsh-数据字典v3最终回修.md` | 7624 | `BDEA9AFEEB711EE06B6135C17FBA25024EE6B4CBED29785E54576439095C6800` |
| `15-数据字典.md` v4 | 47152 | `F5B3B16BAD9C503D7EE28FB9C20D01B81AD21E6EDB1FEF7275AAB17DFCF2CD64` |
| `14-新立项最终方案.md` | 42383 | `50B1C6678CF79FC353187841697D502CC46FCB1DA267F71066C2E8000D9749A9` |
| `_experiment/_interop/evidence/盈亏表T.xlsx` | 51286084 | `1723C9703CCA9CF5165B6EABDCE5EE2875AEE2630C01AD6336FE027F10256E5C` |

静态抽检结果：

- 表标题：31；显式 FK 图 reciprocal edge：0；三组旧循环无回退。
- 合并字段行：0。
- 显式组合 FK 行：38；其中父表具备实际 `UNIQUE (tenant_id, id)` 目标的只有 8 条，剩余 30 条当前不足以生成有效 PostgreSQL FK。
- 文档实际只出现 2 个父表归属唯一键：`platform_accounts`（第 83 行）和 `shops`（第 104 行）。
- 同存 `tenant_id` 的表中，仍有 25 个指向 tenant-owned 父表的单列 FK 未配组合 FK 行。
- 命名 trigger：7 个；均只有名称与一句语义，没有触发时机、字段事件、constraint/deferrable 语义、函数签名与错误码。
- enum 字段共抽出 61 个；按 v4 自己声明的 `enum_<表>_<字段>` 规则，只有 2 个匹配，59 个不匹配。
- `NULLS NOT DISTINCT` 业务约束共 4 行，实际都写成 `(columns) NULLS NOT DISTINCT`；v4 §0.3 声明的 PostgreSQL 15 正式位置应为 `UNIQUE NULLS NOT DISTINCT (columns)`。

## 三、阻断包 1：DDL 可生成性

### 3.1 已通过项

- `product_skus.attributes_hash` 已定义，`attributes_canonical` 悬空引用已消失（第 201、210 行）。
- 15 处合并时间字段已拆开；本轮未检出 `field_a / field_b` 合并行。
- 文档已声明 migration 依赖 `CREATE EXTENSION IF NOT EXISTS btree_gist`（第 34 行）。
- `policy_versions.scope_key` 已成为非空生成键，排他键使用 `COALESCE(tenant_id,0)` 与 `scope_key`（第 723、732 行）。
- 未再检出带 `SELECT` 的 CHECK。

### 3.2 仍阻断项

1. **enum 物理命名与总规则不一致。** 例如：
   - `product_skus.compliance_status` 实际为 `enum_skus_compliance`，规则要求 `enum_product_skus_compliance_status`；
   - `roi_feedback_events.feedback_type` 实际为 `enum_feedback_type`，规则要求 `enum_roi_feedback_events_feedback_type`；
   - `policy_versions.policy_type` 实际为 `enum_policy_type`，规则要求 `enum_policy_versions_policy_type`。
   共 59 处。DSH 需二选一冻结：逐字段改为规则名；或把规则改为“显式注册表允许复用”，并列出所有 `CREATE TYPE` 的物理名、值集和复用表字段。当前文字尚未确定迁移创建顺序与复用边界。
2. **4 处 `NULLS NOT DISTINCT` 仍是概念位置，不是已声明的正式语法。** 位于第 366、392、605、731 行。应改为 `UNIQUE NULLS NOT DISTINCT (...)`，或明确写成对应 `CREATE UNIQUE INDEX ... NULLS NOT DISTINCT`。
3. **feedback 映射仍是中文伪 CHECK。** 第 634 行只有五组值对说明，没有可执行布尔表达式/约束名，和 v4 第 32 行“不再出现伪 CHECK”的总规则冲突。
4. **7 个 trigger 目前只完成命名，尚未形成 DDL 契约。** round-11 第四节将 SQL 实现推迟到 P0-1，但本轮门槛要求 v4 可确定性生成。至少需冻结每个 trigger 的表、`INSERT/UPDATE OF` 字段、`BEFORE/AFTER`、是否 `CONSTRAINT ... DEFERRABLE`、校验查询所需键、统一错误码；函数体可在 P0-1 编写。

### 3.3 指定表抽检

| 表 | 结论 | 依据 |
|---|---|---|
| `product_skus` | 未通过 | `attributes_hash` 已闭合；但组合 FK 指向的 `products(tenant_id,id)` 没有父唯一键，且两个 enum 名不符合总规则 |
| `policy_versions` | 未通过 | `scope_key`/排他方向成立；但 `UNIQUE ... NULLS NOT DISTINCT` 位置错误、缺 `UNIQUE(tenant_id,id)`，并存在 global policy 与组合 FK 的可引用冲突 |
| `roi_feedback_events` | 未通过 | `subject_key` 类型成立；但映射 CHECK 仍为描述文本，多个 tenant-owned FK 未组合化，enum 名不符合总规则 |
| `pricing_decisions` | 未通过 | 排他约束方向成立；但 `shop_id` 未组合化，policy/cost/listing 组合 FK 的父唯一键缺失，`bid_rounded_cents` 未成为实体列 |
| `ad_report_snapshots` | 未通过 | canonical key 成立；但 NULL 唯一语法位置错误，account/shop/listing/product 等关系未组合化，事实维度一致性未被 trigger 覆盖 |

## 四、阻断包 2：tenant 组合 FK 契约

### 4.1 父表目标不成立

v4 第 30 行规定“所有父表统一带 `UNIQUE(tenant_id,id)`”，round-11 也声明 16 个父表已补齐；实际字段表只在 `platform_accounts`、`shops` 出现该约束。

现有组合 FK 还会引用以下缺少父唯一键的表：

`suppliers`、`products`、`product_skus`、`assets`、`asset_product_bindings`、`asset_shop_bindings`、`cost_snapshots`、`shop_listings`、`shop_listing_skus`、`ad_campaigns`、`ad_report_snapshots`、`alert_events`、`policy_versions`、`workflow_runs`。

另外，补齐当前遗漏关系后，`supplier_offers` 也会成为组合 FK 父表，也需 `UNIQUE(tenant_id,id)`。

### 4.2 25 个单列 FK 缺组合约束

按表归并如下：

- `shops.cid_policy_version_id`；
- `cost_snapshots.offer_id/policy_version_id`；
- `selection_decisions.source_account_id/cost_snapshot_id/policy_version_id/workflow_run_id`；
- `assets.derived_from_asset_id`；
- `shop_listings.account_id`；
- `pricing_decisions.shop_id`；
- `ad_campaigns.budget_policy_version_id/cid_policy_version_id`；
- `ad_report_snapshots.account_id/shop_id/shop_listing_id/product_id`；
- `roi_feedback_events.account_id/shop_id/shop_listing_id/shop_listing_sku_id/product_id/campaign_id/asset_binding_id`；
- `manual_tasks.policy_version_id`；
- `policy_versions.supersedes_id`。

自引用也需保证 tenant 一致；polymorphic `decision_object_id/ref_id/scope_ref_id` 可继续使用已冻结的显式 trigger/应用契约，但必须逐字段列明，不与普通 FK 混写。

### 4.3 global policy 引用冲突

`policy_versions.tenant_id` 允许 NULL 作为系统模板，但 `pricing_decisions` 等租户行按 `(tenant_id, policy_version_id)` 组合引用时，系统模板的 `(NULL,id)` 不会匹配租户的 `(tenant_id,id)`。DSH 需冻结一种可生成模型：

- 生效前把 global 模板物化为 tenant-owned policy version；或
- 对 policy 引用使用命名 constraint trigger，语义明确为“同 tenant 或 global”，普通 tenant-owned 父表仍使用组合 FK。

当前“一律组合 FK”与“global policy 可直接引用”两项声明不可同时成立。

### 4.4 跨父实体 trigger 覆盖不足

现有 7 个命名覆盖 offer、素材绑定、listing、campaign 等主要路径，但尚未覆盖：

- `pricing_decisions.shop_id/listing/listing_sku` 的同一上下文；
- `cost_snapshots.decision_object/shop/listing/offer` 的上下文；
- `ad_report_snapshots` 的 account/shop/listing/SKU/product/campaign/asset 事实维度；
- `roi_feedback_events` 与 `source_snapshot_id` 及冗余维度的一致性。

同 tenant 只证明租户归属，不证明这些维度来自同一个商品、店铺或活动。

## 五、阻断包 3：CID 原件复算与精度

### 5.1 公式复算通过

读取 `cid盈亏表` 第 2 行：

```text
G=1.3, H=1.8, I=1.5393, J=0.13194, K=21.99, L=0.83562, U=0.5
roi_buffer=0.1, consumption_rebate_rate=0.05, tech_hi=0.036, tech_lo=0.055
```

按 v4 公式以高精度 decimal 计算：

| 项 | 高精度结果 | 6 位小数 |
|---|---:|---:|
| M | 16.38314 | 16.383140 |
| N | 1.342233540090605... | 1.342234 |
| O | 1.442233540090605... | 1.442234 |
| P | 15.247183891326313... | 15.247184 |
| Q | 0.762359194566316... | 0.762359 |
| R | -0.41781 | -0.417810 |
| S | 2.316125303240003... | 2.316125 |
| T | 0.151905120299466... | 0.151905 |
| V | 30.494367782652626... | 30.494368 |
| X | 0.721116770045303... | 0.721117 |

这些值与 Excel 原件一致，Q/R/S/T 的业务语义也一致。

### 5.2 输入持久化仍会改变原件结果

v4 第 793-798 行把 K/J/I/H/G/L 全部声明为 `bigint 分`，`cost_snapshots.platform_fee/refund_reserve/tax` 也仍是 bigint。原件第 2 行换算成分后：

```text
J=13.194 分，I=153.930 分，L=83.562 分
```

三项都不是整数分。若在入库时按分四舍五入为 J=13、I=154、L=84，M 将从 `16.38314` 变为 `16.38`，P 将从 `15.247183891...` 变为 `15.244464195...`，T 将从 `0.151905120...` 变为 `0.152183047...`。因此“输入 bigint 分 + 中间 numeric”仍不足以重现原件。

最小修订：CID 计算快照中的 K/J/I/H/G/L 使用 `numeric(18,6)` 分，或保存客单/成本原值与费率并在高精度上下文中派生 J/I/L；业务结算字段可另存 `*_rounded_cents bigint`。

### 5.3 比率 scale 与取整顺序仍需冻结

若先把 N/O 写入 `numeric(12,6)` 再以 O 计算 P，P 的 6 位结果会变成 `15.247179`，而原件按全精度链为 `15.247184`。v4 虽写“全链不逐步取整”，但物理类型会在赋值时量化。

需明确：公式引擎使用统一高精度 decimal 上下文一次性算完 M~X，再分别量化持久化；后续项不得读取已经量化为 6 位的中间投影。也可把 N/O 等内部值提高到足够 scale。

### 5.4 平台 round 值尚未实体化

v4 第 819 行称 `bid_rounded_cents bigint` 存入 `pricing_decisions.cid_results`，但 `pricing_decisions` 字段表只有 `cid_results jsonb`，没有实体 `bid_rounded_cents bigint` 列。若坚持 JSON，需给出可验证 JSON schema/生成列；按当前 DDL 契约更直接的做法是增加实体列，并保留未取整 P/V 与 rounding mode。

## 六、阻断包 4：feedback subject 与 14/15 同步

### 6.1 已通过项

- `subject_key varchar(128) NOT NULL` 可以保存 `category_id varchar(64)`，原 bigint 冲突已消除。
- 五组 feedback_type↔subject_type 映射集合完整。
- 第二唯一键不再依赖 nullable 的多主体列。
- `14-新立项最终方案.md` 已同步 actor_registry、31 表、CID 精度说明，以及 status/health_state 两条正交轴。

### 6.2 仍阻断项

1. 第 634 行映射仍是描述文本，需落成可执行、具名 CHECK，例如对 `(feedback_type, subject_type)` 的五组允许值做布尔约束。
2. `subject_key` 只解释 product/shop/SKU/category，没有冻结 `material` 的稳定键来源。建议明确 `material = assets.public_id` 的字符串形式及 UUID 规范化格式。
3. `roi_feedback_events` 除 `source_snapshot_id` 外的 7 个 tenant-owned FK 仍是单列关系；并且没有约束冗余维度必须与 source snapshot 一致。
4. 因本轮终验未通过，`14-新立项最终方案.md` 第 370 行“正式字段级数据字典已定稿”应暂改为“v4 候选，待终验回修”，避免状态文字先于冻结结论。

## 七、交给 DSH 的最小回修清单

请 round-13 只处理以下四项，不扩表、不拆任务：

1. 冻结 enum 注册表/命名规则，修正 4 处 NULLS NOT DISTINCT 语法，把 feedback CHECK 与 7+ 个 trigger 的事件/时机/错误语义写成可生成契约。
2. 为所有组合 FK 父表补 `UNIQUE(tenant_id,id)`；补齐 25 个普通 tenant-owned 单列 FK；单独裁决 global policy 的引用模型；补齐 report/feedback/pricing/cost 的跨维度一致性。
3. 把 CID 输入小数分与公式引擎内部精度写实：高精度一次计算、末端量化；增加实体平台 round 字段或等价可验证生成列。
4. 把 feedback material 稳定键、具名映射 CHECK、source snapshot 维度一致性写实，并把 14 号文档冻结状态改回候选态。

完成后请 DSH 自检以下硬指标再换手：

- 31 表不变，reciprocal FK=0；
- 每条组合 FK 都能找到父 `UNIQUE(tenant_id,id)`；
- 普通 tenant-owned 单列 FK 缺口=0（明确登记的 polymorphic/global exception 除外）；
- enum 字段全部能映射到唯一的 `CREATE TYPE` 注册项；
- 伪 CHECK=0，4 处 NULLS NOT DISTINCT 使用正式位置；
- Excel 第 2 行从已持久化 CID 输入可复算到上述结果，不依赖丢失的小数分；
- `material_score` 的 subject_key 来源明确。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-12-->
