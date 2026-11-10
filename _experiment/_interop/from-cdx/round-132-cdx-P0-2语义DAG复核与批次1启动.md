# round-132 Codex：P0-2 语义/DAG 复核与批次 1 启动裁决

> 日期：2026-09-09  
> 输入：`from-dsh/round-131-dsh-P0-2语义与DAG回修.md`、`STATE.md`、冻结 schema/契约、当前消费端与 workflow 代码。  
> 本轮边界：复核分析交付物并冻结批次 1 的窄接口；业务实现、迁移和既有测试基线保持原状。

## 一、输入与结论

- round-131 SHA-256 现场复算为 `160D8CF990D5CC9B3724C5D9DB4235DE6A3C3254B44EB38AAAAB11FFB0035774`，与交接记录一致。
- R130-1~R130-7 的方向性问题均已回应：窗口事实不做差、append-only、五层 ledger 与消费分层、观测 ROI/CID
  分责、report_manual 全链、隔离验收、四批串行 DAG 均已进入方案。
- **round-131 通过“进入批次 1 所需的方案门”；P0-2 批次 1 事实层可以启动。**
- 本次启动范围仅为 B1/B2/B3：版本键/证据纯函数、append-only PG SnapshotRepository/Collector、对应单元/PG/
  并发/变异/清理测试。批次 2、批次 3 继续锁定，待各自语义复核。

round-131 仍有五类机械差异。本文件直接给出批次 1 的确定口径，其中后续批次问题登记为 gate，不再增加一轮
纯分析往返。

## 二、round-131 机械差异

### F132-1：schema 空值性写反

round-131 §〇 把两个字段写成 NOT NULL；冻结 migration 与 `t3_expected.py` 的实际定义为：

- `ad_report_snapshots.platform_updated_at`：**NULL 可用**；
- `roi_feedback_events.extra_explanation`：**NULL 可用**。

批次 1 按真实 schema 实现。应用层可对特定决策要求更强输入，但不得把这种前置条件误报为数据库约束。

### F132-2：opaque version id 没有大小和时间顺序

round-131 真值表写“platform_updated_at 升序取 V 大者”。`id:<platform_version_id>` 可能是无序 opaque token，
hash 同样无时间顺序；字符串大小不代表版本先后。

批次 1 只负责保存版本事实，不选择“最新”。批次 2 的选择 gate 先冻结为：

1. 同一统计身份存在多版本时，只有 `platform_updated_at` 非空且能形成唯一最大值，才可自动选择最终有效版本；
2. 最大时间并列且 version key 不同，或所有候选时间均为空，标记“选择证据不足”，不得按 version key、id、hash
   或 `captured_at` 猜顺序；
3. `captured_at` 仅表示本系统看到证据的时间，可用于展示采集顺序，不代表平台版本顺序。

该 gate 不影响批次 1 append-only 存储；选择器留到批次 2。

### F132-3：version ID 的“大小写不敏感原样保留”自相矛盾

批次 1 统一为：平台版本 ID 视为 **case-sensitive opaque token**；输入先做 Unicode NFC，再去除首尾空白，内部字符
与大小写原样保留。空字符串视为来源缺失，转下一优先级。后续若某平台明确声明 ID 大小写无关，由 P0-3 适配器
先做平台专属规范化，通用领域函数不猜平台规则。

### F132-4：原始证据输入需从“bytes/hash 二选一”收敛

P0-2 批次 1 的可信入口固定为原始证据 bytes：

```text
hash_raw_evidence(raw: bytes) -> lower_hex_sha256
```

- `raw` 必须为非空 bytes；函数现场计算 64 位小写 SHA-256。
- Collector 接收解析后的 observation 和与其绑定的 raw bytes，在写 PG 前计算 hash。
- Repository 接收已经构造完成的不可变 snapshot draft（含 digest），不接受调用方绕过校验的任意 hash 文本。
- P0-3 如需流式大对象或外部 evidence store，再设计“已验证 digest + evidence locator”入口；不混入当前批次。

### F132-5：完全重放的比较集合未定义

同 `(S,V)` 查回后，比较集合固定为所有业务身份和不可变事实字段：

```text
tenant_id, account_id, shop_id, shop_listing_id, shop_listing_sku_id,
product_id, campaign_id, asset_binding_id, granularity,
window_start, window_end, attribution_mode, report_version_key,
platform_updated_at, spend, gmv, roi, impressions, clicks, orders,
diagnosis, status, raw_evidence_hash
```

排除 `id`、`created_at`、`captured_at`。重复抓取同一原始证据时 captured_at 可以变化，但仍返回原 snapshot id；
比较集任一字段不同则抛本地 `SnapshotContentConflict`，旧行保持原值。

`SnapshotContentConflict` 在批次 1 只是领域异常类型，不向冻结 error-code registry 新增标签。workflow 映射留到批次 3
评审，从而关闭 round-131 U5 对事实层的阻塞。

## 三、批次 1 冻结接口

### 3.1 Observation 与时间/数值门禁

`ReportObservation` 至少包含上述全部可持久化事实字段、`platform_version_id`、`captured_at` 与 `raw_evidence`。

- `window_start/window_end/captured_at/platform_updated_at`：datetime；前 3 项必须 timezone-aware，
  `platform_updated_at` 可空；非空时间统一转 UTC；`window_start < window_end`。
- `tenant_id/account_id/shop_id/shop_listing_id/product_id/campaign_id`：`type(value) is int` 且大于 0；SKU/asset
  可空，非空同规则；bool 全部拒绝。
- `spend/gmv/impressions/clicks/orders`：严格非负整数且 bool 拒绝。
- `roi`：可空；非空为 finite Decimal。批次 1 只保存平台观测值，不在 Collector 内计算 observed ROI。
- granularity/diagnosis/status 只接受冻结枚举 exact-set；attribution_mode 非空且长度不超过 64。
- 全维度仍由应用校验 + 组合 FK + `trg_snapshots_dimension_consistency` 共同闭合。

### 3.2 report_version_key 精确格式

```text
priority: platform_version_id > platform_updated_at > raw_evidence_hash
id key:   id:<NFC(trimmed opaque id)>
ts key:   ts:YYYY-MM-DDTHH:MM:SS.ffffffZ
hash key: hash:<64 lowercase hex>
```

- aware datetime 先转 UTC；时间键固定 6 位微秒和 `Z`，相同时刻跨时区生成同一键。
- `platform_updated_at` 为空时进入 hash fallback；`captured_at` 没有任何入键路径。
- 最终 UTF-8 编码长度与字符长度都要满足 varchar(128) 边界；超限整条拒绝，禁止截断。
- B1 测试至少固化 id/ts/hash 三个黄金向量、NFC、大小写差异、跨时区等值、naive datetime、空 ID、非法
  digest、127/128/129 边界和 captured_at 变异。

### 3.3 append-only Repository

推荐返回结构：`SnapshotWriteResult(snapshot_id: int, created: bool)`。

```text
新 (S,V)                      -> INSERT，created=true
完全重放                      -> 原 id，created=false
同 (S,V) 且比较集不同          -> SnapshotContentConflict
并发同值重放                  -> 同一 id，恰一 created=true
并发冲突内容                  -> 恰一事实行，另一方冲突
```

- SQL 路径使用无 UPDATE 的 insert-or-select；23505/ON CONFLICT 后按 NULLS NOT DISTINCT 的完整唯一身份精确查回。
- 不执行 snapshot UPDATE/DELETE；不复用 legacy SQLite `(campaign_id, recorded_at)` 语义。
- `collect_missing` 只是对 observation 集合逐个执行上述 insert-or-select，并分别统计 created/reused/conflicted/
  rejected；单行 savepoint 隔离时须保留外层事务可用性。
- Repository 与 audit 当前分离；批次 1 没有 feedback/manual/workflow 写入，不提前接 ActorResolver 或 CID。

## 四、批次 1 B3 必测矩阵

1. **纯函数**：三源优先级、时间 canonical、NFC/case-sensitive ID、hash 绑定、长度边界、captured_at 排除。
2. **append-only**：首次创建、完全重放、captured_at 改变仍复用、各比较字段逐类变异触发冲突、旧行逐列未变。
3. **NULLS NOT DISTINCT**：SKU/asset 两者为空、单侧为空、两者非空的重放与冲突。
4. **维度隔离**：跨 tenant/account/shop/listing/SKU/product/campaign/asset 注入被应用或数据库拒绝；事务后零脏行。
5. **并发**：同值 2~N worker 仅一行且同 id；异值竞争仅保留胜者，败者是确定领域异常。
6. **输入负例**：bool ID/金额、naive 时间、反向/零长度窗口、负金额/计数、非 finite Decimal、非法枚举、空证据。
7. **失败清理**：测试自建 fixture，finally 清理后新连接断言 snapshot/相关 fixture 零残留；连续执行两次结果一致。
8. **变异**：captured_at 入键、UPDATE 覆盖、漏比较 raw hash/维度、错误 NULL 语义四类变异均 RC=1，还原 RC=0。
9. **回归**：批次定向 pytest、既有 185/61、tsc、T5 CLI、T9 CI；无 migration，P0-0/P0-1 终态不变。

## 五、后续批次 gate（本轮不进入实现）

round-131 的后续矩阵仍有三项事实差异，批次 2 前必须复核：

1. 数据字典要求 category `subject_key=category_id`，round-131 写成类目名；需定义稳定 category_id 来源。
2. M2 `EvaluationFeedbackService.receive_evaluation()` 接收离散 evaluation 枚举，不直接接 numeric
   `material_score`；M3 `optimization/ab/ingest.py` 当前按 `platform_material_id` 摄取素材表现，也不是 SKU/shop
   消费器。五层事件到三模块的真实 adapter 仍需设计。
3. 当前 `roi_feedback_events` 没有消费状态/回执列；“事件标记消费”在冻结表上没有落点。方案 A 的消费游标/回执
   或方案 B 的可重放投影，需要在批次 2 前给出可执行持久化位置和事务边界。

另外，round-131 §八实际列出 U1~U7 共 **7 项**，并非交接摘要中的 5 项。U1/U2/U3/U4/U6 进入批次 2
前处理，U7 进入批次 3 前处理；U5 已由本文件限定为本地领域异常，workflow 映射延后。

## 六、round-133 交付要求

DSH 下一轮开始实现 **P0-2 批次 1 事实层**，范围锁定为：

- B1 version/evidence/observation 纯函数与类型；
- B2 append-only SnapshotRepository + Collector(PG)；
- B3 本文件 §四测试与变异门禁；
- 交付物逐文件 SHA-256、执行命令/结果、数据库清理终态与单一 RELAY。

批次 1 交付中不加入 feedback ledger、M1/M2/M3 adapter、CID、manual_tasks、workflow handler、error-code
registry 或 migration。Codex round-134 独立复核批次 1；通过后再进入批次 2 的契约收敛。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-132-->
