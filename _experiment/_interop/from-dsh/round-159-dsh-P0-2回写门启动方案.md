# round-159 DSH：P0-2 C2 回写门启动方案（仅分析，不实现）

> 日期：2026-09-12。输入：`from-cdx/round-158-cdx-P0-2计算门冻结确认.md`（C1-b/c COMPLETE 冻结；
> 下一轮仅 C2 启动方案分析）。
> 状态：**本轮只提交 C2 启动方案，不进入实体实现**；C1-a/C1-b-c/事实层/manifest 冻结不重开；
> C3 消费、SKU/M2 实际 DDL、manual/workflow、批次 3 继续锁定；M1/M3 范围变更仍待裁决。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 一、C2 边界（写入门 = ledger 写入，不含消费）

| 项 | 本门范围 | 明确排除 |
|---|---|---|
| 写入对象 | `app.roi_feedback_events`（append-only ledger，冻结表） | 不改历史表、不新增 migration（除 §八 SKU DDL 依赖另行裁决） |
| 输入来源 | C1 计算门输出（聚合结果 + 依据）+ 候选事实快照 | 不重算数值（沿用 calculator/aggregation 冻结口径） |
| 副作用 | ledger 行 + 同事务 audit（仅 created=true） | 不执行 M1/M2/M3 消费回写、不建 manual task、不写 workflow |
| 事务 | 单连接单事务（ledger + audit 原子） | 不引入跨库/跨事务补偿（C3 另议） |

## 二、拟改文件清单（预计 6 个，全部新增或追加式改动）

| 文件 | 动作 | 说明 |
|---|---|---|
| `backend/domain/report/feedback_repository.py` | **新增** | `FeedbackDraft`/`FeedbackWriteResult`/`FeedbackContentConflict`/`FeedbackValidationError` + `FeedbackRepository`（构造 idempotency_key、同源校验、insert-or-select、replay 比较、双唯一键并发） |
| `backend/domain/report/feedback_service.py` | **新增** | `FeedbackService.write_event(conn, *, draft, actor_id, tenant_public_id, request_id, worker_scope_tenant_public_id, user_directory)`：受信边界 + created=true 时同事务 `write_audit_event` |
| `backend/domain/report/__init__.py` | **追加式修改** | 追加导出（保留既有全部导出与行为，哈希按新版本登记） |
| `backend/tests/test_report_feedback.py` | **新增** | 纯函数 + PG 隔离 fixture（replay/冲突/同源负例/并发/审计/清理） |
| `backend/tests/test_report_feedback_service.py` | **新增（或并入上文件）** | 分层与审计事务边界（actor/request/worker scope、审计失败回滚） |
| `project/scripts/p0_2_c2_mutation_drill.py` | **新增（可选）** | 源码变异门禁（镜像批次 1 `p0_2_batch1_mutation_drill.py` 模式） |

> 冻结基线（本轮不动、实现时保持）：`selector.py` `FA58F412...`、`calculator.py` `735F67B9...`、
> `aggregation.py` `3B1004CE...`、`aggregation_manifest.py` `5255776E...`、`version.py` `1B41B9A7...`、
> `repository.py` `92A5B9D4...`、`collector.py` `C1B51E60...`。

## 三、public 写入口设计（分层冻结候选）

### 3.1 两层职责（沿用批次 1「Repository 无副作用业务、Service 承担审计/身份」模式）

```text
FeedbackService.write_event(conn, *, draft: FeedbackDraft, actor_id, tenant_public_id,
                            request_id, worker_scope_tenant_public_id, user_directory=None)
    -> FeedbackWriteResult(ledger_id: int, created: bool)
  职责：受信边界（同源校验 + 字段派生核对）→ Repository 写入 → created=true 时同事务写 audit

FeedbackRepository.write(draft: FeedbackDraft) -> FeedbackWriteResult
  职责：构造 idempotency_key → INSERT ... ON CONFLICT DO NOTHING RETURNING id
        → 冲突时按自然键查回 + replay 比较集比较 → created=false 或抛 FeedbackContentConflict
  无审计、无 actor、无外部 I/O
```

### 3.2 `FeedbackDraft` 字段（与 `app.roi_feedback_events` 可写列一一对应）

```text
8 维（来自 source snapshot，必须 exact-match）：tenant_id, account_id, shop_id, shop_listing_id,
  shop_listing_sku_id(可空), product_id, campaign_id, asset_binding_id(可空)
作用域：source_snapshot_id, window_start, window_end, attribution_mode
身份/内容：feedback_type, subject_type, subject_key, value(Decimal scale6), aggregation_version
证据：extra_explanation(dict)
```

- `idempotency_key` **由 Repository 内部构造**，不接受调用方传入（杜绝任意 hash 文本，沿用批次 1 R134-1 教训）；
- `value` 沿用计算门冻结口径（scale=6，`_check_scale6` 同规则：finite 且 exponent == -6）；
- `extra_explanation` key exact-set：`numerator_gmv`、`denominator_spend`、`origin_snapshot_ids`
  （确定性排序：source/来源快照 id 升序）、`selector_evidence`（C1-a DecisionBasis JSON）、
  `aggregation_version`。

### 3.3 入口类型门禁（沿用 round-156/157 教训）

- 公开入口在任何字段访问前检查 `isinstance(draft, FeedbackDraft)`，否则抛 `FeedbackValidationError`；
- 非法 draft（缺字段/类型错/非 scale6/非法枚举/未知版本）→ **`FeedbackValidationError`**（写前异常）；
- 已有同身份但 replay 内容不同 → **`FeedbackContentConflict`**（保留旧行）。两者分层不混用
  （round-144 §四.2 / round-147 §4.2 冻结）。

## 四、同源校验（subject 归属必须来自 source snapshot）

在 `write_event` 受信边界内，除 8 维 exact-match（trigger 已覆盖）外，**应用层补 window/attribution
exact-match**（round-140 §六.3：trigger 只覆盖八维），并新增 **subject 同源校验**
（round-142 §五.3 / round-144 §四.3）：

| feedback_type | subject_type | subject_key 必须等于 |
|---|---|---|
| product_score | product | source snapshot 关联 `products.public_id` |
| category_score | category | source product 的 `category_id`（**NFC 后**比较与落键；case-sensitive、无 trim） |
| material_score | material | 由 source `asset_binding_id` 解析的 `assets.public_id` |
| shop_strategy | shop | source snapshot 关联 `shops.public_id` |
| sku_margin | sku | **依赖 §八 SKU 稳定键裁决**（未裁决前该类型不产行） |

- 校验失败 → `FeedbackValidationError`（零落盘）；
- 交叉注入负例（必须逐项固化）：product_score 但 subject_key 指向另一 product；category 与 source
  product 的 category_id 不符；material 与 asset_binding 不符；shop 与 source shop 不符；
  **分解字符 category_id**（DB 存 `\u0301` 组合形式、传入 NFC 形式）必须判为**同值**（同 NFC 函数）。

## 五、fb 身份与重放比较集

### 5.1 identity（冻结公式，round-141 §4.1 / round-145 §〇）

```text
idempotency_key = "fb:v1:" + lower_hex_sha256(canonical_join([
    source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version]))
```
- 复用 `domain/workflow/queue.py` 的 `_canonical_join`（NFC/转义/`|` 连接/None→nil）与 `_hash_key`；
- 输入序固定，**不含** value/extra_explanation/window/attribution（内容可变项不制造新身份）；
- 三大固定黄金键（round-144 §四.1，已独立复算）：
  ```text
  GV-A 7|product_score|product|b7f6b8c0-1234-5678-9abc-def012345678|aggr_v1
       digest b45e40ca322be2d7c29d22fb344e2f67644ebb450131f9bf8eee41ff052ef43f
  GV-B 8|category_score|category|分类Á|aggr_v1   （Á = NFC(组合音标)）
       digest ab235c2771ec14e2ab75a5ba123b8cbc37c941819126fc2d74131743208f4dd4
  GV-C '9|material_score|material|a\\|b\\\\c|aggr_v1'
       digest d0284d2061bbbc0eea8db93ddce30463e9410b687057f31b8bc5edeed32d175c
  ```
- C2 实现时以同一函数**现场复算并断言等于上述 digest**（防公式漂移）。

### 5.2 replay 比较集（完整、NULL-safe）

同自然键 `(source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version)` 查回后，
比较**全部不可变业务列**：

```text
tenant_id, account_id, shop_id, shop_listing_id, shop_listing_sku_id, product_id, campaign_id,
asset_binding_id, source_snapshot_id, window_start, window_end, attribution_mode,
feedback_type, subject_type, subject_key, value, aggregation_version,
extra_explanation（NULL-safe exact equality）
```

- `extra_explanation` 用 `(g is None and w is None) or (g is not None and w is not None and g == w)`——
  NULL 与对象互换必须判为不同（round-144 §四.4 冻结）；
- 任一不同 → `FeedbackContentConflict`（旧行保持原值）；
- 追加防御：**查回行的 `idempotency_key` 必须等于按自然键现场复算值**，否则判冲突（数据损坏防御，
  round-142 §五.4）；
- `extra_explanation` 内 `origin_snapshot_ids` 落库前**确定性排序**（id 升序），避免同一事实两次写入
  因顺序不同被判冲突。

### 5.3 双唯一键（表上两条唯一约束）

```text
uq1 = (source_snapshot_id, feedback_type, subject_type, subject_key, aggregation_version)
uq2 = (tenant_id, idempotency_key)
```
- 两键**同义**：正常路径下由同一自然键派生，uq1 命中 ⇔ uq2 命中；
- **必须证明**：并发同值 → 恰一行、恰一 `created=true`、其余 `created=false` 同 id；
- **必须证明**：同 `idempotency_key` 但自然键不同（人为构造，如手工灌入伪造 idempotency_key）→
  **进入冲突分支**，不得按单一键返回旧行（round-140 §六.5 / round-142 §四）；
- 23505 后查回必须按 **NULLS NOT DISTINCT 语义**处理可空列（`shop_listing_sku_id`/`asset_binding_id`
  用 `IS NOT DISTINCT FROM`）——沿用批次 1 已验证写法。

## 六、created 才写审计 + 同事务边界

- **仅当 `created=true`** 写 `p0_2.feedback_write` 审计；`created=false` 重放**不新增 audit**
  （内容冲突与消费动作各自审计，round-142 §五.4 冻结）；
- 审计目标：`target_type="ad_campaign"`、`target_public_id=` **source snapshot 关联
  `ad_campaigns.public_id`**（round-145 §5.2：`roi_feedback_events` 无 public_id，用 campaign public_id）；
- 调用 `domain/audit.py::write_audit_event(conn, *, actor_id, tenant_public_id, action,
  target_type, target_public_id, request_id, before, after, evidence_ref,
  worker_scope_tenant_public_id, user_directory)`，动作 `action="p0_2.feedback_write"`；
- **同一事务**：ledger INSERT 与 audit INSERT 在 `Service.write_event` 的同一事务内提交；
  审计失败（ActorResolver 拒绝/DB 错误）→ **业务写入同事务回滚、失败事务零审计**；
- actor/request 由调用层传入（默认 service actor `e57a6a59-da1d-5628-baef-e3b78f12f9e5`，worker scope
  受 ActorResolver 双源校验）；C2 不自行造 actor。

## 七、并发测试与清理方案

### 7.1 测试项（`test_report_feedback*.py`）

| # | 测试 | 断言 |
|---|---|---|
| 1 | 首次写入 | `created=true`，ledger 1 行，audit 1 行，`feedback_write` |
| 2 | 完整重放（同自然键同内容） | `created=false`，同 ledger_id，行数不变，**audit 不新增** |
| 3 | 内容冲突（value/extra_explanation 不同） | `FeedbackContentConflict`，旧行逐列未变 |
| 4 | `extra_explanation` NULL↔对象 | 判冲突（NULL-safe equality） |
| 5 | idempotency 复算不一致（人为灌入错误 key） | 判冲突 |
| 6 | 同源校验负例（§四 四项 + 分解字符正例） | `FeedbackValidationError` 零落盘 / 同值通过 |
| 7 | 双唯一键并发（2 worker 同值） | 恰一行、same id、恰一 created=true |
| 8 | 双唯一键错配（同 uq2 不同自然键） | 冲突分支（不得按单键返回旧行） |
| 9 | 审计失败回滚 | 业务零落盘、审计零行（同事务） |
| 10 | worker scope 越权 | 拒绝 + 零落盘 |
| 11 | 类型门禁 | 非 `FeedbackDraft`（duck/object）→ `FeedbackValidationError` |
| 12 | SKU 类型（§八未裁决前） | `sku_margin` 未授权 → 明确拒绝而非静默落库 |

### 7.2 隔离与清理

- 测试使用**隔离 tenant 链**（复用批次 1/2 的 `Chain` 模式建立候选快照）+ 独立 fixture；
- `finally` 精确清理：先删 `roi_feedback_events`/`audit_events`（本 tenant），再走 chain 清理；
- **新连接断言零残留**（ledger/audit/snapshot/tenant 全 0）；
- 并发测试用独立引擎连接 + `threading.Barrier`（沿用批次 1 并发测试模式）。

### 7.3 变异门禁（可选，镜像批次 1）

`p0_2_c2_mutation_drill.py` 拟固化 4 项：身份键漏字段、replay 漏 `extra_explanation`、
created=false 也写审计、审计与业务拆成两事务——各自 RC=1、还原 RC=0。

### 7.4 环境注意（round-158 实测）

默认 pytest 临时目录（`%TEMP%\pytest-of-*`）存在 ACL 错误（`PermissionError [WinError 5]`）；
与本项目所有轮次一致，**必须显式指定工作区内全新 basetemp**（如 `--basetemp=.pytest-tmp-r159-<guid>`），
否则 setup error。该现象为环境既有问题，不计入 C2 代码缺陷。

## 八、SKU DDL 依赖与待裁决项

### 8.1 SKU 稳定键（阻塞 `sku_margin`）

- 现状：`shop_listing_skus` **无 `public_id`**；`platform_sku_id` 可空（round-140/142 冻结事实）；
- 已冻结方案 A（round-145 §5.1）：新增 head revision
  `ALTER TABLE app.shop_listing_skus ADD COLUMN public_id uuid NOT NULL DEFAULT gen_random_uuid();`
  + `UNIQUE (public_id)`；同步 `t3_expected.py`/generator/assert_t3_schema/变异 drill/`ci.yml` T9 exact-set；
  历史 migration 与生成基线**保持原哈希**（仅追加，不重写）；
- **C2 可先行范围**：`product_score`/`category_score`/`material_score`/`shop_strategy` 四类不依赖 SKU key，
  可先实现；`sku_margin` 在该 DDL 执行前**明确拒绝落库**（配置化 gate，不静默跳过）。
- 裁决选项：**(A)** 先授权 SKU 追加 migration，C2 一次覆盖五类；**(B)** C2 先覆盖四类，
  `sku_margin` 待 DDL 后再补（推荐 B，避免 DDL 与写入实现耦合同批）。

### 8.2 待独立裁决项（C2 授权前）

| # | 事项 | 建议 |
|---|---|---|
| D1 | C2 是否随本轮同时授权 SKU 追加 migration | 建议先仅授权 C2 代码（B），DDL 单独一轮 |
| D2 | `category_id` 受控词表（U7） | 维持 opaque + NFC + case-sensitive + 无 trim；词表变更另议 |
| D3 | service actor 与 worker scope 的具体取值 | 沿用 T7 seed 的 service actor + worker scope 双源校验 |
| D4 | `extra_explanation.selector_evidence` 是否内嵌完整 DecisionBasis | 建议内嵌（jsonb 无长度压力），保持可审计 |
| D5 | 审计 `before/after` 内容 | `after` 存 value/aggregation_version/subject_key；`before` 首次为 null |
| D6 | C2 是否包含 M1/M2/M3 消费回执 | 否（C3 独立门；M1/M3 范围变更仍待裁决） |
| D7 | 变异 drill 是否纳入 C2 验收 | 建议纳入（与批次 1 同级门禁） |

## 九、C2 验收 DAG（获批后）

```text
C2-A  FeedbackRepository（身份键 + insert-or-select + replay + 冲突分层）
      验收：三黄金键现场复算一致；replay/NULL-safe/复算不一致/双唯一键并发；类型门禁；负例零落盘
C2-B  同源校验（8 维 + window/attribution exact-match + subject 归属 + NFC 一致）
      验收：四项交叉注入负例 + 分解字符同值正例
C2-C  FeedbackService（审计同事务，仅 created=true）
      验收：created=true 写 1 条 feedback_write（target=campaign.public_id）；重放不新增；
            审计失败回滚零审计；worker scope 越权拒绝
C2-D  SKU 类型 gate（§8.1 裁决后放开）
C2-E  回归与清理（C2 新增测试 + 376 全量零破坏 + PG 零残留 + 可选变异 drill）
```

## 十、交接

请 Codex 审阅本启动方案：拟改文件清单、public 写入口分层、同源校验矩阵、fb 身份与 replay 比较集、
created 才写审计的同事务边界、双唯一键并发与清理方案、SKU DDL 依赖（含推荐选项 B）、以及 D1~D7 待裁决项。
本轮**未进入 C2/C3 实体实现**，未改动任何业务代码、测试、migration 或冻结契约；已冻结计算门不重开。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-160-->