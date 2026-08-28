# M5 自动小店投放（商品托管）· v0.5 数据回写 — 交付说明

> 角色：数据回写子代理 ｜ 日期：2025 体系建立日 ｜ 状态：**待总工验收**
> 任务：v0.5 回流层「数据回写」——三类跨模块回写载体（纯函数 + JSON 文件 IO，**零数据库写**）：
> ① 选品「投放转化」维度（C-2 契约聚合，M5-OUT-01）② 素材评估回流（M5-OUT-02）③ review_reason 回写（M5-OUT-03）。

---

## 一、文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `backend/ads/feedback.py` | **新建** | 数据回写核心模块：类目聚合 ×1 + C-2 交换文件构建/写出 ×2 + 素材评估回流 ×1 + review_reason 回写 ×1 + category_map 加载 ×1（全部纯函数 + JSON IO，零 SQLAlchemy / 零 DB 依赖） |
| `backend/tests/test_ads_feedback.py` | **新建** | 28 个用例（数据驱动 + tmp_path，fixtures 文件内自建；含 **C-2 契约交叉验证用例**） |
| `_management/modules/m5-ads/REPORT_v0.5_feedback.md` | **新建** | 本交付说明 |

**未改动**：`backend/sourcing/*`、`backend/materials/*`、`backend/ads/` 全部既有文件
（`ad_backfill.py` / `integration.py` 仅只读参考）、既有测试、`conftest.py`（0 处改动）。
**零数据库写**：feedback.py 不 import 任何 DB/SQLAlchemy，本任务未写 m5-ads.db，
更未触碰 m1-sourcing.db / m2-materials.db。

---

## 二、接口说明（backend/ads/feedback.py）

### 1. `aggregate_by_category(product_rows: list[dict], category_map: dict[int, str]) -> dict`
按商品类目聚合托管转化数据（纯函数，锚点 = M1 `products.category`）：
- 输入 `product_rows`（M5 自有数据，调用方从 ad_campaigns + ad_report_snapshots 聚合后传入）：
  `[{product_id, gmv_fen, spend_fen, sample_count}]`（金额分 int）；`category_map`（来自 M1
  products 快照，经 data-audit/总控协调提供，本函数只接收映射不从任何库读取）；
- 按 category 聚合：`sales_amount=Σgmv_fen`、`spend=Σspend_fen`、`sample_count=Σsample_count`；
  `spend>0` 时 `roi = 总gmv/总spend`（float，>0）；
- **spend=0 的类目跳过**（ROI 无意义）→ 计入 skipped（`product_id` 取该类目首个商品）；
  **未知 product_id**（不在 category_map / 缺失）→ 跳过计入 skipped；
  弱样本（sample_count<5）**仍输出**（消费端 M1 过滤，本层不丢弃）；
- 返回 `{"data": {category: {"roi": float, "sales_amount": int, "sample_count": int}},
  "skipped": [{"product_id", "reason"}]}`；skipped 的 reason 取值：`spend=0` / `unknown product_id` / `invalid row`（防御）。

### 2. `build_exchange_file(category_data: dict, period_start: str, period_end: str, generated_at: datetime | str) -> dict`
C-2 交换文件构建（返回 dict 可 `json.dumps` 直写）：
- period 校验 YYYY-MM-DD（非法抛 ValueError）；generated_at：aware datetime（naive 自动补 UTC）
  或 ISO8601 字符串（含 Z/偏移，统一转 UTC）→ 序列化 ISO8601 字符串；
- 逐条校验（与 M1 `AdCategoryData` 口径一致）：**roi≤0 / sales_amount 非 int / sample_count 非 int
  → 抛 ValueError**（整批拒绝，避免 M1 消费端逐条 skipped）；
- 输出结构严格对齐 C-2：`schema_version=1` / `period{"start","end"}` / `generated_at` /
  `data{category: {"roi","sales_amount","sample_count"}}`。

### 3. `write_exchange_file(data: dict, path: str | Path) -> dict`
UTF-8（`ensure_ascii=False`，中文原样、无 BOM）写出，父目录自动创建，幂等覆盖；
返回 `{"path", "bytes", "written_at"}`（written_at = UTC ISO8601）。

### 4. `build_material_evaluation_file(material_rows: list[dict], generated_at=None) -> dict`
素材评估回流（M5-OUT-02 → M2）：
- 输入（M5 自有：从 ad_materials + ad_report_snapshots 关联，调用方聚合传入）：
  `[{asset_id, evaluation, impressions, gmv_fen, spend_fen}]`；
- 校验：evaluation ∈ {exploring, efficient, potential}（**镜像 M2
  materials.config.EVALUATION_VALUES**，非法抛 ValueError）；asset_id 缺失/非法抛 ValueError；
- 输出 `{"schema_version": 1, "generated_at": ISO8601, "data": [{"asset_id", "evaluation",
  "evidence": {"impressions", "gmv_fen", "spend_fen", "source_agent": "M5"}}]}`——evidence 为
  回流批次/报表快照摘要，对齐 M2 `EvaluationFeedbackService.receive_evaluation` 的 evidence 语义
  （M2 侧原样存 evidence_json；缺省指标补 0）。

### 5. `build_review_reason_file(campaign_failures: list[dict], generated_at=None) -> dict`
托管失败/不可投放原因回写（M5-OUT-03 → M1 products.review_reason，写入由 M1 消费端负责）：
- 输入 `[{product_id, review_reason, campaign_id, failed_at}]`；校验 product_id 非空、
  review_reason 非空字符串；failed_at 缺省 → 当前 UTC（naive 补 UTC、带偏移转 UTC）；
- 输出 `{"schema_version": 1, "generated_at": ISO8601, "data":
  [{"product_id", "review_reason", "campaign_id", "failed_at"}]}`（campaign_id 可选，缺省输出 None 供审计追溯）。

### 6. `load_category_map(path: str | Path | None) -> dict[int, str]`
product→category 映射加载（供调用方把 M1 快照映射喂给 aggregate_by_category）：
- 支持两种形状：`{"product_id 字符串": "category"}`（dict）或
  `[{"product_id": 123, "category": "..."}]`（list）；product_id 统一转 int；
- 无文件 / JSON 损坏 / 结构非法 → 返回 `{}`（log warning，不抛）；单条非法（id 非数字/缺字段/空类目）
  → 跳过该条并 log warning（尽力而为，不整份丢弃）。

---

## 三、测试结果

命令（P-001 + P-011：独立 basetemp `.pytest-tmp-m5`，未共用 `.pytest-tmp`；均于 backend/ 下执行）：

```
python -m pytest tests/test_ads_feedback.py -q --basetemp=".pytest-tmp-m5"
→ 28 passed in 0.63s

python -m pytest tests/test_ads_feedback.py tests/test_ads_repo.py -q --basetemp=".pytest-tmp-m5"
→ 40 passed（与既有 repo 协同不破坏）

python -m pytest tests/test_ads_feedback.py tests/test_ads_repo.py tests/test_ads_tables.py tests/test_ads_settings.py tests/test_ads_executor.py tests/test_ads_stop_loss.py tests/test_ads_report.py -q --basetemp=".pytest-tmp-m5"
→ 158 passed（全 ads 套件：既有 130 + 新增 28，零回归）
```

用例覆盖（28 个）：
- aggregate_by_category 8：同/异类目聚合、spend=0 类目跳过（含部分 spend=0 商品仍计入）、弱样本仍输出、
  未知商品跳过、空输入、混合跳过与保留；
- build_exchange_file 5：C-2 结构对齐（顶层/period/data 键集合 + json 直写直读）、generated_at 变体
  （naive 补 UTC / +08:00 转 UTC / Z 字符串）、非法 period 抛错、roi≤0 抛错（含 NaN/bool/缺失）、
  sales_amount/sample_count 非 int 抛错；
- write_exchange_file 3：UTF-8 中文读回 + 无 BOM、幂等覆盖（bytes 精确）、父目录自动创建；
- build_material_evaluation_file 4：evidence 结构（source_agent=M5）、枚举校验（合法 3 值 + 非法抛错 +
  **与 M2 EVALUATION_VALUES 镜像对齐**）、asset_id 缺失/非法、缺省 generated_at 为当前 UTC；
- build_review_reason_file 3：结构 + 缺省 failed_at、failed_at/generated_at 变体（naive/偏移/Z/非法）、
  字段校验（product_id/review_reason 缺失/空）；
- load_category_map 4：dict 形状、list 形状、无文件/损坏/None 返回 {}、坏条目跳过；
- **C-2 契约交叉验证 1**（见下节）。

---

## 四、C-2 契约交叉验证结果（关键验收点）

**M1 消费端可直接消费本层产出**（只读校验，不写 M1 库）：

1. 测试内验证（`test_c2_cross_validate_with_m1_consumer`）：构造 `build_exchange_file` 示例
   （中文类目 + 弱样本 +08:00 时间）→ `write_exchange_file` 写到 tmp → M1 消费端
   `from sourcing.ad_backfill import load_exchange; e = load_exchange(path)` 校验通过：
   `e.schema_version == 1`、`period.start/end` 原样、`generated_at` 归一化 aware、
   `data` 逐类目字段口径（roi/sales_amount 分 int/sample_count）全部通过 M1 `AdExchangeFile`
   结构校验与 `AdCategoryData` 条目口径（roi>0、sales_amount int≥0、sample_count int≥0），
   弱样本（sample_count=3）M1 保留不丢弃。
2. 命令行验证（验收命令等价）：
   ```
   python -c "from ads.feedback import ...; d=build_exchange_file({'收纳整理': {...}}, ...); write_exchange_file(d, p); from sourcing.ad_backfill import load_exchange; e=load_exchange(p); assert e is not None and e.schema_version==1"
   → C-2 交叉验证 OK: schema_version=1, category= ['收纳整理']
   ```
3. import 检查：`python -c "from ads.feedback import aggregate_by_category, build_exchange_file, build_material_evaluation_file, build_review_reason_file"` → ok（另含 write_exchange_file / load_category_map / EVALUATION_VALUES）。

---

## 五、M5-OUT-01~03 产出结构

| ID | 方向 | 载体文件（调用方落盘，建议 `_management/data-exchange/`） | 产出结构（本层函数产出） |
|---|---|---|---|
| M5-OUT-01 | M5 → M1 | `m5-ad-conversion.json`（C-2） | `{"schema_version": 1, "period": {"start","end"}, "generated_at": ISO8601, "data": {category: {"roi", "sales_amount"(分 int), "sample_count"}}}`；弱样本仍输出；spend=0/未知商品入 skipped |
| M5-OUT-02 | M5 → M2 | `m5-material-evaluation.json` | `{"schema_version": 1, "generated_at": ISO8601, "data": [{"asset_id", "evaluation"(exploring/efficient/potential), "evidence": {"impressions", "gmv_fen", "spend_fen", "source_agent": "M5"}}]}` |
| M5-OUT-03 | M5 → M1 商品主表 | `m5-review-reason.json` | `{"schema_version": 1, "generated_at": ISO8601, "data": [{"product_id", "review_reason", "campaign_id", "failed_at"}]}` |

调用方编排建议（不在本任务范围）：从 ad_campaigns + ad_report_snapshots 关联聚合
product_rows / material_rows / campaign_failures → 调本层纯函数 → `write_exchange_file`
落盘到 `_management/data-exchange/` → 通知总控经 data-audit 转达 M1/M2 消费端导入
（M1 侧入口：`sourcing.ad_backfill.backfill(db, path)`，已会签可消费）。

---

## 六、宪法与纪律自查

| 纪律 | 自查 |
|---|---|
| 零数据库写 / 不碰其他模块库 | ✅ feedback.py 无任何 SQLAlchemy/DB import，纯函数 + JSON IO；未写 m5-ads.db，更未碰 m1-sourcing.db / m2-materials.db |
| 禁改既有文件 | ✅ 仅新增 feedback.py + test_ads_feedback.py；sourcing/materials/ads 既有文件 0 改动；conftest.py 0 改动 |
| 禁 git / 禁安装 | ✅ 未运行任何 git 命令，未安装任何软件 |
| 禁明文密钥 | ✅ 本任务不涉及凭证；错误消息不含输入值（仅原因/字段名/类目名） |
| 口径（DA-001/REC-005） | ✅ 金额=分 int；时间=UTC 带时区（ISO8601）；枚举英文（evaluation=exploring/efficient/potential） |
| UTF-8 无 BOM | ✅ write 工具 UTF-8 无 BOM，未用 PowerShell 写中文（测试有读回断言） |
| 测试 basetemp | ✅ 全部命令带独立 basetemp `.pytest-tmp-m5`（P-001 + P-011） |

---

## 七、偏差与说明

1. **`roi` 输出为全精度 float**（任务书允许「保留 2 位或 float」）：`spend>0` 时
   `roi = 总gmv/总spend` 原样输出（如 3.0/4.0 精确、3.2 序列化即 3.2），避免四舍五入把
   极小比值打成 0.0 导致 build_exchange_file 误拒；M1 侧为 float 存储无精度要求。
2. **spend=0 类目的 skipped 条目 `product_id` 取该类目首个商品**（便于追溯，任务书仅要求
   `{"product_id", "reason"}` 结构）；另增防御性 reason `invalid row`（非 dict 行/金额非法）。
3. **build_exchange_file 对 roi≤0 整批抛 ValueError**（严格按任务书）：gmv=0+spend>0 的
   类目会命中此路径——若后续业务需要「花了钱没成交」也留痕，建议在调用方过滤或消费端
   按条目 skipped 处理（M1 `apply_exchange` 本就单条拒绝不整批崩），本层口径不变。
4. **`EVALUATION_VALUES` 为 M2 枚举的本地镜像**（`("exploring", "efficient", "potential")`）：
   不跨包 import materials（保持 ads 包零依赖、防 materials 异常连带），测试内有镜像对齐断言
   （`set(ads.feedback.EVALUATION_VALUES) == set(materials.config.EVALUATION_VALUES)`）。
5. **review_reason 文件的 campaign_id 可选**（缺省输出 None）：任务书输出结构含该字段，
   校验只要求 product_id/review_reason 非空；None 供审计追溯，消费端可忽略。
6. **素材评估 evidence 缺省指标补 0**：impressions/gmv_fen/spend_fen 缺省 0，保证 evidence
   四字段结构完整（对齐 M2 evidence_json 语义）；调用方聚合时应尽量传全。
7. 三类文件的**实际落盘路径**（`_management/data-exchange/`）与调度触发由调用方/总控编排，
   本层只提供纯函数 + 写出工具（任务书范围）。

---

## 八、data-audit 登记建议文本（M5 侧数据提供记录，请总工转录入 `_management/logs/data-audit.md`）

```markdown
## DA-00X ｜ M5 数据回写提供登记（提供方：M5 总工 ｜ 接收方：M1/M2）

- **内容**（M5 v0.5 回流层产出，载体 data-exchange JSON，由总控协调落盘与转达）：
  1. M5-OUT-01 → M1 选品：类目级托管转化数据（契约 C-2 `m5-ad-conversion.json`）——
     category / roi / sales_amount(分 int) / sample_count / period{start,end} / generated_at(ISO8601 UTC)，
     M5 按「与 products.category 完全一致」的类目名聚合；弱样本（sample_count<5）仍输出由 M1 消费端过滤；
     spend=0 类目与未知商品不入 data（skipped 留痕）。
  2. M5-OUT-02 → M2 素材：素材评估回流（`m5-material-evaluation.json`）——
     asset_id / evaluation(exploring/efficient/potential) / evidence{impressions, gmv_fen, spend_fen, source_agent=M5}，
     对齐 M2 EvaluationFeedbackService.receive_evaluation evidence 语义（幂等审计）。
  3. M5-OUT-03 → M1 商品主表：托管失败/不可投放原因（`m5-review-reason.json`）——
     product_id / review_reason / campaign_id / failed_at(UTC)，写入 products.review_reason 由 M1 消费端负责。
- **字段明细与口径**：见 `_management/modules/m5-ads/context/README.md`（数据字典）与
  `context/data-requests.md`（M5-OUT-01~03）；口径按 DA-001 统一（金额=分 int、时间=UTC 带时区、枚举英文）。
- **校验结果**：
  1. C-2 契约会签交叉验证通过——M5 产出经 M1 消费端 `sourcing.ad_backfill.load_exchange` 校验
     `schema_version=1` 且逐类目条目口径通过（roi>0、sales_amount 分 int、sample_count int）；
  2. M5 侧 28 用例全绿 + 全 ads 套件 158 passed；
  3. 本登记为数据提供记录，M5 未写任何其他模块库；落盘与转达由总控协调。
- **总控核对结论**：（待总控核对字段/单位/时间格式后填写）
```
