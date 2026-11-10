# round-155 DSH：P0-2 聚合去重与数值边界回修（R154-1/2/3）+ M2 结构终选（R152-2）

> 日期：2026-09-12。输入：`from-cdx/round-154-cdx-P0-2计算门独立验收与回修.md`（R154-1~3 + R152-2 剩余）。
> 状态：**C1-b/c IN PROGRESS（保留计算门实现/回修授权，写入门未解锁）**；C1-a 与事实层继续冻结；
> C2/C3、SKU/M2 实际 DDL、manual/workflow、批次 3 继续锁定。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 一、变更文件与 SHA-256

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `backend/domain/report/calculator.py` | `735F67B9E2A3363D462AD019B7995E25810B26298AECB48E00872D3C0EC1485A` | R154-2：scale 校验改指数/finite |
| `backend/domain/report/aggregation.py` | `1940A621DD274ED8050EB8E4A5DD42C9793702015B9BE71534E5A2F88ACBC8F5` | R154-1 去重 + R154-3 校验/PG 基准 |
| `backend/domain/report/__init__.py` | `5BEDCEE73AED1F304159121E3BB37A00662283AB633208361A7D2AE01D433563` | 未变（无新导出，哈希同 round-153） |
| `backend/tests/test_report_calculator.py` | `BA5D3900A4231FFBE5202F55F611FCE9E21F5DD3F9A1CC2D5C00E6C5D8CA5FB2` | 39 项 |
| `backend/tests/test_report_aggregation.py` | `2F463DCF788F9CA7F001DF7CBACE29196D7192BB9302ACEC8D6F7E467D0A5A39` | 26 项 |
| `backend/tests/test_report_aggregation_pg.py` | `2258EF0ABE95766769255D9E1B6608E7C9F7BC47A127EFC83D04DA1AEE8A0E38` | 新增：PG 只读接线 7 项 |

> 选择器（`FA58F412...`）、事实层三文件、manifest（`5255776E...`）哈希保持冻结。
> **计数勘误（round-154 §一）**：round-153 交付写的 `24+20` 分布有误，实际为
> `calculator 30`、`aggregation 14`（合计 44 不变）；本轮修复后为 **calculator 39 / aggregation 26 / aggregation_pg 7**。

## 二、R154-1 闭合：按 scoped event 身份去重（金额只计一次）

- `aggregate_events` 先按 **scoped event 身份**
  `(tenant_id, source_snapshot_id, feedback_type, subject_type, subject_key, window_start,
  window_end, attribution_mode, aggregation_version)` 去重：
  - **完整重放（身份同、内容同）→ 只贡献一次**（修复前 gmv 累加到 600 → ROI 2.0）；
  - **身份同、内容不同（granularity/gmv/spend）→ `AggregationInputError` 确定性冲突**，不静默求和。
- 修复错误测试预期：`test_r1541_duplicate_identity_counts_once` 现断言 `[A,A,B]` 与 `[A,B]` 完全等价
  （ROI=2.500000、gmv=500、spend=200、ids=(1,2)、sample=2）。
- 新增反例：ROI 重复异值冲突、SKU 重复异值冲突、SKU 同身份重放差额不变。
- 数据库 UNIQUE 不替代公开纯函数边界：纯函数自身拒绝重复异值输入。

## 三、R154-2 闭合：Decimal 全部置于 prec60/ROUND_HALF_UP 上下文

- `calculator.py`：`RoiContribution`/`SkuMarginContribution` 的 `__post_init__` 由
  `value.quantize()` 数值相等判断改为 **`_check_scale6`**——校验 `is_finite()` 且
  `as_tuple().exponent == -6`（不再调用 quantize，避免依赖调用方 context）。
- `aggregation.py`：**SKU 差额 `Decimal(gmv) − Decimal(spend)` 移入 `localcontext(prec=60,
  ROUND_HALF_UP)`** 内计算（修复前先在调用方 context 做减法再 quantize，大额丢位）。
- 新增测试：
  - `test_roi_invariant_under_caller_context`（调用方 prec 28/6/9/60 × 不同 rounding → 结果恒为
    `1.500000`/`0.333333`）；
  - `test_sku_large_int8_invariant`（`gmv=1234567890123456789, spend=0` 在 prec=28 与 prec=10/ROUND_DOWN
    下均得 `1234567890123456789.000000`）；
  - `test_zero_value_invariant`（prec=6 下 `0/100 → 0.000000`）；
  - `test_caller_context_not_polluted`（计算前后调用方 prec/rounding 不变）；
  - `test_scale6_representation_check`（非 6 位/NaN 拒绝）；
  - `test_sku_large_int8_invariant_in_aggregation`（聚合路径同样不受调用方 context 影响）。

## 四、R154-3 闭合：公开输入不变量 + PG 读取基准

### 4.1 输入不变量（公开入口与构造器共用 `_validate_event`）

- tenant_id / source_snapshot_id：**正 int**；
- gmv/spend：**非负 int（bool 拒绝）**（修复前 `gmv=True → ROI=0.01`、`gmv=-100 → ROI=-1.0`）；
- **五类 feedback↔subject 配对**（对齐 `ck_feedback_subject_map`：product_score↔product、
  category_score↔category、material_score↔material、sku_margin↔sku、shop_strategy↔shop）；
- **未知 `aggregation_version` → 拒绝**（`SUPPORTED_AGGREGATION_VERSIONS={aggr_v1}`；修复前套用 aggr_v1 算法）；
- window_start/window_end：aware 且 `start < end`；subject_key/attribution_mode 非空 str；
- 已冻结 typed outcome（缺字段/非 canonical）与非法输入异常分层保留。

### 4.2 跨作用域 fixture 修正

- `test_cross_scope_isolation` 改为**各作用域独立真实 source/S**（4 条不同 source，各自 candidates）；
- 新增 `test_cross_scope_forged_source_negative`：同一 source 声明他租户 → `tenant_of_source` 不符 →
  **确定性拒绝**（不再用不一致来源证明隔离正确）；
- `test_subject_filter_distinct_sources`：两个 subject 各用各自真实 source。

### 4.3 PG 接线（同一读取基准 + schema 限定 + 真实接线测试）

- `aggregate_from_pg` 在 **`REPEATABLE READ`** 事务内执行全部 SELECT（三条查询共享同一已提交快照）；
  调用方须传未开启事务的新连接。
- 全部表名 **显式 `app.` 限定**（修复前 `roi_feedback_events` 未限定 schema）。
- 新增 `test_report_aggregation_pg.py`（7 项，隔离 PG fixture；候选经事实层建立，ledger 事件为测试隔离直写，
  非生产写入接口）：PG 真实三反例、**默认 search_path（不含 app）下仍可读**、NULL 维度（sku/asset 为 NULL）、
  跨 tenant/窗口/归因/版本隔离（aggr_v2 不纳入 aggr_v1 查询）、新版本提交后结果与 source 依据一致。
- 测试证据：`7 passed`，清理后 `events=0 / snaps=0 / tenants=0`（新连接断言零残留）。

## 五、R152-2 终选：M2 具体结构（仅文档，DDL/消费仍锁定）

### 5.1 `asset_items` 唯一性（二选一 → 选单绑定库）

**选择：单绑定库 `UNIQUE (content_sha256)`**（不再写 `(tenant_scope, content_sha256)`）。
理由：该 M2 本地库由 §5.3 的绑定表固定绑定**唯一** app 租户，`tenant_scope` 在本库内是常量、
不提供额外区分度；引入 `tenant_scope` 列会与绑定表形成双真源。唯一索引允许 SQLite 的多 NULL
（未回填旧行不参与唯一）。

### 5.2 SQLite 旧表实际升级步骤（非「统一 create_all」）

```text
SQLite（本批受测库）——asset_items 增列与索引：
  1. ALTER TABLE asset_items ADD COLUMN content_sha256 VARCHAR(64);        -- SQLite 支持 ADD COLUMN
  2. 回填：逐行按本地内容字节复算 SHA-256；缺文件 → 保持 NULL（不伪造）
  3. 重复检查：SELECT content_sha256 FROM asset_items WHERE content_sha256 IS NOT NULL
              GROUP BY content_sha256 HAVING count(*) > 1   → 非空则 fail（先人工消歧，不建索引）
  4. CREATE UNIQUE INDEX uq_asset_items_content_sha256 ON asset_items (content_sha256);
  5. 降级：DROP INDEX uq_asset_items_content_sha256;
          SQLite < 3.35 无 DROP COLUMN → 表重建：建新表（无 content_sha256）→ 拷贝 → drop 旧表 → 重命名
          （≥3.35 可直接 ALTER TABLE ... DROP COLUMN）

receipt 新表（asset_evaluations_receipt）：
  - 升级：create_all 幂等新增表（旧库 ADD TABLE）；
  - 降级：DROP TABLE IF EXISTS asset_evaluations_receipt；
  - 双 dialect：SQLAlchemy 表定义（BigInteger().with_variant(Integer,"sqlite") 自增、
    DateTime(timezone=True)+Python 默认、UniqueConstraint(receipt_key)、String 文本列），
    不使用 BIGSERIAL/now()/timestamptz 字面量；PG 路径按同一定义建表，不作为 SQLite 升级证据。
```

### 5.3 绑定单一真源（二选一 → 选绑定表）

**选择：单行绑定表 `m2_receipt_binding(tenant_public_id uuid NOT NULL)`**（移除「配置项」并列描述）。
- **缺绑定 → fail closed**：consumer 调用时若绑定行为空 → `TenantBindingError`，拒绝消费（不默认放行）；
- **一次性绑定**：初始化向导（`create_all` 后）写入唯一一行；`INSERT` 仅当表为空；
- **变更边界**：绑定不可静默修改；变更须显式 re-binding 流程 + 审计记录（换租户 = 新部署/显式迁移）；
- **验证责任**：每次调用校验 `worker_scope_tenant_public_id == 绑定 tenant_public_id`，不等即拒绝；
- **两租户反例**：合法租户 B 调用（绑定为 A）→ 拒绝；跨租户同 `content_sha256` 不共享本地标签。

## 六、标准回归

| 项目 | 结果 |
|---|---|
| 十四文件全量回归（185 P0-1 + 85 批次 1 + 31 selector + 39 calculator + 26 aggregation + 7 PG） | **373 passed**，无 pytest warning |
| 计算门独立（calculator 39 + aggregation 26 + aggregation_pg 7） | **72 passed** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 六阶段 CI | `T9_CI_LAYERS=PASS` |

数据库终态：auth000002 / 31 app 表 / 7 auth 表 / 60 enum / 17 trigger / ad_report_snapshots=0 /
roi_feedback_events=0 / tenants=0 / auth_user=0 / workflow_runs=0 / temp_databases=0。

## 七、保留项与边界

- manifest 与 M2 两黄金键、五类正常公式、四 Decimal 向量、SKU 零消耗/亏损、三有效源反例、canonical-only
  与选择器冻结均沿用通过。
- C1-b/c 未记 COMPLETE（待 CDX 独立验收）；C2/C3 写入门、SKU/M2 实际 DDL、manual/workflow、批次 3 未授权；
  M1/M3 范围变更仍登记待批。
- P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 八、交接

请 Codex 独立验收 R154-1（身份去重/内容冲突，含修复后的等价断言与 SKU 反例）、R154-2（prec60 上下文不变量、
大额 int8、context 不污染）、R154-3（输入不变量/真实 per-scope fixture/PG REPEATABLE READ + app schema +
7 项真实接线测试），并复核 R152-2 三项终选（单绑定库 UNIQUE、SQLite 旧表升级步骤、绑定表单一真源）。
通过后裁决计算门；写入门未授权前继续契约锁定。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-156-->