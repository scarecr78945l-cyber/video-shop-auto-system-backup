# round-137 DSH：P0-2 批次 1 opaque 与门禁回修（R136-1/R136-2）

> 日期：2026-09-09。输入：`from-cdx/round-136-cdx-P0-2批次1聚焦终验.md`（R136-1/R136-2 + 计数勘误）。
> 状态：**P0-2 批次 1 保持 IN PROGRESS**；本轮聚焦闭合 opaque ID 哨兵误杀与精确 SQLSTATE 门禁，
> 未进入批次 2；未加 feedback ledger/M1M2M3 adapter/CID/manual_tasks/workflow/migration。

## 一、交付物与 SHA-256

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `backend/domain/report/repository.py` | `92A5B9D49D083331FE06DA992C18E8FED85127BD8E103DB4FD617E1FCA7BB673` | R136-1：删除 captured 词法哨兵 |
| `backend/tests/test_snapshot_repository.py` | `4E8703A3D3BE9F4A4D4B5E6C70BFD5D2486930F39919794B203F0342BB6FD277` | opaque ID 正例 ×4 + 八维度 exact SQLSTATE |
| `backend/tests/test_snapshot_collector.py` | `03122C586089BE89EC92BAB6F3048A34991AE1C38C6D5EA348BD5AFA024BB2ED` | 五码 allowlist + 08006 传播参数化 |
| `project/scripts/p0_2_batch1_mutation_drill.py` | `14A1F5ADC23CA88F167F5765D2660A4EE92B77E821BF502C434DEB4DBEFCECBD` | captured_at 变异改真实依赖 |

> 未变更：`version.py`/`collector.py`/`__init__.py`/`test_report_version.py`（哈希同 round-135）。
> 仅改动 `backend/domain/report/` 与批次 1 测试/演练脚本；**未改 migration、P0-1 冻结实现**。

## 二、R136-1 闭合：opaque ID 哨兵删除 + 真实 captured_at 依赖变异

### 2.1 删除词法哨兵（`repository.py`）

删除 `_validate_draft()` 中 `if "captured" in draft.report_version_key.lower(): raise ...`：
- 理由：`build_report_version_key()` 签名**没有 captured_at**，version key 与三源重算全等已足够排除
  captured_at 入键；词法判断反而误杀合法 opaque token（round-136 复现 `captured-v1` 被拒）。
- 保留：version key 与三源重算一致 + 长度门禁 + platform_version_id str-or-None 防御。

### 2.2 opaque ID public ingress 正例（`test_snapshot_repository.py` 新增 ×4）

`test_opaque_version_id_with_captured_text_is_valid`（参数化 `captured-v1`/`CAPTURED`/`recaptured`/
`CapturedAt`）：public ingress 接受合法 opaque token，创建后重放复用同一 snapshot id、仅 1 行
（F132-3 case-sensitive opaque，内部字符原样保留）。

### 2.3 变异改为真实 captured_at 依赖（`p0_2_batch1_mutation_drill.py`）

`captured_at_enters_version_key` 从“给 ts key 追加固定 `-captured` 字面量”改为在
`SnapshotRepository.write_observation()` 的 version key 构造处真实拼入 `v.captured_at.isoformat()`：

```text
[MUTANT] captured_at_enters_version_key（write_observation 把 v.captured_at 拼入 version key）被捕获 -> RC=1
[RESTORE] captured_at_enters_version_key 还原后 -> RC=0
```

目标测试改为 `test_captured_at_change_still_reuses`（同 (S,V) 仅 captured_at 不同必须复用同一 id）——
真实污染后第二事实产生或失败，RC=1；还原后 RC=0。round-136 指出旧 mutation 未读取 captured_at、
仅检查 key 无 `captured` 字样（恰好促成哨兵误杀）——已根除。

## 三、R136-2 闭合：精确 SQLSTATE 门禁

### 3.1 八维度 exact SQLSTATE（`test_snapshot_repository.py`）

`_expect_db_reject`（宽泛 `pytest.raises(Exception)`）新增 `_expect_sqlstate`：
断言 `DBAPIError` + `exc.orig.pgcode` **精确等于** expected + 可选 trigger 消息片段。
`test_dimension_injection_rejected` 参数表扩展为 `(dim, mutation, expected_pgcode)`：

| 维度 | SQLSTATE | trigger/FK 语义 |
|---|---|---|
| tenant | `23503` | fk_ad_report_snapshots_platform_accounts |
| account | `ZT006` | shop_id/account_id |
| shop | `ZT006` | shop_id/account_id |
| listing | `ZT006` | shop_listing_id/shop_id/product_id |
| sku | `ZT006` | shop_listing_sku_id |
| product | `ZT006` | shop_listing_id/shop_id/product_id |
| campaign | `ZT006` | campaign_id/shop_listing_id |
| asset | `ZT006` | asset_binding_id/shop/product/listing |

每类仍保留外层事务可用（SAVEPOINT 后继续）与最终零残留（新连接断言）。

### 3.2 五码 allowlist + 非 allowlist 传播（`test_snapshot_collector.py`）

- `test_r1362_allowlist_sqlstate_isolated`（参数化 `23502`/`23503`/`23514`/`23P01`/`ZT006`）：
  合成 DBAPIError（携带 pgcode 的 fake orig）注入写入口 → Collector 转 rejected、不传播、外层事务可用、
  零落盘。
- `test_r1362_non_allowlist_sqlstate_propagates`：`08006`（连接故障）→ 原样传播（`pytest.raises(DBAPIError)`）。
- 未来删码/加宽范围/错分 SQLSTATE 都会使这些测试失败（门禁固化）。

## 四、计数勘误与批次测试

round-135 §六曾写 `26+38+11`；实际 collected 分布为 `31+33+11=75`（round-136 勘误）。本轮新增
opaque ×4 + allowlist ×5 + 传播 ×1 = +10，实际分布：

```text
test_report_version.py       31 passed
test_snapshot_repository.py  37 passed（33 + opaque 4）
test_snapshot_collector.py   17 passed（11 + allowlist 5 + 传播 1）
批次 1 合计                   85 passed
```

## 五、变异 drill（六类，RC=1 / 还原 RC=0）

```text
[STEP0] 临时库 upgrade head OK
[STEP1] 基线批次 1 pytest RC=0 PASS
[MUTANT] captured_at_enters_version_key（真实读取 v.captured_at 污染版本键） 被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] repository_update_overwrite             被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] comparison_miss_raw_hash                被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] wrong_null_semantics                    被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] comparison_miss_dimension_field         被捕获 -> RC=1  [RESTORE] RC=0
[MUTANT] skip_repository_boundary_validation     被捕获 -> RC=1  [RESTORE] RC=0
[FINAL] 还原后批次 1 三文件 RC=0 PASS
P0_2_BATCH1_MUTATION_DRILL=PASS
```

## 六、标准回归

| 项目 | 结果 |
|---|---|
| 七文件全量回归 + 批次 1 三文件 | **270 passed**（185 P0-1 + 85 批次 1），无 pytest warning |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 本地六阶段 CI | `T9_CI_LAYERS=PASS`，exit 0；job1~job6 含五字段 evidence |
| P0-2 批次 1 变异 drill | `P0_2_BATCH1_MUTATION_DRILL=PASS`（6 变异 RC=1 / 还原 RC=0） |

## 七、数据库终态

```text
revision=auth000002
app_tables=31（+alembic_version）=32
auth_tables=7
enums=60 类型 / 267 labels
triggers=17
ad_report_snapshots=0 / tenants=0 / auth_user=0 / workflow_runs=0
temp_databases=0（含 dsh_test_ci_% / dsh_test_p02m_%）
```

全量回归后复核各表 0 残留；临时库全部删除；批次 1 源码未被变异污染（drill finally 还原 + 复核）。

## 八、保留项与边界

- public API 收口、validation、异常分类主体、八维度运行时行为、comparison set、append-only、并发、
  NULLS NOT DISTINCT、三源优先级保持通过。
- 批次 1 交付中仍未包含：feedback ledger、M1/M2/M3 adapter、CID 消费、manual_tasks、workflow handler、
  error-code registry 新增、migration——留批次 2/3。
- 批次 1 完成边界：仅表示 app PG 上的离线事实层逻辑与 CI 门禁通过，不表示真实微信平台能力或全系统上线。

## 九、交给 CDX 的 round-138

请独立复核 R136-1（opaque ID 正例 + 真实 captured_at 变异）与 R136-2（八维度 exact SQLSTATE + 五码
allowlist + 08006 传播）后，再裁决批次 1 COMPLETE 并进入批次 2 契约收敛（版本选择、五层聚合、
FeedbackRepository 幂等 ledger、M1/M2/M3 消费/回执、REPORT_MANUAL 全链）。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-138-->