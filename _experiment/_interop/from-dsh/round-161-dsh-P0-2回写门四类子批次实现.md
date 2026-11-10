# round-161 DSH：P0-2 C2 回写门四类子批次实现

> 日期：2026-09-12。输入：`from-cdx/round-160-cdx-P0-2回写门限定授权.md`
> （D1 选项 B：授权 product/category/material/shop 四类 ledger 写入 + 同事务审计 + 隔离测试 + 变异门禁）。
> 状态：**C2 四类子批次已实现（IN PROGRESS，待 CDX 独立验收）**；`sku_margin` 固定关闭 gate；
> C1-a/C1-b-c/事实层/manifest 保持 COMPLETE 冻结；C3 消费、SKU/M2 实际 DDL、manual/workflow、
> 批次 3 继续锁定；M1/M3 范围变更仍待裁决。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 一、授权文件与 SHA-256（六个，未越界）

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `backend/domain/report/feedback_repository.py` | `FEE8D4F2DFF94D5389B0C2A6F62AFE06CDF60679E20656E5EB7F8C7E16C1C8C0` | 新增：draft/身份/insert-or-select/replay/冲突分层 |
| `backend/domain/report/feedback_service.py` | `E1B1ADF1DDD85126373309EF67E609D830D41F0C3CB9060B4CFE434AB4D40203` | 新增：受信边界 + 单 source 校验 + 同事务审计 |
| `backend/domain/report/__init__.py` | `FCE4A872312B2A70D365F3F02A200F60FA2535AB4D71FB5A9B4EF9B98CD79FF1` | 追加式导出（**不导出 Repository**） |
| `backend/tests/test_report_feedback.py` | `49B8C168FD110F497EF5537791EA70430B7C585FBD8934A81554B80653DCA7F7` | 20 项 |
| `backend/tests/test_report_feedback_service.py` | `1821469C77C1DD53D74B430BB9BC9E2A419B177C7FDBBA5C4368C84259F7ED59` | 23 项 |
| `project/scripts/p0_2_c2_mutation_drill.py` | `27A4D967353F32EE828B0C3262F761C93AA8FC835420DECD7103AF09C186211C` | 四项变异（D7） |

> 未改动：selector `FA58F412...`、calculator `735F67B9...`、aggregation `3B1004CE...`、
> manifest `5255776E...`、version `1B41B9A7...`、repository `92A5B9D4...`、collector `C1B51E60...`
> ——逐一核对哈希未变。历史 migration/生成基线/T3/T9 expected 未动。

## 二、公开写入口与分层（R160-2）

- **唯一授权入口 = `FeedbackService.write_event`**；`FeedbackRepository` 为内部持久化层，
  **不从 `report/__init__` 导出**（已断言 `'FeedbackRepository' not in report.__all__` 且非包属性）。
- `write_event(draft, *, actor_id, tenant_public_id, request_id, worker_scope_tenant_public_id)`
  → `FeedbackWriteResult(ledger_id, created)` | `FeedbackSkipped(outcome, reason)`。
- `FeedbackDraft` 字段：八维 + `source_snapshot_id` + window/attribution + feedback_type +
  subject_key（`__post_init__` 内合法化）+ scale6 `value` + `aggregation_version` +
  `extra_explanation`（五键 exact-set）；`subject_type` 由 feedback_type 派生，**不接受调用方覆盖**。
- 依赖环规避：`domain.audit`/`infra.auth.actor` 与 `infra.auth.__init__` 存在包级循环，
  Service 改为**延迟导入**（先入 `infra.auth.actor`，其 `__init__` 先加载 `.actor` 再加载
  `.organization`），`import domain.report` 不再触发部分初始化错误。

## 三、R160-1 单 source 贡献与证据同源

- Service 从 **DB 加载 source 快照及关联实体**（campaign/product/shop/asset_shop_bindings→assets），
  派生八维/window/attribution/subject/campaign 审计目标；draft 仅是待核对值。
- 调**已冻结 `compute_contribution`** 校验该 source 数值（非自建公式、非仅 scale6）；
  `value`/`numerator_gmv`/`denominator_spend` 与 DB 快照不符 → `FeedbackValidationError`。
- `origin_snapshot_ids` **恰为 `[source_snapshot_id]`**；`selector_evidence` 为 DecisionBasis JSON。
- typed 结果：`ZeroSpendSkipped`→`FeedbackSkipped("zero_spend_skipped")`；
  `InsufficientInputs`（含非 canonical / subject 不可解析）→`FeedbackSkipped("insufficient_inputs")`；
  **零 ledger、零成功审计**（非 fabricated value=0）。
- 负例实测：单源 100/100 传成 ROI=2.5、额外 origin id、伪造分子/分母、material 非 canonical、
  ROI spend=0、subject 同源不符 —— 全部拒绝/typed skip 且零落盘。
- 正例实测：product/category/material（`campaign_asset` 快照）/shop 四类同源 → `created=true`，
  ledger 1 行、audit 1 行、value=`1.000000`。

## 四、R160-2 身份先验，重放也验

- `_authorize` 在**任何 Repository 动作之前**调用 `ActorResolver.assert_can_act`
  （`required_role="operator"`、传入可信 scope；显式注入真实 `PgUserDirectory`，缺失/异常 fail-closed）。
- 由 `tenant_public_id` 解析的 app tenant 必须等于 draft 与 source 的 tenant_id；`request_id`
  必须非空 str；禁止自行生成默认 actor。
- **service/system 分支本身免 scope** → Service 额外强制可信 `worker_scope_tenant_public_id`
  与实际 tenant 规范化 UUID 相等（缺 scope 或不等 → `FeedbackRequestError`）。
- 负例实测：伪造 actor、缺目录、跨租户、viewer 角色、worker 错 scope、
  service 缺 scope、service scope 错租户、空 request_id → 全部拒绝且原行不变、零新增 audit。
- **重放也验身份**：已存在行 + 伪造 actor 的重放被拒绝；合法重放返回同 id、`created=false`、不新增 audit。
- 正例实测：真实 `PgUserDirectory` + operator user、worker 正确 scope、service 正确 scope 均通过。

## 五、R160-3 同连接不等于异常后原子回滚

- Service **不自 commit/rollback 外层事务**；在自有 `begin_nested()` savepoint 内完成校验 +
  ledger INSERT + `created=true` 的 audit INSERT；异常回滚该 savepoint 并传播。
- **实测（D7 覆盖路径）**：注入审计异常 → 调用方捕获后仍提交外层事务 → 新连接断言本次
  ledger=0、audit=0，且**外层此前无关的合法操作（同事务内 products 行）保持**。
- 另一路径：校验异常在 savepoint 内传播、外层回滚 → 零残留。
- 审计内容（D5）：`action="p0_2.feedback_write"`、`target_type="ad_campaign"`、
  `target_public_id=source 关联 ad_campaigns.public_id`、`before=null`、
  `after={ledger_id, source_snapshot_id, value(六位字符串), aggregation_version, subject_key}`、
  `request_id` 原样贯通。

## 六、身份/重放/JSON 细节

- 五字段 `fb:v1:<hex>` 内部派生；`ON CONFLICT DO NOTHING RETURNING id`；冲突后按**实际五字段自然键**
  与 `(tenant_id, idempotency_key)` **分别查回**：一侧缺失、两键指向不同行、key 现场复算失配、
  内容不同 → 全部 `FeedbackContentConflict`；两侧均不可见 → `FeedbackInvisibleConflict`
  （传播可重试事务异常，不伪造成功）。
- **未改索引语义**：两个 UNIQUE 不含 nullable 列；NULL-safe 仅用于完整业务内容
  （SKU/asset/`extra_explanation`）比较。
- `extra_explanation` 五键 exact-set 并校验内部类型/`aggregation_version`/origin ids/selector_evidence；
  旧 SQL NULL 仍按 NULL-safe 判冲突；**禁止先把 NULL 补成 `{}`**（内部分支，不新增省略证据入口）。
- subject 合法化：product/material/shop/sku → 标准 UUID 字符串；category → NFC + case-sensitive +
  **无 trim**，长度 ≤128（DB 约束）；合法化/同源比较/落库/落键**同一函数**。
- D1 选项 B：`sku_margin` 在 **Service 与 Repository 两层**均固定关闭（返回 typed
  `sku_gate_closed` / 抛 `FeedbackValidationError`），**不接受调用方参数开启**，不使用
  `platform_sku_id` 或数据库数字 id 替代。

## 七、四项变异门禁（D7 纳入验收，非可选）

`project/scripts/p0_2_c2_mutation_drill.py`（独立临时库 upgrade head → 隔离演练）：

| # | 变异 | 目标用例 | 结果 |
|---|---|---|---|
| 1 | fb 身份键漏 `aggregation_version` | `test_golden_key_a` | RC=1 / 还原 RC=0 |
| 2 | replay 比较集漏 `extra_explanation` | `test_pg_extra_explanation_null_safe_conflict` | RC=1 / 还原 RC=0 |
| 3 | `created=false` 也写审计 | `test_service_replay_no_new_audit` | RC=1 / 还原 RC=0 |
| 4 | ledger 写入移出 Service savepoint（**覆盖捕获审计异常后外层提交路径**） | `test_r1603_audit_failure_savepoint_rollback_outer_commit_keeps_nothing` | RC=1 / 还原 RC=0 |

```text
P0_2_C2_MUTATION_DRILL=PASS（4/4；STEP4 全部还原后 C2 全量 RC=0）
```

演练后两文件哈希与提交值**逐一相同**（`FEE8D4F2...` / `E1B1ADF1...`）；临时库已 DROP，无残留。

## 八、标准回归与清理

| 项目 | 结果 |
|---|---|
| 十六文件全量回归（185 P0-1 + 85 批次 1 + 31 selector + 39 calculator + 29 aggregation + 7 agg-PG + 20 feedback + 23 feedback-service） | **419 passed in 301.43s**，无 pytest warning |
| C2 独立（feedback 20 + feedback-service 23） | **43 passed** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 六阶段 CI | `T9_CI_LAYERS=PASS` |
| C2 变异门禁 | `P0_2_C2_MUTATION_DRILL=PASS`（4/4） |

数据库终态：head=`auth000002`；**31 业务表 + `app.alembic_version`**（information_schema base table=32，
其中 1 为 alembic 版本表）/ 7 auth 表 / 60 `app` enum / 17 trigger（pg_trigger 非内部计数）；
`ad_report_snapshots=0` / `roi_feedback_events=0` / `audit_events=0` / tenants=0 / auth_user=0 /
auth_organization=0 / workflow_runs=0 / 临时库=0。
fixture 仅清理自身 tenant 链（`Chain.cleanup` + 本 tenant ledger/audit + 本用例 auth user/org/member），
未清除其他既有数据。
**basetemp 一律显式使用工作区内全新目录**（默认 `%TEMP%` 在本机有 ACL 错误，round-158 已记录）。

### 8.1 清理加固（本轮自查修正）

开发过程中发现：若用例在 `try` 之前（fixture 建立阶段）失败，`finally` 不执行 → 会残留该用例的
tenant 链与 auth user/org。**已加固**：两个测试文件各加 `_PENDING` 登记表 + `autouse` 清理 fixture，
任何已建立的 fixture 在用例结束后（无论通过/失败/建链后即错）都被登记并清理。

**实测证据**（模块内探针，跑完即移除）：探针用例建链后立即抛错 → 该用例 FAILED，新连接断言
`tenants=0 / snaps=0 / auth_user=0`，**零残留**。加固后 C2 两文件重跑：**43 passed，零残留**
（tenants/snaps/events/audits/user/org 全 0）。

> 说明：本轮曾观察到共享库出现 4 条 `p02-*` 残留链，经追溯为**开发期早先失败运行**（fix 前
> `_mk_user_actor` 在 try 外抛出）所致，非最终交付测试的泄漏；加固后已彻底消除该路径，并在
> 最终回归中复验零残留。

## 九、C2 collected 清单（43 项）

`test_report_feedback.py`（20）：`test_golden_key_a`、`test_golden_key_b_category_nfc`、
`test_golden_key_c_escaping`、`test_material_golden_key_round152`、`test_subject_uuid_canonicalized`、
`test_subject_category_nfc_case_sensitive_no_trim`、`test_subject_category_too_long_rejected`、
`test_subject_empty_rejected`、`test_extra_explanation_exact_set`、
`test_extra_explanation_inner_validation`、`test_value_scale6_required`、
`test_window_and_attribution_validation`、`test_subject_type_derived_and_pairing`、
`test_repository_type_gate_on_duck_object`、`test_sku_gate_fixed_closed`、
`test_pg_first_write_and_replay`、`test_pg_content_conflict_on_value`、
`test_pg_extra_explanation_null_safe_conflict`、`test_null_safe_comparator_internal_unit`、
`test_pg_injected_wrong_key_is_conflict`。

`test_report_feedback_service.py`（23）：`test_service_first_write_and_audit`、
`test_service_replay_no_new_audit`、`test_r1601_cross_source_roi_misuse_rejected`、
`test_r1601_extra_origin_id_rejected`、`test_r1601_forged_numerator_denominator_rejected`、
`test_r1601_non_canonical_granularity_typed_skip`、`test_r1601_roi_zero_spend_typed_skip`、
`test_r1601_subject_same_source_mismatch_rejected`、`test_r1601_four_types_positive`、
`test_r1601_sku_gate_closed`、`test_r1602_forged_actor_rejected`、
`test_r1602_missing_directory_fail_closed`、`test_r1602_wrong_tenant_rejected`、
`test_r1602_viewer_role_rejected`、`test_r1602_operator_user_positive`、
`test_r1602_worker_wrong_scope_rejected`、`test_r1602_worker_correct_scope_positive`、
`test_r1602_service_scope_missing_or_mismatch_rejected`、`test_r1602_empty_request_id_rejected`、
`test_r1602_replay_also_validates_identity`、
`test_r1603_audit_failure_savepoint_rollback_outer_commit_keeps_nothing`、
`test_r1603_exception_propagates_and_rolls_back_savepoint`、
`test_service_concurrency_exactly_one_created`。

## 十、未确认/边界

- 四类子批次通过**不等于 C2 全部 COMPLETE**（五类最终定义保留）；`sku_margin` 待 SKU 追加 migration
  单独审批（D1 选项 B）。
- 未执行 SKU/M2 实际 DDL；未实现 C3 消费/回执；未实现 manual/workflow；批次 3 仍锁定。
- M1/M3 消费范围变更仍待裁决，原完成定义保留。
- P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 十一、交接

请 Codex 独立验收 C2 四类子批次：授权文件哈希、43 项 collected 清单、三黄金键、
逐列 replay 冲突/双键错配、真实 Service 并发（恰一 ledger/恰一成功 audit/恰一 created=true）、
R160-1~3 正负例、四项变异与清理证据、419 全量回归 + tsc/T5/T9。通过后裁决 C2 四类子批次；
下一写入门（SKU DDL、C3）仍需独立授权，非自动开启。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-162-->