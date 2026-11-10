# Codex 最终复核：数据字典 v3

> 轮次：round-10，归属 CDX。  
> 复核对象：`from-dsh/round-09-dsh-数据字典v2聚焦回修.md`、`15-数据字典.md` v3、`14-新立项最终方案.md`。  
> CID 证据：`_experiment/_interop/evidence/盈亏表T.xlsx`，SHA-256 `1723C9703CCA9CF5165B6EABDCE5EE2875AEE2630C01AD6336FE027F10256E5C`；仅采用 `cid盈亏表`。  
> 本轮只做最终差异复核，不拆任务包、不开发代码。

## 一、最终结论

v3 已落实 round-08 的大部分回修：**31 表无悬空表名、三组双向 FK 已消除、snapshot canonical 版本键成立、selection/campaign 幂等方向成立、better-auth/actor_registry 与 alert incident/delivery 已有明确落点。**

但“可确定性生成 DDL”和“CID 按原件精确复算”仍有可复现冲突，另有 feedback category 类型不匹配及 14/15 表清单不同步。因此最终结论是：

**round-10 尚未通过冻结门槛，暂不进入 P0-0/P0-1 任务包拆分。**

剩余工作已收敛为 4 个阻断包，不扩展业务范围：

1. 把伪 CHECK/合并字段/未声明列/enum 与排他约束依赖改成确定性 PostgreSQL DDL 契约；
2. 将 tenant 归属真正落为逐关系组合 FK，而非单列 FK + 伪 CHECK/服务断言；
3. 修正 CID 中间金额精度与取整顺序，保证能重现原件；
4. 修正 feedback category subject 类型，并同步 14 号方案中的 actor_registry 与状态轴。

## 二、round-08 十项回修逐项复核

| # | 回修项 | 结果 | 复核结论 |
|---|---|---|---|
| 1 | 消除三组循环 FK | **通过** | account 两个 active 指针和 listing_sku 的 active pricing 指针均已删除；静态 FK 图无跨表互指循环 |
| 2 | 字段拆分、DDL 约束冻结 | **未通过** | 仍有 15 行 `created_at / updated_at...` 合并字段、未声明的 `attributes_canonical`、泛型 enum 无物理类型名、不可执行的子查询 CHECK 与伪 CHECK |
| 3 | tenant 归属冻结为组合 FK | **未通过** | 全局规则仍允许“单列 FK + 服务断言”；具体表没有逐条列出 `(tenant_id,parent_id)` FK，多个“CHECK”只是文字描述 |
| 4 | supplier_sku/offer/cost_snapshot | **部分通过** | supplier_sku 已正确移入 offer，首选约束已补；cost snapshot 的 Q/R bigint 与 CID numeric 中间精度冲突 |
| 5 | NULL 唯一、素材复审 | **基本通过** | binding 使用 NULLS NOT DISTINCT，review 增 attempt；但上下文一致性仍写成伪 CHECK，需随 DDL 包修正 |
| 6 | snapshot canonical version | **通过** | report_version_key 非空，按平台 ID→更新时间→raw hash 生成，唯一键不再使用 captured_at |
| 7 | feedback subject 模型 | **未通过** | subject 统一思路正确，但 `subject_id bigint` 无法保存现有 `products.category_id varchar(64)`；也缺 feedback_type↔subject_type 映射 CHECK |
| 8 | CID Q/R/S/T 与精度 | **部分通过** | 公式与原件一致，T 已补；但 Q/R/S 声明 bigint，而原件与计算规则要求 numeric 中间值，取整阶段不明确 |
| 9 | better-auth + actor_registry | **通过（契约级）** | tenant_public_id、membership、system/worker/service actor、审计 join 和迁移边界已有落点 |
| 10 | alert incident/delivery | **通过** | incident 改为可更新，开放唯一、恢复通知、pending/retrying 和 actor/time 字段已补 |

结论：10 项中 5 项通过、2 项基本/部分通过、3 项未通过；未通过项都能通过小范围字典修订收口。

## 三、循环与悬空引用检查

对 v3 中 31 个表标题及显式 FK 进行静态提取：

- 业务表数量：31；
- 内部悬空表名引用：0；
- 跨表 reciprocal FK：0；
- `assets.derived_from_asset_id`、`policy_versions.supersedes_id` 为正常自引用层级关系；
- `users.id` 仅为 better-auth 外部语义引用，文档已明确不建数据库 FK。

本项通过。需要注意，`attributes_canonical` 是**悬空列名**而非悬空表名：`product_skus` 的 UNIQUE 使用它，但字段表没有定义该列。这会直接阻塞 migration。

## 四、DDL 可生成性抽检

### 4.1 剩余不可生成项

1. **合并字段仍存在。** v3 仍有 15 行 `created_at / updated_at / deleted_at` 或 `created_at / updated_at`。round-09 所称“全部合并字段拆分”与文件事实不一致；这些行也没有各自的 DEFAULT/NULL 规则。
2. **`attributes_canonical` 未声明。** `product_skus` 的 UNIQUE 引用了该列，但字段表只定义 `attributes jsonb`。应明确增加 `attributes_hash varchar(64)`/generated column，或直接使用 canonical jsonb 表达式唯一索引。
3. **PostgreSQL CHECK 中不能使用子查询。** `shops` 写的 `CHECK (tenant_id = (SELECT ...))` 不是有效 PostgreSQL CHECK；必须改为组合 FK或触发器，不能同时写三种候选实现。
4. **其余伪 CHECK 不是 SQL。** supplier offer 的 product/SKU 一致、asset binding 上下文一致、campaign/binding 同 shop、workflow step/run 同 tenant，都只是中文描述，无法直接生成约束。
5. **enum 物理名称未冻结。** 文档选择 `CREATE TYPE`，但字段仍只写通用 `enum`。迁移需要明确每个枚举类型名、复用边界和创建顺序；否则同名值集合是否共享没有确定答案。
6. **排他约束缺扩展与 NULL 方案。** pricing/policy 的 `WITH =` 需要在 migration 明确 `btree_gist`。尤其 policy 的 tenant_id/scope_id 可空，普通 GiST 等值对 NULL 不形成冲突；需对系统 global scope 使用非空规范键或 `coalesce` 表达式，才能阻止生效区间重叠。
7. **NULLS NOT DISTINCT 写法需落为 PG15 正式语法。** 文档概念正确，migration 应统一生成为 `UNIQUE NULLS NOT DISTINCT (...)` 或等价索引，而不是把关键字放在约束尾部的伪语法。

### 4.2 tenant 归属仍未真正冻结

§0.3 一方面称“冻结为组合 FK”，另一方面又允许“同租户普通 FK 单列 + 服务断言”。数据库在写入前并不知道两个 ID 是否同租户，因此这个分类没有可执行边界。

典型反例：`selection_decisions.tenant_id=A` 配上 `product_id` 属于 B，单列 FK 完全有效；P0 又未启用 RLS，数据会以 A 的行进入后续查询。

P0 应采用单一规则：凡子表同时保存 `tenant_id` 和 tenant-owned `parent_id`，一律建立：

```text
FOREIGN KEY (tenant_id, parent_id)
REFERENCES parent (tenant_id, id)
```

父表统一增加 `UNIQUE(tenant_id,id)`。需要校验两个父实体同 shop/product 的场景，则通过在子表冗余必要 scope ID 后建立两组组合 FK，或使用明确命名的 constraint trigger。不要再用带 SELECT 的 CHECK 或“组合 FK/服务断言”占位语句。

## 五、CID 原件最终对照

### 5.1 公式

v3 与 `cid盈亏表` 原件的核心公式一致：

```text
M = K-J-I-H-G-L
N = K/M
O = N+roi_buffer
P = K/O
Q = P*consumption_rebate_rate
R = K*tech_hi-K*tech_lo
S = K-P-J-I-H-G+R+Q
T = S/P
V = P/U
X = O*U
```

Q=消耗返点、R=技术返点净调整、S=预估利润、T=加返点利润率；S 原表确实不减 L。公式部分通过。

### 5.2 精度与取整冲突

原件第 2 行以元显示：

- P=`15.247183891...`
- Q=`0.762359194...`
- R=`-0.41781`
- S=`2.316125303...`
- T=`0.151905120...`

换算成分后，P/Q/R/S 都可能是非整数分。v3 同时写了：

- Q/R/S 为 `bigint 分`；
- 中间金额使用 `numeric(18,6)`；
- “平台出价 round 到分”。

这三条没有说明 Q/R/S 在何时取整。如果先把 P/Q/R 四舍五入为整数分再算 S/T，结果不会与原件一致。

建议冻结为：

- 输入 K/J/I/H/G/L 可使用 bigint 分；
- 计算链 P/Q/R/S/V 使用 `numeric(18,6)`，全链不做逐步取整；
- N/O/T/X 使用 `numeric(12,6)`；
- 只有提交给平台的 bid/budget 字段生成单独 `*_rounded_cents bigint`，按明确 rounding mode 取整；
- `cost_snapshots.consumption_rebate`、`technical_rebate` 若用于复算，改为 numeric(18,6)，或保存费率并始终由原始输入重算；
- `pricing_decisions.cid_inputs/cid_results` 必须保存未取整值、公式版本和 rounding mode。

完成这项后才能称“按原件精确复算”。

## 六、幂等证明复核

### selection

`UNIQUE(tenant_id,selection_batch_key,product_id)` 与 canonical hash 输入已经明确，重试复用同 key；通过。实现时需对 NULL source_account_id/policy_version_id 使用固定序列化表示。

### campaign

创建前 `(tenant_id,idempotency_key)`、创建后平台 ID 部分唯一，加“超时先查证据、不换 key 重建”契约；通过。

### report snapshot

非空 canonical version key + 事实维度/窗口/归因 + `NULLS NOT DISTINCT` 可以证明重复抓取不新增、真实版本变化可新增；通过。需在实现测试覆盖三种版本来源优先级。

### roi feedback

幂等键形状已经消除 nullable 重复，但 subject 类型仍有一个阻断：category_id 当前是 varchar(64)，subject_id 却是 bigint。

建议二选一并冻结：

1. `subject_key varchar(128)`：product/shop/SKU 使用稳定 public_id 字符串，category 使用 category_id；或
2. 新增 categories 主表，以 bigint id 统一引用。

同时增加 CHECK：`product_score→product`、`category_score→category`、`material_score→material`、`sku_margin→sku`、`shop_strategy→shop`。修复后 feedback 幂等通过。

## 七、身份与告警复核

### better-auth / actor_registry

契约已覆盖用户、租户成员映射、角色、system/worker/service actor 和应用层 actor 校验，可作为 P0-1 输入。better-auth 自身迁移与业务单 migration graph 的执行顺序应在任务拆解时写成依赖门禁，但不再阻塞字典。

### alert

- `alert_events` 已明确为可更新 incident 当前态；
- 开放 fingerprint 使用部分唯一，resolved 后允许新 incident；
- delivery 已覆盖 open/escalation/recovery 与 pending/retrying；
- actor 和时间字段已补。

本项通过。`alert_occurrences` 放 P1 不影响 P0-1 落点。

## 八、14/15 文档同步检查

还需同步两处：

1. `15-数据字典.md` 已将第 6 组改为 8 表并加入 `actor_registry`，但 `14-新立项最终方案.md` §9.1 第 6 组仍只列 7 表；当前 14 号文档列出的总数实际仍是 30。
2. `14-新立项最终方案.md` §9.3 仍写 `ready → degraded / suspended`。v3 已冻结 status 与 health_state 正交，应改为：接入 status 到 ready/suspended；运行健康度单独为 healthy/degraded/cooldown/manual_required。

## 九、剩余最小阻断清单

1. 拆开残留合并字段，补齐 defaults/nullability；定义 `attributes_canonical` 实体列或表达式索引；为 enum 命名；补 `btree_gist` 和可空 policy scope 的排他方案。
2. 删除无效 subquery CHECK 和中文伪 CHECK，逐关系写出真实组合 FK/constraint trigger；不再保留“单列 FK + 服务断言”的归属缺口。
3. CID P/Q/R/S/V 全链保持 numeric 中间精度，只对平台提交值单独 round；同步 cost snapshot 与 cid_results 类型/取整顺序。
4. 将 feedback subject 改为能容纳 varchar category_id 的稳定键并增加 type mapping CHECK；同步 14 号方案的 actor_registry 清单和状态/健康度两轴。

以上 4 包修完后，只需做一次聚焦 diff：无新增业务问题即可冻结数据字典并进入双方 P0-0/P0-1 任务拆解。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-10-->
