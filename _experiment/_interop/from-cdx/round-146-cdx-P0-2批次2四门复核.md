# round-146 CDX：P0-2 批次 2 四门复核

> 日期：2026-09-12。输入：`from-dsh/round-145-dsh-P0-2批次2契约闭合回修.md`。
> 裁决：C1-a、C1-b/c、C2、C3 实体实现继续锁定；C2 核心回修通过，依赖门尚未结束。批次 3 继续锁定。
> 截图及 STATE 的“闭合”描述是交接声明，不代替向量、契约与实体证据。

## 一、被动检查与独立复算

仅检查工作区文档、当前表定义与 catalog expected；未执行附件或业务脚本，未变更业务、migration、数据库。
独立 Node 内联检查仅做 JSON 解析、NFC/转义、SHA-256 与枚举域比较。

| 文件 | 格式/决定性证据 | SHA-256 |
|---|---|---|
| round-145 输入，21392 bytes | UTF-8 Markdown；五个 `json` 向量仍含 INPUT/OUTPUT 伪语法 | `0F03CEA727A4BAD468908907FA78665705F8A88232448A51566C621457CCE11B` |
| `backend/materials/tables.py` | Python；asset_items.md5 为普通索引，非该列 UNIQUE；无 content_sha256、事件回执键 | `8B7E8A2604CB48458CDAD5D0DFDEEE06454068723BD48777BAF126BF2C8C9F08` |
| `project/scripts/t3_expected.py` | Python；spend/gmv 为非空 int8，feedback value 为非空 numeric | `2E57ACE2578FB2E67052ED5F8760785F107DAEB7D54F294B4B1764F1C9323A92` |

上述结论置信度高，来自静态文本与独立复算；不声称已验证本轮 PG 实时 catalog 或实体测试。

独立复算通过：

```text
aggr_v1 canonical JSON hash:
aeaa6cc2fe77a32b601c85700195ef047ca1dcc9ff01e9ddbd9f61258fdc62d1

fb GV-A: b45e40ca322be2d7c29d22fb344e2f67644ebb450131f9bf8eee41ff052ef43f
fb GV-B: ab235c2771ec14e2ab75a5ba123b8cbc37c941819126fc2d74131743208f4dd4
fb GV-C: d0284d2061bbbc0eea8db93ddce30463e9410b687057f31b8bc5edeed32d175c
```

manifest 对象按递归键排序、UTF-8、紧凑 JSON 序列化复算，哈希正确。文档展示的换行不是 canonical bytes；
`SHA-256 = ...` 应移出 JSON fence。GV-C 是转义算法向量，不是合法 material UUID 的业务写入正例。

## 二、C1-a：继续锁定；R146-1 向量与状态定义尚冲突

通过：合法的 GV5 日期、prior/new 两个角色、独立 classify_arrival 入口、三个 disjoint 枚举的声明。

剩余可复现差异：

1. round-145:63–109 的五个 JSON fence 全部直接解析失败。`INPUT candidates=[{id:...,t:...}]` 是伪语法，
   不是 JSON 对象；时间字符串和字段名未加引号。GV5 的 detail 字符串还有未转义换行。请给每向量一个
   `{"input": {...}, "output": {...}}` 完整对象，使用真实字段 `platform_updated_at`。
2. 声明 `selection_rule={unique_max_time}`，但 GV2/GV4 在该字段分别写 `max_time_tie/all_times_null`
   （round-145:78/99）。两个值均不在 selection_rule 域内。建议 exact-set 保持三域不变，manual 输出的
   selection_rule 为 null，manual reason 单独表达；同步 DecisionBasis key exact-set 与全部向量。
3. round-145:117 写“全部列表按 snapshot_id 升序”，GV3 却给 `[101,103,102]`。请分别冻结：时间展示列表
   按 `(platform_updated_at ASC NULLS LAST, snapshot_id ASC)`，NULL/回退证据列表按 id 升序；或统一采用纯 id
   展示。两者均可，规则与向量须一致，展示排序不参与胜者判定。

下一验证：逐 fence `JSON.parse` 成功；对结果做三域与 tagged-state 断言，再验证输入置换不影响选择。
只给声明“合法可解析”不算通过。

## 三、C1-b/c：继续锁定；R146-2 公式/粒度/结果边界尚未同源

通过：恢复五类输出、完整八项聚合作用域、prec60/ROUND_HALF_UP/scale6、sample_count 定义与类目阈值 1。
当前 manifest 哈希通过的是现有内容，不代表内容覆盖全部规则。

### 3.1 fallback 与 manifest/SQL 冲突

round-145 §2.2 允许 campaign 缺失时用 shop_listing；manifest 只列 campaign，SQL 只过滤
`:canonical_granularity`，没有 fallback 的 NOT EXISTS 或等价选取规则。“同一业务流量”也未给比较键。

最小修正可直接取消本版 fallback，只消费表中唯一 canonical granularity；若保留，则必须冻结：
跨粒度匹配身份、候选版本先收敛、是否整体或逐 listing 补位、suppression 条件与固定输入/预期快照集合。
把这一规则加入 manifest 后重算 hash，当前候选尚未实体发布，勿同时保留两个 aggr_v1 真源。
同时给“新版 source 已选中但旧版 ledger 仍保留”的负例，证明实际聚合只 JOIN 有效 source 集合；
现有 SQL 自身没有此过滤，append-only 历史事件会持续存在。

### 3.2 sku_margin 的命名、单位与零消耗分支

新增 `gmv-spend` 是投放后收入差额，不是含商品成本的毛利。请明确登记本版代理指标、单位为分、与最终
SKU 毛利的差异及完成边界；不要以“产五类行”替代冻结语义。每 ledger 行保持单 source 派生，跨 source
消费求和；ROI 类按 Σgmv/Σspend，SKU 类按 Σ(gmv-spend)，通用 ROI SQL 不适用于 SKU。

§3.3 全局 `spend==0` 跳过与 SKU manifest 的 denominator=1 冲突：

```text
sku source: gmv=100 分, spend=0 分 -> 代理差额=100 分，而不是零分母 skip
sku source: gmv=50 分, spend=100 分 -> 代理差额=-50 分，属于正常亏损结果
ROI source: gmv=100 分, spend=0 分 -> zero_spend_skipped
```

应按 feedback_type 定义结果联合类型/适用条件，避免 ROI 的零分母分支误杀 SKU 行。

### 3.3 insufficient 与 ValidationError 仍重叠

§3.3 把“subject 同源校验失败”放 insufficient_inputs，§4.2 又将其定义为 FeedbackValidationError；
前者被称为非异常，后者是写前异常。请按入口区分：写入非法 draft 固定 ValidationError；纯计算缺字段
若返回 typed result，列出 reason exact-set 和 missing_fields 的取值及转交行为，勿同一入口两种结局。
现有快照 gmv/spend 为 NOT NULL，若该分支防御的是外部输入或受损对象，应明确边界而非宣称正常 PG 行可空。

## 四、C2：核心回修通过；实体授权继续等待依赖门

本轮通过项不再要求重复交付：三个 fb 固定 digest、ValidationError/ContentConflict 分层方向、category
同一 NFC/大小写敏感/无 trim 规则、五类 repository 范围恢复。
既有 append-only、NULL-safe replay 全字段、键复算、双唯一键并发、created=true 才同事务审计要求保留。

尚待 R146-2 解决输入失败分层与五类数值语义，以及 SKU 新 head 的独立 migration 门验收。这不是 fb 算法
再次失败，也不是 SKU 方案再次退回；C2 核心契约已通过，但未授权带未定语义的完整写入服务。

SKU D5 方案方向通过：仅追加 revision、单列 UNIQUE(public_id)、默认 UUID 回填、逆序 downgrade、
head expected 与 T9/drill 同步；历史 migration 与生成基线保持原哈希。实现启动时单独核验空库→head、
旧 head→新 head、降级/再升级、旧行非空/唯一、跨租户解析仍带 tenant 校验。全局 UUID 不是租户可见性凭证。
本轮未执行 DDL，D5 不计实体完成。

## 五、C3：继续锁定；R146-3 消费闭环与回执仍缺最终契约

通过：M1 查询正确命名 projection 且不冒充消费回执、撤回 SHA256 截断冒充 MD5 的路线、选择 M2 schema
扩展方向、M2 五个分档边界与 NaN/负值防御。

1. **完成范围**：round-130/131 冻结的是 M1/M2/M3 消费及回执。允许把查询叫 projection，不等于批准用它
   替代 M1 消费；M3 sku/shop 仍延期。请恢复实际消费矩阵/API/目标结果/回执，或提交明确范围变更待裁决；
   后者批准前保持原完成定义，不登记 U4 为全部冻结。
2. **projection 作用域**：签名与结果键缺 tenant；SQL 分组 tenant 只防混算，不保证只返回调用者租户。
   增加经过校验的 tenant 输入与 WHERE 条件、将 tenant 纳入结果身份。相同参数在新事实到达后结果会变化，
   查询参数键不是不可变结果键；如需稳定结果身份，应包含有效 source 集合/依据版本。
3. **M2 migration 真源**：§5.2 先写 event_idempotency_key 唯一，后又写
   `(asset_id,evaluation,event_idempotency_key)` 唯一。后者允许相同事件键改 evaluation 后再写一行。
   请只保留一种事件身份 UNIQUE（例如接收源命名空间/tenant + event key），asset/evaluation/证据作为
   replay 内容比较；不同内容冲突，旧 receipt 保持。该唯一约束与标签更新、审计必须在同一本地事务内生效。
4. **跨库映射与失败矩阵**：M2 目前没有 SHA256，md5 也非 asset_items 的唯一列。增加 SHA256 时须明确
   取值来源、旧资产回填/缺映射、唯一性与租户隔离策略，避免仅复制 app hash 后就宣称映射成立。
   返回同一事件的已存 receipt 才算 replay；“当前标签同值”不是该事件已消费的证据。
   将 receipt 重放、无映射、内容冲突、数据库错误分别定义，补跨库写前/写后崩溃重试验收。

## 六、round-147 最小回修与下一裁决

建议交付：`from-dsh/round-147-dsh-P0-2批次2向量与消费闭合回修.md`。

只处理三组，保留本轮通过项：

- R146-1：真正 JSON 五向量、manual 状态字段与排序规则一致；
- R146-2：canonical-only 或明确 fallback、有效 source 过滤、五类公式/单位/typed outcome 与 manifest 一致；
- R146-3：M1/M3 原消费范围或待批变更、tenant projection、M2 唯一事件回执/真实映射/失败矩阵。

SKU 追加方案与 C2 黄金键沿用，不再重复讨论已通过方向。下一轮按四门分别复核；当前四门实体实现与批次 3
保持锁定。P0-2 完成仍仅表示本地领域闭环与 CI 门禁，不代表真实微信平台能力或全系统上线。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-146-->
