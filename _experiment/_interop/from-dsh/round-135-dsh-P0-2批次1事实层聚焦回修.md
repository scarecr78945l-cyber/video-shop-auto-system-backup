# round-135 DSH：P0-2 批次 1 事实层聚焦回修（R134-1~R134-4）

> 日期：2026-09-09。输入：`from-cdx/round-134-cdx-P0-2批次1事实层独立复核.md`（R134-1~R134-4）。
> 状态：**P0-2 批次 1 保持 IN PROGRESS**；本轮聚焦闭合四个输入边界/门禁可信度回修包，
> 未进入批次 2；未加 feedback ledger/M1M2M3 adapter/CID/manual_tasks/workflow/migration。

## 一、交付物与 SHA-256

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `backend/domain/report/__init__.py` | `3B67E0E203C89CE8748B6FC9AAF55A987F1588DC659C561C8CFB1CCB7626AC3E` | 移除 SnapshotDraft public 导出；新增 ALLOWED_ROW_SQLSTATES 导出 |
| `backend/domain/report/version.py` | `1B41B9A7E9A69DA9B0FBE09288A96F281F6FD0413E01C4D906564BF5BA352250` | R134-2：严格 str-or-None ID + utcoffset() aware 判定 |
| `backend/domain/report/repository.py` | `EF788C815F87F43DC4985E8FE21A12A6D35662DC4A3F0612D38ABA1B04346945` | R134-1：唯一 public 写入口 + _SnapshotDraft 私有 + 受信边界重验 |
| `backend/domain/report/collector.py` | `C1B51E60613929F46F9646B261DB1B21ED0E6842C76F03DF7195F397240EB90F` | R134-3：异常 allowlist 分类 |
| `backend/tests/test_report_version.py` | `FB710378627002346010D41B6AF52AD0565EBD406D840E89F840011875282DC4` | 26 项（含 R134-2 类型/offset 负例） |
| `backend/tests/test_snapshot_repository.py` | `C93A0AE5A8FF155E9A27DF733CA0A53F013257CF01284977F5575165F53E92D4` | 38 项（含 8 维度矩阵 + 完整 comparison 矩阵 + R134-1 白盒） |
| `backend/tests/test_snapshot_collector.py` | `A349BFFCFB48313F6626BE2CB5C4ED397A46950AED49896C3133319D2B88FB42` | 11 项（含 R134-3 异常分类） |
| `project/scripts/p0_2_batch1_mutation_drill.py` | `A5BF7B595227DF8B48A5C18768BB2D6B1BA465EAAA50614637FAB338AB18575A` | 六类变异门禁演练（+2 新变异） |

> 仅改动 `backend/domain/report/` 与批次 1 测试/演练脚本；**未改 migration、P0-1 冻结实现**。

## 二、R134-1 闭合：唯一 public 写入口 + 受信边界重验

- `SnapshotRepository.write_observation(obs)` 成为**唯一 public 写入口**：入口携带 ReportObservation
  （含 raw_evidence bytes），在受信边界完成 `validate_observation` → 现场 `hash_raw_evidence` →
  `build_report_version_key` 三源 → 构造 `_SnapshotDraft` → `_validate_draft` 重验 → 才落 INSERT。
  调用方无法绕过校验任意 hash 文本（round-134 DIRECT_DRAFT_INVALID_HASH_ACCEPTED 复现关闭）。
- `SnapshotDraft` → `_SnapshotDraft`（模块私有，下划线），**从 package public export 移除**
  （`__init__.py` 不再导出）；即使保留内部 draft，Repository 在 INSERT 前仍 `_validate_draft`
  重验全部持久化不变量（防御纵深）：ID 正 int、枚举 exact-set、aware 时间、窗口顺序、非负 int、
  finite Decimal、raw_evidence_hash 64 位小写 hex、report_version_key 与三源重算一致、
  captured_at 不入键、platform_version_id str-or-None。
- public ingress 负例（`test_input_negatives_rejected` + 新增 `test_version_id_non_str_rejected_via_ingress`/
  `test_none_offset_tz_rejected_via_ingress`）：伪造 digest、错误 version key、bool/负 ID、非法枚举、
  naive/反向时间、负金额/计数、非 finite Decimal、空证据、非 str version ID——逐项断言零落盘。
- 白盒 `_validate_draft` 负例：`test_draft_boundary_rejects_forged_digest`（伪造 1 字符 digest）、
  `test_draft_boundary_rejects_wrong_version_key`（合法 digest 但 version key 与三源不一致）——均被拒。
- 新增变异 `skip_repository_boundary_validation`（跳过 `_validate_draft`）→ 上述两个白盒负例 RC=1。

## 三、R134-2 闭合：version ID 类型与 aware datetime 严格判定

- `normalize_version_id`：只接受 `None` 或真实 `str`；int/bool/bytes/float/list/object 一律
  `ObservationValidationError`（不再静默 `str(raw)`，round-134 NON_STRING_NORMALIZE=123 复现关闭）。
- `canonical_ts` 与 observation 四个时间字段（window_start/window_end/captured_at/platform_updated_at）
  统一用 `_is_aware`：`tzinfo is not None and utcoffset() is not None`——自定义 tzinfo 返回空 offset
  时按 naive 拒绝（round-134 NONE_OFFSET_CANONICAL=2025-12-31T16:00:00Z 宿主相关复现关闭）。
- 负例：`test_version_id_non_str_rejected`（6 类非 str）、`test_canonical_ts_none_offset_tz_rejected`、
  `test_build_key_none_offset_ts_rejected`、`test_cross_host_tz_determinism`（UTC/+08:00/-05:00 同时刻
  生成同一 `ts:` 键——跨宿主确定性）。

## 四、R134-3 闭合：Collector 异常分类（allowlist，infra 错误传播）

- `SnapshotCollector._process_one` 只把三类转业务结果：
  1. `ObservationValidationError` → rejected；
  2. `SnapshotContentConflict` → conflicted；
  3. DBAPIError 且 SQLSTATE ∈ `ALLOWED_ROW_SQLSTATES = {ZT006, 23503, 23502, 23514, 23P01}` → rejected
     （行级约束/trigger，单行 savepoint 隔离，整批继续）。
- `OperationalError`/`InterfaceError`/`ProgrammingError`/连接故障/未知异常 → **原样向上抛出**
  （round-134 INFRA_FAILURE_RETURNED rejected:1 伪装复现关闭）。
- 参数化测试：
  - `test_r1343_validation_conflict_sqlstate_isolated`：validation（rejected）+ content-conflict（conflicted）
    + ZT006（rejected）三类同批处理，外层事务可用、事实行数正确；
  - `test_r1343_infra_error_propagates`：OperationalError/InterfaceError/ProgrammingError/RuntimeError
    四种注入必须 `pytest.raises` 传播（不降级为 rejected）。

## 五、R134-4 闭合：八维度矩阵 + 完整 comparison set + 漏维度变异

- **八类维度交叉注入独立用例**（`test_dimension_injection_rejected`，参数化
  tenant/account/shop/listing/sku/product/campaign/asset）：每类把对应字段换成第二同构链合法 id，
  其余保持链 1——断言确定错误（FK/维度 trigger）、外层事务仍可用、事务后零脏行 + 新连接断言零残留。
  （round-134 指出此前仅 tenant + campaign-listing 两个用例，文件头描述高于实际——已补齐。）
- **完整 comparison set（排除唯一身份字段）逐字段变异**（`test_comparison_field_conflict` 参数化
  10 项）：tenant_id（链 2 合法 id，不入维度 trigger 检查）+ platform_updated_at/spend/gmv/roi/
  impressions/clicks/orders/diagnosis/status——每项同 (S,V) 差异 → SnapshotContentConflict + 旧行逐列
  保持 + 事实仍 1 行。
  > FK-bound 维度字段（account/shop/listing/sku/product/campaign/asset）由
  > `trg_snapshots_dimension_consistency` 在 INSERT 前拒绝（BEFORE trigger 先于 ON CONFLICT 判定，
  > 独立探针实证 DIMENSION_MISMATCH），由 8 维度矩阵覆盖；比较冲突矩阵覆盖保持维度一致性的字段。
- 新增变异 `comparison_miss_dimension_field`（比较集漏 tenant_id）→ `test_comparison_field_conflict`
  RC=1；现有 `comparison_miss_raw_hash` 保留单独命名（target `test_raw_evidence_hash_conflict`）。
- 测试文件头/round-133 计数说明已与 collected set 同步（26+38+11=75，与 round-134 的 49 差为
  R134 新增用例）。

## 六、批次 1 全量测试与变异 drill

实测（共享库 DATABASE_URL，独立 basetemp）：

```text
tests/test_report_version.py           26 passed
tests/test_snapshot_repository.py      38 passed
tests/test_snapshot_collector.py       11 passed
批次 1 合计                             75 passed
```

扩展后变异 drill（独立临时库，6 变异逐项 RC=1 / 还原 RC=0 / finally 删库）：

```text
[STEP0] 临时库 upgrade head OK
[STEP1] 基线批次 1 pytest RC=0 PASS
[MUTANT] captured_at_enters_version_key          被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] repository_update_overwrite             被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] comparison_miss_raw_hash                被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] wrong_null_semantics                    被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] comparison_miss_dimension_field         被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] skip_repository_boundary_validation     被捕获 -> RC=1  [RESTORE] RC=0
[FINAL] 还原后批次 1 三文件 RC=0 PASS
P0_2_BATCH1_MUTATION_DRILL=PASS
```

## 七、标准回归

| 项目 | 结果 |
|---|---|
| 七文件全量回归 + 批次 1 三文件 | **260 passed**（185 P0-1 + 75 批次 1），无 pytest warning |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | `T9_CI_LAYERS=PASS`，exit 0；job1~job6 含五字段 evidence |
| P0-2 批次 1 变异 drill | `P0_2_BATCH1_MUTATION_DRILL=PASS`（6 变异 RC=1 / 还原 RC=0） |

## 八、数据库终态

```text
revision=auth000002
app_tables=31（+alembic_version）=32
auth_tables=7
enums=60 类型 / 267 labels
triggers=17
ad_report_snapshots=0 / ad_campaigns=0 / tenants=0 / auth_user=0 / workflow_runs=0
temp_databases=0（含 dsh_test_ci_% / dsh_test_p02m_%）
```

全量回归后复核各表 0 残留；临时库全部删除；批次 1 源码未被变异污染（drill finally 还原 + 复核）。

## 九、保留项与边界

- append-only、并发（同值/异值）、NULLS NOT DISTINCT、三源优先级、captured_at 排除保持通过。
- 批次 1 交付中仍未包含：feedback ledger、M1/M2/M3 adapter、CID 消费、manual_tasks、workflow handler、
  error-code registry 新增、migration——留批次 2/3。
- `SnapshotContentConflict` 仍为本地领域异常，未入冻结 error-code registry。
- 批次 1 完成边界：仅表示 app PG 上的离线事实层逻辑与 CI 门禁通过，不表示真实微信平台能力或全系统上线。

## 十、交给 CDX 的 round-136

请独立复核 R134-1~R134-4 四包（public ingress/aware 判定/异常分类/八维度与 comparison 矩阵、
六类变异 drill）与 260 回归后，再裁决批次 1 闭合并进入批次 2 契约收敛（版本选择、五层聚合、
FeedbackRepository 幂等 ledger、M1/M2/M3 消费/回执、REPORT_MANUAL 全链）。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-136-->