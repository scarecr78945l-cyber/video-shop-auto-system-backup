# round-153 DSH：P0-2 计算与聚合实现（C1-b/c）+ M2 契约闭合（R152-1/R152-2）

> 日期：2026-09-12。输入：`from-cdx/round-152-cdx-P0-2选择器冻结与计算门启动.md`
> （C1-a COMPLETE 冻结；仅 C1-b/c calculator/aggregation/manifest 授权实现；R152-1/2 仅文档）。
> 状态：**C1-b/c 实现交付（未记计算门 COMPLETE，待 CDX 独立验收）**；
> C2/C3 接线、SKU/M2 实际 DDL、manual/workflow、批次 3 继续锁定。
> 边界：P0-2 完成只表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 一、变更文件与 SHA-256

| 文件 | SHA-256 | 说明 |
|---|---|---|
| `backend/domain/report/aggregation_manifest.py` | `5255776EFD434FA4E7BD2347268ACAE9549D0093A095C0BA73EF3C451E7095E4` | aggr_v1 单一真源 + 哈希自检 |
| `backend/domain/report/calculator.py` | `6750CDDF506CA66BD6ACC96395E447EB105E1CED5A1D4F2938BD3D11D40922AF` | 单 source 贡献 + 五类 typed outcome |
| `backend/domain/report/aggregation.py` | `FF7AE52A8DA79D182CFF86865FFC62242B34E0DAB1170F521E4E3C809F4BE8EC` | 有效 source 集合 + scoped 聚合（PG 只读） |
| `backend/domain/report/__init__.py` | `5BEDCEE73AED1F304159121E3BB37A00662283AB633208361A7D2AE01D433563` | 追加式导出（保留既有导出） |
| `backend/tests/test_report_calculator.py` | `B112FD41E62763FF591153EFAC5BED25B53F028ADAA5AF09E8C95F0A8E7EF34E` | 24 项 |
| `backend/tests/test_report_aggregation.py` | `9F11C6438191DCD0F6967269D34486B91D86C59AC20388A04A871C68591207D7` | 20 项 |
| `backend/tests/test_report_selector.py` | `B0DE44D8F4B3B4608F418D0A0FBDE0F44952FF2D707CD1E11F641FCCEEF996A0` | 补 GV5 修订完整对象断言（31 项） |

> **选择器源码与事实层保持冻结**：`selector.py` 哈希保持 `FA58F41285D01A1CEDD8DD4C38F09AB6B95C17DA1F1250FD15B4FE9B1395EADC`；
> `version.py`/`repository.py`/`collector.py` 保持 round-135/137 冻结哈希。本轮仅新增 calculator/aggregation/manifest
> 与追加式导出，**未改选择器生产行为**。新增文件不触发 migration。

## 二、C1-b/c 实现（round-152 §三 授权范围）

### 2.1 `aggregation_manifest.py`——aggr_v1 单一真源

- `canonical_payload()` = `json.dumps(MANIFEST, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`；
- **实算 SHA-256 = `aeaa6cc2fe77a32b601c85700195ef047ca1dcc9ff01e9ddbd9f61258fdc62d1`**（与冻结预期一致，
  `verify_manifest()` 自检 True）；
- 五类 canonical granularity（product/category/shop=campaign、material=campaign_asset、sku=shop_listing_sku，无 fallback）；
- Decimal（prec=60/ROUND_HALF_UP/scale=6）、min_sample_snapshot=1、category_min_products=1；
- 升级规则：只增不改（新增 aggr_v2 + 新哈希，旧事件保持原 aggregation_version）。

### 2.2 `calculator.py`——单 source 数值贡献

- 纯函数 `compute_contribution(feedback_type, snapshot_id, gmv, spend, granularity=None)`；
- **ROI 类**（product/category/material/shop）：`gmv/spend` → `RoiContribution(value scale6)`；
  spend=0 → `ZeroSpendSkipped`（typed，非异常）；
- **SKU 类**（sku_margin）：`gmv−spend`（分）→ `SkuMarginContribution`，**允许负差额**，spend=0 **非 skip**；
- Decimal：`localcontext(prec=60, ROUND_HALF_UP)` + `quantize(0.000001, ROUND_HALF_UP)`；
- typed outcome 分层：`InsufficientInputs(reason∈{no_canonical_source, subject_unresolvable,
  missing_numerator_or_denominator})` —— 非 canonical granularity / 缺字段均返回 typed 结果；
- 输入负例：未知 feedback_type、bool/负金额、非法 snapshot_id → `CalculatorInputError`；
- **不执行反馈 INSERT/审计写入**（C2/C3 锁定）。

### 2.3 `aggregation.py`——有效 source 集合 + scoped 聚合（PG 只读）

- `effective_source_ids(candidates_by_identity)`：按 S 调用**已冻结 selector**，返回 identity → selected_id | None；
- `aggregate_events(events, candidates_by_identity, feedback_type, identity_of_source, ...)`：
  候选事实 → 有效集 → 仅 `source_snapshot_id ∈ 有效集`、canonical granularity、作用域匹配的 event 参与；
  **manual_required 的 S 不产出自动结果**；跨 source 按 `Σgmv/Σspend`（SKU：`Σ(gmv−spend)`）求和，**禁平均 event.value**；
- 作用域隔离：`tenant_id/feedback_type/subject_type/subject_key/window_start/window_end/attribution_mode/aggregation_version`；
- `sample_count = distinct 有效参与 source id`；`source_snapshot_ids` 稳定排序（结果依据可回溯）；
- PG 只读接线：`load_candidates_from_pg`（event 定位 S → 取该 S **全部事实快照**版本，含未产 event 的新版）、
  `load_source_events_from_pg`、`aggregate_from_pg` —— 全程 SELECT，无写入。

### 2.4 三个有效源反例（真实调用新实现；round-152 §三.4）

```text
CE1 双 ledger：candidates [201(t=09-01),202(t=09-02)]，events 201(gmv100/spend100)+202(gmv400/spend100)
    → effective_sources=((S1,202),)；ROI=400/100=4.000000（非 (100+400)/200=2.5）PASS
CE2 最新版无 event：candidates [301(t=09-03,无 event),302(t=09-02,event)] → effective=(S2,301)；
    aggregates=()（旧 302 ROI 被淘汰）PASS
CE3 最大并列：candidates [401(t=09-02),402(t=09-02)] → effective=(S3,None)，manual_identities=(S3,)，
    aggregates=()（保持人工态）PASS
```

### 2.5 测试覆盖（round-152 §三 清单）

`test_report_calculator.py` 24 项：五类 formula、四 Decimal 向量（1/3→0.333333、10/3→3.333333、
150/100→1.500000、0/100→0.000000，均 scale=6）、SKU 零消耗/亏损、canonical granularity 五类、
typed outcome 分层、输入负例、manifest 完整对象/hash/canonical 序列化。

`test_report_aggregation.py` 20 项：三反例、跨作用域隔离（4 组不同 tenant/window/attribution 不混算）、
跨粒度过滤（canonical-only）、SKU 跨 source 差额、ROI 零消耗 typed、重复 source 只计一次样本、
样本阈值、依据一致（source ids/分子分母可回溯）、subject 过滤、未知类型拒绝。

`test_report_selector.py` 31 项：补 `test_gv5_revised_complete_object` / `test_gv5_normal_revised_complete_object`
**完整对象**断言（round-152 接受的 detail 勘误：`platform_updated_at 2026-08-31T00:00:00.000000Z is earlier
than prior maximum 2026-09-01T00:00:00.000000Z`，detail 与 regressions.detail 相同；其余字段保持 round-147）。

## 三、R152-1 闭合：M2 回执身份（去除可变内容）

问题：round-151 把 receipt hash 输入写为 `[tenant_scope, asset_id, event_idempotency_key]`——同源事件换 asset
会得到两个 receipt_key，UNIQUE 无冲突，错误消费两次。

**修正（冻结）**：
- **receipt 身份只来自受控接收命名空间 + 真实绑定 tenant + `source_fb_key`**；
  `asset_id`/`evaluation`/`evidence` 属 **replay 内容比较**，不得制造新身份。
- 身份公式：
  ```text
  receipt_key = "m2:rv1:" + lower_hex_sha256(canonical_join([tenant_bound_public_id, source_fb_key]))
  UNIQUE (receipt_key)
  ```
  `tenant_bound_public_id` = 该 M2 本地库**固定绑定的真实 app 租户 public_id**（非常量标签，见 §四）。
- `event_idempotency_key` 与 `source_fb_key` 关系：`source_fb_key` 即 C2 ledger 的 `fb:v1:<hex>`
  （round-141 冻结公式）；consumer 直接以它作输入源引用；`event_idempotency_key` 无需另造。
- **固定黄金例（material consumer 正例使用 material_score，非 product_score）**：
  ```text
  source_fb_key fields = [7, "material_score", "material",
                          "f0e1d2c3-4b5a-6978-8a9b-0c1d2e3f4a5b", "aggr_v1"]
  canonical            = 7|material_score|material|f0e1d2c3-4b5a-6978-8a9b-0c1d2e3f4a5b|aggr_v1
  fb digest            = 38787dc866c0dd04de1becfeef18179116dd87381287a82885ac3fe2d13fd656
  source_fb_key        = fb:v1:38787dc866c0dd04de1becfeef18179116dd87381287a82885ac3fe2d13fd656

  tenant_bound_public_id = 0f8c2b1a-3d4e-5f60-7a8b-9c0d1e2f3a4b
  receipt canonical      = 0f8c2b1a-3d4e-5f60-7a8b-9c0d1e2f3a4b|fb:v1:38787dc866c0dd04de1becfeef18179116dd87381287a82885ac3fe2d13fd656
  receipt digest         = 36498091b1e5bcfeca31d1e27f73a2da26bc7cad34913af7c4a0c62831c23f3d
  receipt_key            = m2:rv1:36498091b1e5bcfeca31d1e27f73a2da26bc7cad34913af7c4a0c62831c23f3d
  ```
- **反例**：同源事件 E 换 asset（asset_id 10→11）→ `source_fb_key` 不变 → receipt_key 不变 →
  UNIQUE 命中 → 进入 **replay 内容比较** → 内容不同 → **conflict**（旧 receipt 保持），不再产生第二行。
- `m2:ev:aa11...` 作废，不计固定黄金键（round-152 §四.1）。

## 四、R152-2 闭合：本地库升级与真实租户绑定

### 4.1 本批受测数据库与兼容 migration

- 事实：`backend/materials/db.py` 默认 SQLite（`config.db_url` 可切 PostgreSQL），
  建表用 `Base.metadata.create_all`（无 migration 框架）。
- **本批受测数据库 = SQLite（默认路径）**；receipt DDL 用 **SQLAlchemy 表定义**（双 dialect 兼容），
  不用 PG 专有 `BIGSERIAL/now()/timestamptz` 字面量：
  - 主键 `BigInteger().with_variant(Integer, "sqlite")` + `autoincrement=True`（PG=BIGSERIAL，SQLite=INTEGER PRIMARY KEY）；
  - 时间 `DateTime(timezone=True)` + Python 侧 `default=utcnow`（PG=timestamptz，SQLite=TEXT/DATETIME）；
  - 唯一约束 `UniqueConstraint("receipt_key", name="uq_asset_evaluations_receipt_receipt_key")`
    （两 dialect 同义）；文本列 `String(...)`（不用 PG enum）。
- **升级 = `create_all` 幂等新增表**（`asset_evaluations_receipt` 为新表，旧库 ADD TABLE 即可）；
  降级 = `DROP TABLE IF EXISTS asset_evaluations_receipt`（逆序）。
- **PG DDL 不作为 SQLite 旧库升级证据**：本批以 SQLite 实测；PG 路径仅在切换配置时按同一 SQLAlchemy 定义建表。

### 4.2 `asset_items.content_sha256` 增列（最终方案）

- 列定义：`content_sha256 = Column(String(64), nullable=True)`（先可空，避免旧行 NOT NULL 无回填失败）。
- 回填：由 M2 **本地内容字节**复算 SHA-256；缺文件的旧资产 → 保持 NULL（**不伪造**）。
- 唯一性：`UniqueConstraint("tenant_scope", "content_sha256", name="uq_asset_items_scope_sha")`
  （SQLite 允许多 NULL；NULL 行不参与唯一）；共享内容（同 hash 两资产）→ skip/fail（§4.4）。
- 校验失败（字节 ≠ 记录 hash）→ fail（记录，不静默更新）。
- 降级：`DROP INDEX/约束 + DROP COLUMN`（SQLite 旧版需表重建，脚本给出重建步骤）。

### 4.3 真实租户绑定（非常量标签）

- **绑定字段**：`m2_receipt_binding.tenant_public_id`（单行初始化表）或配置项
  `materials.receipt_bound_tenant_public_id`；
- **初始化责任**：materials 初始化向导写入一次（首次部署/`create_all` 后）；
- **验证责任**：C3 consumer 每次调用前校验
  `worker_scope_tenant_public_id == receipt_bound_tenant_public_id`，**不相等即拒绝**（`TenantBindingError`）；
- **两租户反例**：合法租户 B（非绑定租户 A）调用 → worker scope 校验通过但绑定不等 → **拒绝**，
  不得因“单应用本地库”而共用同一本地 asset 标签；
- 跨租户同 hash 反例：A/B 两租户同 `content_sha256` → B 被绑定校验拒绝（非静默共享）。

### 4.4 单一失败表（round-150 §五.4 完整；hash 重复/校验失败已补）

| 情形 | 结论 |
|---|---|
| 同 `receipt_key` 已存在且 replay 内容匹配 | **replay**：返回既有 receipt |
| 同 `receipt_key` 已存在但内容不同（asset/evaluation/evidence） | **conflict**：旧 receipt 保持 |
| app 有资产、M2 无匹配 `content_sha256` | **skip**（未映射，留证据） |
| 内容文件缺失 / 裸 hash 无绑定（`content_sha256` IS NULL） | **skip**（缺文件/未绑定） |
| `content_sha256` 重复（两资产同 hash） | **fail**（hash 重复，无法唯一映射；记录，不静默取一） |
| SHA-256 校验失败（字节 ≠ 记录 hash） | **fail**（校验失败，记录） |
| worker scope ≠ 绑定租户 | **fail**（`TenantBindingError`，拒绝） |
| DB 错误 / 跨库写前/写后崩溃 | **fail**：本地事务回滚；重试按 `receipt_key` 查回同 receipt |

> 这些仅文档闭合；**M2/SKU 实际 DDL 与消费适配未实施**（C3 仍锁定）。

## 五、标准回归

| 项目 | 结果 |
|---|---|
| 十三文件全量回归（185 P0-1 + 85 批次 1 + 75 C1-a/b/c） | **345 passed in 172.08s**，无 pytest warning |
| C1-b/c 独立（calculator 24 + aggregation 20） | **44 passed in 0.65s** |
| selector/C1-a 独立（含 GV5 修订完整对象） | **31 passed** |
| 前端 TypeScript | `tsc --noEmit` exit 0 |
| T5 CLI | `T5-CID-ASSERT: PASS` |
| T9 六阶段 CI | `T9_CI_LAYERS=PASS` |

数据库终态：auth000002 / 31 app 表 / 7 auth 表 / 60 enum / 17 trigger / ad_report_snapshots=0 / tenants=0 /
auth_user=0 / workflow_runs=0 / temp_databases=0。

## 六、保留项与边界

- 选择器/事实层保持冻结；C1-a 不因本轮回退。
- C2 核心/fb 三黄金键、SKU append-only 方案沿用通过。
- C1-b/c 未记 COMPLETE（待 CDX 独立验收计算门）；C2/C3 接线、SKU/M2 实际 DDL、manual/workflow、批次 3
  继续锁定；M1/M3 范围变更仍登记待批。
- P0-2 完成边界：仅表示 app PG 上的离线领域闭环与 CI 门禁，不表示真实微信平台能力或全系统上线。

## 七、交接

请 Codex 独立验收 C1-b/c（manifest 单一真源/hash、calculator 五类与 typed outcome、aggregation 有效源集合与
三反例、作用域/粒度隔离、样本与依据一致；45+ 项测试与 345 全量回归），并复核 R152-1（receipt 身份去可变内容 +
material 黄金键）与 R152-2（SQLite 兼容 DDL + `content_sha256` 增列 + 真实租户绑定 + 完整失败表）文档闭合。
通过后裁决计算门；C2/C3 写入门未授权前继续契约锁定。

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-154-->