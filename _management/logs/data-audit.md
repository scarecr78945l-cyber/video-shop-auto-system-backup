# 数据联动审计（Data Exchange Audit）

> 所有跨模块数据调取、提供、口径核对记录。总控负责最终核对。
> 规则见宪法第 5 节。只追加。

## 审计约定

- 数据口径字段：字段名、单位、时间格式、主键来源必须在双方 `context/` 数据字典中一致。
- 数据交接载体：`_management/data-exchange/<交换名>.json`（由总控创建目录）。
- 每次调取至少登记：申请方、提供方、数据内容、校验结果、总控核对结论。

---

## 2025 体系建立日 ｜ M3 申请数据联动（申请方：M3 总工 ｜ 提供方：M1/M2/M5）

- **内容**：
  1. 从 M2（素材收集）获取：原始素材（asset_id / asset_type / source_platform / source_url / md5 / phash / file_path / duration / resolution / size / tags_json / heat_score / evaluation）——视频二创原始输入与主图参考，只读；
  2. 从 M1（选品）获取：商品信息（product_id / taobao_original_title / category / sku_spec_json）——标题机械清洗与口播稿依据，只读；
  3. 从 M5（投放）回写：投放效果（platform_material_id / exposure / clicks / spend / orders / roi / diagnosis_json）——评估标签（高效/潜力/探索期）与模板参数重训练输入；
  4. M3 对外提供：M4（主图 5 张 + 详情图 ≥3 + 标题 15–35 字符）、M5（9:16 视频多版本 + 投放文案/角标 + evaluation 排序）。
- **字段明细与口径**：见 `_management/modules/m3-optimization/context/README.md`（数据字典/跨模块契约）与 `context/data-requests.md`。
- **校验结果**：待总控核对口径并转达 M1/M2/M5 总工。
- **总控核对结论**：（待填）

---

## 登记区（暂无其他记录）

<!-- 总工申请数据联动时在此追加 -->

---

## DA-001 ｜ 全局金额/时间口径统一（总控裁决 REC-005）

- **申请方**：M5 总工 ｜ **冲突发现**：M0 数据字典初稿「金额=元、时间=UTC」；M4/M5 上下文「金额=分(int)、时间=UTC+8」。
- **总控裁决**：
  1. **金额一律以「分」为整数存储**（与微信小店 channels API、投放后台口径一致），展示层由前端/报表转「元」；数据字典统一「金额单位=分(int)」。
  2. **时间一律 UTC（ISO8601 带时区）存储**，展示层转 UTC+8（东八区）；时间戳字段名后缀 `_at`。
  3. M0 修订其 `context/README.md` 数据字典口径；M1~M5 全部遵循。
- **核对结论**：M4（分）✅、M5（分）✅ 与裁决一致；M0 需修订；M1/M2/M3 开发时遵循。
- **涉及模块**：全部。

## DA-002 ｜ M5 跨模块数据需求（待转达）

- **申请方**：M5 总工 ｜ **需求**：① M1 托管候选池（选品 TopN + 销售中状态）；② M2/M3 素材库（assets + 评估标签 exploring/efficient/potential）；③ M4 上架成功商品列表（销售中确认）。
- **状态**：M1 筹备收尾中；M2/M3 已启动开发；待相关模块就绪后由总控转达，数据载体 `_management/data-exchange/`。

## DA-003 ｜ M3 申请数据联动（申请方：M3 总工 ｜ 提供方：M1/M2/M5）

- **内容**：
  1. 从 M2（素材收集）获取：原始素材（asset_id / asset_type / source_platform / source_url / md5 / phash / file_path / duration / resolution / size / tags_json / heat_score / evaluation）——视频二创原始输入与主图参考，只读；
  2. 从 M1（选品）获取：商品信息（product_id / taobao_original_title / category / sku_spec_json）——标题机械清洗与口播稿依据，只读；
  3. 从 M5（投放）回写：投放效果（platform_material_id / exposure / clicks / spend / orders / roi / diagnosis_json）——评估标签与模板参数重训练输入；
  4. M3 对外提供：M4（主图 5 张 + 详情图 ≥3 + 标题 15–35 字符）、M5（9:16 视频多版本 + 投放文案/角标 + evaluation 排序）。
- **校验结果**：口径已按 DA-001 统一（金额=分、时间=UTC）；字段明细见 M3 context/README.md。
- **总控核对结论**：✅ 口径通过；待 M1 筹备完成、M2/M5 相应模块就绪后由总控转达。

---

## DA-004 ｜ M2 数据联动登记（申请方：M2 总工 ｜ 提供方：M3/M5）

- **内容**：
  1. **从 M5（投放）接收**：evaluation 评估标签回写（asset_id + evaluation 枚举 exploring/efficient/potential + evidence）——写 `asset_evaluations` 审计 + 更新 `asset_items.evaluation`，频率=日快照批量；
  2. **从 M3（素材优化）接收**：上传小店素材库结果回填（platform_material_id + upload_status=uploaded）——写 `asset_uploads` + 更新 `asset_items`，频率=每次上传任务完成；
  3. **M2 对外提供**：M3（原始素材 asset_id/asset_type/source_platform/source_url/md5/phash/file_path/duration/resolution/size/tags_json/heat_score/derivation_note，**门禁 compliance_status=passed**，用途=二创原料）；M5（素材查询/绑定 asset_id/file_path/platform_material_id/upload_status=uploaded/规格字段，用途=投放优选绑定）。
- **字段明细与口径**：见 `_management/modules/m2-materials/context/README.md`（数据字典/3.x 跨模块契约）与 `context/data-requests.md`（四类登记）；evaluation 枚举与 M5 共口径（exploring/efficient/potential）；时间 UTC（DA-001）。
- **服务层**：`backend/materials/integration.py`（EvaluationFeedbackService / MaterialUploadService，已验收 17 例）。
- **校验结果**：M2 侧实现与测试已完成（evaluation 回写幂等、上传抽象 mock 全链路）；待 M3/M5 侧就绪后由总控协调联调。
- **总控核对结论**：（待填）

---

## DA-005 ｜ M4 → M5 数据提供登记（销售中商品候选池）

- **提供方**：M4 总工（m4-listing）｜ **接收方**：M5（小店投放/商品托管）。
- **提供内容**：销售中商品候选池——`listing_tasks` 中 `status=listed` 且 `link_verified_at` 非空 且 `product_link` 非空 的任务（**仅已上架商品**，07 文档六节；草稿/审核中/驳回/人工/待重提一律不出现）。
- **字段口径**：`product_id` / `task_id` / `title` / `category_id` / `product_link`（已验证真实链接，R22）/ `link_verified_at` / `price_min_cents` / `price_max_cents`（金额单位=分 int，DA-001）；title/category_id 关联 `listing_spus`（无 SPU 置空），价格区间聚合 `listing_skus.price_cents`（无 SKU 置 None）。
- **提供方式**：`CandidatePool.get_sale_candidates()` 只读查询（纯只读、幂等，不修改任何任务状态）；按 `link_verified_at` 升序（先上架先出）；`limit` 生效且不超过 `candidate_batch_max`（≤50 错峰批量，P-006），超出截断并附 evidence 提示。
- **频率**：按需 / 批次错峰——上架批次与 M5 托管提交互斥时段 `peak_avoid_window`（默认 10:00–12:00，左闭右开；start>end 跨天窗口按环形处理，如 22:00→02:00）。
- **负责人**：M4 总工。
- **校验**：仅已上架商品（07 文档六节）；口径对齐 `_management/modules/m4-listing/context/README.md` 5.3 节「向 M5 提供」。
- **总控核对结论**：（待总控核对）

---

## DA-006 ｜ M5 数据回写提供登记（提供方：M5 总工 ｜ 接收方：M1/M2）

- **内容**（M5 v0.5 回流层产出，载体 data-exchange JSON，由总控协调落盘与转达；M5 未写任何其他模块库）：
  1. **M5-OUT-01 → M1 选品**：类目级托管转化数据（契约 C-2，载体 `m5-ad-conversion.json`）——`category / roi / sales_amount(分 int) / sample_count / period{start,end} / generated_at(ISO8601 UTC)`；M5 按「与 products.category 完全一致」的类目名聚合（product→category 映射经协调提供）；弱样本（sample_count<5）仍输出由 M1 消费端过滤；spend=0 类目与未知商品不入 data（skipped 留痕）。**消费端**：M1 `sourcing.ad_backfill.backfill(db, path)`（已会签）。
  2. **M5-OUT-02 → M2 素材**：素材评估回流（载体 `m5-material-evaluation.json`）——`asset_id / evaluation(exploring/efficient/potential) / evidence{impressions, gmv_fen, spend_fen, source_agent=M5}`；对齐 M2 `EvaluationFeedbackService.receive_evaluation` evidence 语义（幂等审计，与 DA-004 第 1 项互为对端）。
  3. **M5-OUT-03 → M1 商品主表**：托管失败/不可投放原因（载体 `m5-review-reason.json`）——`product_id / review_reason / campaign_id / failed_at(UTC)`；写入 `products.review_reason` 由 M1 消费端负责。
- **字段明细与口径**：见 `_management/modules/m5-ads/context/README.md`（数据字典）与 `context/data-requests.md`（M5-OUT-01~03）；口径按 DA-001 统一（金额=分 int、时间=UTC 带时区、枚举英文）。
- **实现层**：`backend/ads/feedback.py`（aggregate_by_category / build_exchange_file / write_exchange_file / build_material_evaluation_file / build_review_reason_file / load_category_map，纯函数+JSON IO，零 DB 写）。
- **校验结果**：
  1. **C-2 契约会签交叉验证通过**——M5 产出经 M1 消费端 `sourcing.ad_backfill.load_exchange` 校验 `schema_version=1` 且逐类目条目口径通过（roi>0、sales_amount 分 int、sample_count int），弱样本保留（总工独立复跑确认）；
  2. M5 侧 28 用例全绿 + 全 ads 套件 **158 passed**（零回归）；
  3. M5-OUT-02/03 结构对齐 M2/DA-004 契约，待 M2 侧联调消费（receive_evaluation 已就绪）。
- **总控核对结论**：（待总控核对字段/单位/时间格式后填写；C-2 会签建议双方总工在文件头签字）

---

## DA-007 ｜ M3 消费 M5 投放效果回写（v1.1-① 联调，评估标签回流摄取）

- **提供方**：M5 总工（ad_report_snapshots 口径）｜ **接收方**：M3 总工（评估标签回流消费）。
- **载体**：经总控协调的 data-exchange JSON（规划 `_management/data-exchange/m5-to-m3-evaluation.json`）；M3 不直读 M5 库（宪法第 5 节）。
- **契约字段**（对齐 M5 context 数据字典 + DA-001）：
  - `platform_material_id`（= M5 素材记录 material_id = M3 opt_video_variants.platform_material_id，回写主键）；
  - `report_date`（UTC YYYY-MM-DD，幂等键 (variant_id, report_date)）；
  - `impressions`（曝光 int）/ `clicks`（可选，M5 快照暂缺省 0 → CTR 分量按 0，评分由 ROI/诊断主导）；
  - `spend_cents` / `gmv_cents`（金额「分」int，DA-001）→ M3 换算：spend 元 = /100、roi = gmv/spend；
  - `orders`（可选缺省 0）；`diagnosis`（M5 中文枚举：优秀/良好/1项待优化/N项待优化 → ab.scoring 兼容）。
- **M3 消费入口**：`backend/optimization/ab/ingest.py`（ingest_m5_record / ingest_m5_batch）——unmatched material_id 不落库（失败隔离），幂等回写 opt_evaluation_feedback，驱动评估标签与模板重训练。
- **校验结果**：联调契约测试 `test_optimization_m5_integration.py` **5 用例全绿**（金额分→元换算、ROI 计算、中文诊断兼容、unmatched 隔离、幂等、排序消费）；全量回归 **1021 passed, 2 skipped**（M3 全范围全绿）。
- **总控核对结论**：（待总控核对字段/单位后填写；建议 M5 侧同步登记对端，双方在 data-exchange JSON 文件头会签）

---

## DA-008 ｜ A6 数据字典定稿 + 跨模块契约会签（申请方：M0 总工 ｜ 涉及 M1~M5）

- **会签目的**：全局数据字典口径定稿 + 共享基座契约核对（M0 基座 v0.6 已就绪：五表 DDL/队列/调度器/风控/脱敏）。M0 侧基准已定稿——`_management/modules/m0-foundation/context/README.md`（全局字段口径表）+ `database/README.md`（五表 DDL v0.2）。
- **全局数据字典基准（各方确认口径一致）**：
  1. 金额一律「分」int 存储（含 JSON 内金额），展示层转元（DA-001 REC-005，M4/M5 已 ✅）；
  2. 时间一律 UTC（ISO8601 带时区）存储，时间戳字段后缀 `_at`，展示层转 UTC+8（DA-001）；
  3. 主键 ID=自增整数；指纹=SHA-256 hex（64 位小写）；枚举=小写下划线 snake_case（英文，如 error_code/status/evaluation）；
  4. 错误码唯一权威=`error_codes` 表（09 文档 8+1 码：VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/TIMEOUT/NO_MATCH/INSUFFICIENT_REFERENCES/PLATFORM_REJECT/UNEXPECTED/PAGE_CHANGED）。
- **共享表契约（读写边界，M0 拥有，全员只读）**：`workflow_jobs`/`tasks`/`logs`/`app_config`/`error_codes`——写入经 M0 队列 API/总控协调；其他模块只读（宪法第 4 节）。
- **分模块核对项（请各模块总工会签确认）**：
  - **M1（选品）**：① workflow_jobs 入队/查询契约（product_id/stage/generation_version 幂等键）是否对接；② app_config 键 `category.whitelist`/`scoring.weights` 口径（M1 pipeline 已接线读取）；③ m1_ad_conversion_cache/ingests 金额=分 int、generated_at UTC 校验（M1 S1b 已实现）。
  - **M2（素材）**：① downloader 错误分类（RATE_LIMIT/TIMEOUT/NO_MATCH/AUTH_REQUIRED/PLATFORM_REJECT/UNEXPECTED）与 M0 error_codes 表码表一致确认；② asset_* 表时间 _at UTC/金额（如有）分 int；③ evaluation 枚举 exploring/efficient/potential 共口径。
  - **M3（优化）**：① app_config 只读（`risk.high_risk_categories` 扩展点预留）；② opt_* 表时间 _at UTC、金额分 int（如有）；③ evaluation 枚举与 M2/M5 共口径（DA-003/DA-007 已互认）。
  - **M4（上架）**：① listing_tasks 幂等键 (product_id, stage, generation_version) 与 M0 workflow_jobs 同构确认（是否双写/引用 M0 队列，由总控裁定）；② listing 状态机错误码映射（09 码表子集）与 M0 error_codes 一致确认；③ 金额分 int（price_cents）/时间 _at UTC 确认。
  - **M5（投放）**：① **风控共享规则引用基座**——M0 `foundation/risk.py`（S7 预算三重/S1·S3 止损/S5 余额/S8 全停）与 M5 `ads/stop_loss.py` 同签名同语义，M5 后续 import 基座替换自有实现（总控协调）；② ad_* 表金额分 int/时间 _at UTC 确认（DA-001 已 ✅）；③ app_config 只读确认。
- **状态**：M0 侧基准已定稿；**待总控转达 M1~M5 总工会签**，各方确认后回传 M0，完成会签后更新 progress.md/decisions.md（A6）并推进 A7 集成联调。
- **总控核对结论**：（待填）

### DA-008 ｜ M1 会签意见（2026-08-29 ｜ M1 总工）

按 4 项核对逐条确认/提出异议（已核实 M1 代码实现）：

1. **全局数据字典口径** ✅ **确认**——M1 已符合：金额一律分 int（`ad_backfill` sales_amount INTEGER 分、`m1_ad_conversion_cache.sales_amount` int、示例交换文件校验 int ge=0）；时间一律 UTC（`models.utcnow` aware UTC + `DateTime(timezone=True)`，`_at` 后缀：generated_at/ingested_at）；主键自增整数（tables.py 全部 Integer PK autoincrement）；指纹 SHA-256 hex（`dedup.py:33` `hashlib.sha256(...).hexdigest()`，String(64) 吻合）；枚举 snake_case 英文（ComplianceState: hard_reject/candidate/manual_review；state: pool/manual_review/rejected）。
2. **队列入队契约（product_id/stage/generation_version 幂等键）** ✅ **确认**——M1 当前**无独立 workflow_jobs 入队实现**：选品产出商品池（products 表 state=pool），入队由上架链 M4 消费；M1 调度器走 source+board 账本（source_board_states），不经 workflow_jobs。若后续 M1 需驱动 workflow_jobs（如询价/补全任务入队），将严格使用 M0 幂等键 product_id/stage/generation_version 并只经 M0 队列 API 写入。
3. **app_config 键约定** ⚠️ **提出对齐项**——M1 已实现键名为 **`category_whitelist`**（下划线，`pipeline._load_category_whitelist` 第 57 行已接线，`test_compliance_appconfig.py` 6 例测试覆盖），与 M0 定稿 **`category.whitelist`**（点分隔）不一致。**M1 表态：跟随 M0 定稿，将 `category_whitelist` → `category.whitelist`（改 pipeline.py 1 处 + 测试键名 + context/README 契约），在 S3c 验收后一并修改并跑回归**（成本低，请总控裁定后执行）。`scoring.weights`：M1 打分权重现于 `config.scoring`（ScoringConfig 配置化，环境变量 SOURCING_* 可覆盖），**尚未接 app_config 读取**；确认「后续迭代接入 app_config 的 `scoring.weights` 键」（当前以 config 默认/环境变量为准，功能不受影响）。
4. **错误码唯一权威 = M0 error_codes 表** ✅ **确认**——M1 使用的错误码（AUTH_REQUIRED / VERIFICATION_REQUIRED / RATE_LIMIT / TIMEOUT / NO_MATCH / PLATFORM_REJECT / UNEXPECTED / **PAGE_CHANGED**）全部在 09 文档 8+1 码表内（M0 基准已含 PAGE_CHANGED 扩展码，M1 采集器 5 处使用该码语义对齐 P-003，与 M0 一致 ✅）。

**结论：M1 会签确认（4 项中 2 项确认、2 项有对齐动作或补充说明），唯一待执行项为 app_config 键名对齐（category_whitelist → category.whitelist，S3c 后执行）。** 其余核对项（③金额/时间/主键/指纹/枚举、④错误码）M1 实现与 M0 基准一致，无需改动。

---

### DA-008 ｜ M2 会签确认（2025 体系建立日 ｜ M2 总工）

按 M2 分模块核对项（DA-008 第 129 行）逐条确认（已核实 `backend/materials/` 实现）：

1. **downloader 错误分类与 M0 error_codes 码表一致** ✅ **确认**——`backend/materials/downloader.py` 使用 RATE_LIMIT/TIMEOUT/NO_MATCH/PLATFORM_REJECT/AUTH_REQUIRED/VERIFICATION_REQUIRED/UNEXPECTED，全部在 09 文档 8+1 码表内；collectors（tiktok_wrapper/wechat_video/taobao_refs/board_image_cache）、tagger、integration、pipeline 全部对齐该码表。⚠️ **补充说明**：M2 未采用 `PAGE_CHANGED` 码（页面结构变化统一映射 `PLATFORM_REJECT` + HTML 快照证据，见 B2'/B1 的 page_changed 实现）；`INSUFFICIENT_REFERENCES` 为选品专用码（M2 不涉及）。
2. **asset_* 时间/金额口径** ✅ **确认**——时间一律 TEXT ISO8601 UTC + `_at` 后缀（created_at/updated_at/next_run_at/lease_expires_at/claimed_at）；**金额字段：M2 素材库无金额字段**（`heat_score` 为 REAL 热度归一化分数，非金额，无冲突）。⚠️ **指纹差异登记**：M2 素材指纹=**MD5 32 位小写 hex**（`asset_items.md5`，05 文档双去重指定，判重非安全用途）+ 感知哈希 phash（图片 16 位 hex / 视频关键帧 JSON 数组），**非 SHA-256**——与 M0「指纹=SHA-256 hex」口径不同源（M0 指纹规范适用于商品/通用指纹）；素材文件判重用 MD5 为行业惯例且 05 文档权威，**若总控要求全系统统一 SHA-256 请裁决**（不阻塞，M2 表结构已定型；如需切换仅涉及 `dedup.compute_md5` 与 `asset_items.md5` 列语义）。
3. **evaluation 枚举共口径** ✅ **确认**——`exploring`（探索期）/`efficient`（高效）/`potential`（潜力），`asset_items.evaluation` 与 `asset_evaluations.evaluation` 均有 CheckConstraint 锁定（tables.py ck_asset_items_evaluation/ck_asset_evaluations_evaluation），与 M3/M5 共口径（DA-001/DA-003/DA-004/DA-007 互认）；`EVALUATION_VALUES` 常量与 config.py 同口径。

**结论：M2 会签确认（3 项全部确认，含 2 处口径差异登记：PAGE_CHANGED 未采用、素材指纹 MD5 非 SHA-256，均不阻塞，SHA-256 统一与否请总控裁决）。** 佐证：`backend/materials/tables.py`（7 表 DDL）、`downloader.py`（码表）、`integration.py`（EvaluationFeedbackService 为 M5-OUT-02 对端，已就绪）。

---

### DA-008 ｜ M4 会签确认（2025 体系建立日 ｜ M4 总工）

按 M4 分模块核对项（DA-008 第 131 行）逐条确认（已核实 `backend/adapters/wechat_openapi.py`、`backend/services/listing_gate.py`、`backend/listing/` 实现）：

1. **金额分 int / 时间 UTC（_at）/ 主键自增 / 枚举 snake_case 英文 —— ✅ 确认**：
   - 金额：`listing_skus.price_cents/cost_cents`、`candidate_pool.price_min/max_cents`、adapter `update_price(int(price_cents))` 全部整数「分」（DA-001/REC-005）；
   - 时间：`listing_tasks/listing_op_logs/listing_audit_records` 等时间戳 `_at` 后缀 TEXT ISO8601 UTC（`models.utcnow_iso`），展示层转 UTC+8；
   - 主键：自增表（`listing_upload_assets.asset_id`/`listing_op_logs.log_id`/`listing_audit_records.audit_record_id` AUTOINCREMENT）+ 业务主键表（`listing_tasks.task_id`/`listing_spus.spu_id`/`listing_skus.sku_id`，与 M0 workflow_jobs 任务表同模式）；
   - 枚举：状态机 `status`（pending/creating/draft/platform_auditing/listed/rejected/retry_candidate/manual/failed）、`REJECT_CATEGORIES`（title/category/qualification/image/price/content_compliance/other）全部小写下划线英文。
2. **listing_tasks 幂等键与 M0 workflow_jobs 同构 —— ✅ 确认**：`UNIQUE(product_id, stage, generation_version)`（P3 `listing/tables.py` 已实现，与 M0 DDL v0.2 同构）；M4 任务经 `workflow_jobs.stage=listing_upload` 关联，双写/引用 M0 队列的落点方式由总控裁定（M4 侧幂等键同构已满足，无异议）。
3. **状态机错误码映射与 M0 error_codes 一致 —— ✅ 确认（会签发现一处差异已当场修正）**：
   - M4 全链错误码（adapter `ERROR_CODES`、state_machine/pipeline/ui_fallback/rejection）与 09 文档 8+1 码表一致：VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/TIMEOUT/NO_MATCH/INSUFFICIENT_REFERENCES/PLATFORM_REJECT/UNEXPECTED/PAGE_CHANGED；
   - **差异修正**：会签核对发现 `backend/listing/ui_fallback.py` 原用 `error_code="page_changed"`（小写）→ 已改为 **`PAGE_CHANGED`**（对齐 M0 权威码表，注释注明 DA-008）；`backend/adapters/wechat_openapi.py` ERROR_CODES 集合补充 `INSUFFICIENT_REFERENCES`/`PAGE_CHANGED` 至全量 8+1 码（含退避 `INSUFFICIENT_REFERENCES=120s`）；测试断言同步（test_listing_fallback.py 1 处）；
   - 修正后 M4 全量复跑：**131 passed**（12.80s，`--basetemp=".pytest-tmp-m4"`）无回归。
   - ⚠️ 补充说明（与 M2 同向）：M4 目前实际产出码为 09 文档基础 7 码 + PAGE_CHANGED（ui_fallback）；`INSUFFICIENT_REFERENCES` 为选品专用码 M4 不产出，仅入集合保证非法码归一正确。

**结论：M4 会签确认（3 项全部确认，含 1 处已当场修正：page_changed → PAGE_CHANGED 对齐权威码表）。** 回传 M0；同意推进 A7 集成联调（M4 侧 mock 模式全链路就绪，live 待官方 OpenAPI 契约核对 T1~T7 与主体/资质开通）。佐证：`backend/listing/tables.py`（幂等键）、`ui_fallback.py`（PAGE_CHANGED）、`adapters/wechat_openapi.py`（ERROR_CODES 8+1 码）。

---

## 总控会签裁决记录（REC-009 ~ REC-011）

### REC-009 ｜ M2 两处口径差异裁决（2026-08-29 ｜ 总控）
1. **PAGE_CHANGED → PLATFORM_REJECT 映射**：✅ 批准（M2 未采用 PAGE_CHANGED 码，页面结构变化统一映射 PLATFORM_REJECT + HTML 快照证据，合理且与 P-003 留证要求一致；M0 error_codes 保留 PAGE_CHANGED 供 M1/M4 使用）。
2. **素材指纹 MD5 + phash**：✅ 批准保留（双去重判重用途，05 文档权威）；数据字典最终口径：**安全/证据指纹=SHA-256 hex（商品/通用/证据摘要），去重指纹=MD5 32 位 hex + phash（素材/文件判重）**——两类指纹并存，各模块按用途选用。

### REC-010 ｜ M1 app_config 键名对齐裁决（2026-08-29 ｜ 总控）
- **批准 M1 跟随 M0 定稿**：category_whitelist → **category.whitelist**（改 pipeline.py + 测试键名 + context/README 契约），M1 在 S3c 验收后执行并跑回归；scoring.weights 键确认 M1 后续迭代接入（当前 config 默认/环境变量为准）。

### REC-011 ｜ M4 幂等键双写问题裁定（2026-08-29 ｜ 总控）
- **批准 M4 独立维护 listing_tasks（模块内幂等键同构），不双写 M0 workflow_jobs**；队列语义（租约/失败隔离/错误码）与 M0 一致；M0 workflow_jobs 作为跨模块编排队列，A7 集成联调确认对接方式。

### 会签状态
- ✅ 已确认：M0（基准定稿）、M1、M2、M4 ｜ ⏳ 待确认：M3、M5（M5 含风控基座引用任务）

---

### DA-008 ｜ M5 会签确认（2025 体系建立日 ｜ M5 总工）

按 M5 分模块核对项（DA-008 第 132 行）逐条确认（已核实 `backend/ads/` 实现）：

1. **风控共享规则引用基座 —— ✅ 已执行（v1.1 改造完成）**：`backend/ads/stop_loss.py` 已改为 **import M0 基座 `foundation.risk`** 替换自有实现——S1（rule_s1_stop_loss）/ S3（rule_s3_roi_floor）/ S5（rule_s5_balance）/ S7（check_budget_triple）/ S8（kill_switch_enabled）+ normalize_diagnosis + RuleVerdict/BudgetVerdict/EngineResult 数据类型全部指向基座（import 断言 `sl.rule_s1_stop_loss is fr.rule_s1_stop_loss` 等通过）；**业务专属 S2（诊断优化记录）/ S4（平台补贴记录）/ S6（活跃数上限）与 StopLossEngine 编排保留本模块**（基座不含，文档注明）。改造后定向 `pytest tests/test_ads_stop_loss.py -q --basetemp=".pytest-tmp-m5"` → **28 passed**；全 ads 套件 7 文件 → **158 passed**（零回退）。
2. **ad_* 表金额分 int / 时间 _at UTC —— ✅ 确认**：ad_campaigns/ad_runs/ad_report_snapshots/ad_account_states/ad_materials 金额字段（spend/gmv/platform_subsidy/balance）全部 Integer 分；时间戳 `_at` 后缀 DateTime(timezone=True)+utcnow（UTC 存储，展示转 UTC+8）；主键自增 INTEGER。
3. **app_config 只读 —— ✅ 确认**：`ads/repo.py` 仅 `read_app_config`（原生 SQL 只读，本模块库无此表时返回 default 不抛错），禁止 INSERT/UPDATE（宪法第 4 节）。
4. **补充口径登记**：枚举存储英文（status=pending/active/paused/not_eligible/ended；evaluation=exploring/efficient/potential 与 M2/M3 共口径；诊断 excellent/good/optimize_1/optimize_n），动作枚举 pause/halt_new/stop_new/degrade_material/record_optimization/record_subsidy/halt_all；错误码使用 09 码表（含 PAGE_CHANGED 扩展码，M5 executor/report 使用）——与 M0 基准一致。

**结论：M5 会签确认（3 项全部确认，其中第 1 项风控基座引用已执行完毕并通过 158 全量验证）。** 回传 M0；同意推进 A7 集成联调（M5 侧 v0.1~v1.0 代码全部完成，mock 模式全链路可测；真实实投依赖登录态/账号/余额/素材/实机探针就绪）。佐证：`backend/ads/stop_loss.py`（基座引用）、`ads/repo.py`（app_config 只读）、`ads/tables.py`（5 表 DDL）。

---

### DA-008 ｜ M3 会签确认（2025 体系建立日 ｜ M3 总工）

按 M3 分模块核对项（DA-008 第 130 行）逐条确认（已核实 `backend/optimization/` 实现）：

1. **app_config 只读（`risk.high_risk_categories` 扩展点预留）** ✅ **确认**——`review/manual.py` ManualSampler 的 `high_risk_categories` 为构造注入扩展点（生产可从 app_config 读取后注入，**本模块不直读 app_config**，归 M0 只读，写入经总控协调）；`review/gate.py`/`ab/*`/`upload/*` 均无 app_config 写操作。错误码使用 09 文档 8+1 码表（VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/TIMEOUT/NO_MATCH/PLATFORM_REJECT/UNEXPECTED，upload 错误映射 + video VideoToolError 限定子集）。
2. **opt_* 表时间 _at UTC / 金额分 int** ✅ **确认（会签发现 1 处差异已当场修正）**：
   - 时间：opt_* 9 表时间戳全部 `_at` 后缀、`DateTime(timezone=True)` + `utcnow()`（UTC 存储，展示转 UTC+8），与 DA-001 一致；
   - 金额：**差异修正**——`opt_evaluation_feedback.spend` 原为元（float，ingest 层 /100 换算）→ **已改为「分」直存**（`ab/ingest.py` 去掉 /100，`spend=float(spend_cents)` 直存，DA-001 金额单位=分 int）；`models.EvaluationSnapshot.spend` 注释同步（金额单位分）；roi 为比值不受单位影响；
   - 主键：`TEXT` UUID 风格（`opt_<uuid12>`，与 M4 listing_tasks 业务主键模式同向）——**补充说明**：M0 基准「主键自增整数」适用于自增表；M3 opt_* 业务实体主键用模块内生成 ID（跨库不建 FK、避免依赖基座序列），如总控要求统一自增可裁定（不阻塞）。
3. **evaluation 枚举与 M2/M5 共口径** ✅ **确认（会签发现 1 处差异已当场修正）**——**差异修正**：M3 原用 `exploration`/`high_efficiency` → **已统一为 `exploring`/`efficient`/`potential`**（与 M2/M5 共口径，DA-004/DA-007 互认）：`ab/evaluate.py` 常量（HIGH_EFFICIENCY="efficient"、EXPLORATION="exploring"）、`ab/ranking.py` EVALUATION_ORDER、`tables.py` 默认值（opt_video_variants/opt_evaluation_feedback）、`models.py`、`upload`（api/service/ui）、`video/composer` 全部同步；测试断言同步（e2e/m5_integration/retrain_driven/video_composer/ab）。
   - **修正后验证**：M3 全范围 `pytest tests -q --basetemp=".pytest-tmp-m3" -k "optimization"` → **305 passed, 1 skipped 全绿**；全量 → **1089 passed, 2 skipped**（含 M0 foundation_security 此前 2 个失败亦已消失，零回归）。

**结论：M3 会签确认（3 项全部确认，含 2 处会签发现差异已当场修正：金额分直存、evaluation 枚举统一共口径）。** 回传 M0；同意推进 A7 集成联调。佐证：`backend/optimization/ab/evaluate.py`（枚举常量）、`ab/ranking.py`（EVALUATION_ORDER）、`ab/ingest.py`（金额分直存）、`review/manual.py`（app_config 只读扩展点）。

---

## DA-009 ｜ A7 集成联调发现：M4 pipeline 未落 SPU/SKU 本库（候选池价格/标题恒 None）

- **发现方**：M0 总工（A7 跨模块冒烟联调 `test_foundation_integration.py`）｜ **涉及**：M4（m4-listing）。
- **现象**：M4 上架闭环跑通（ListingPipeline mock adapter → listed + R22 链接证据），但 M5 消费端 `CandidatePool.get_sale_candidates()` 返回的 `title`/`category_id`/`price_min_cents`/`price_max_cents` 恒为 **None**（商品级字段 `product_id`/`product_link` 正常）。
- **根因**：M4 `listing/pipeline.py` 上架流程只调用 `adapter.create_spu/create_skus`（mock 平台侧），**未将 SPU/SKU 行写入本模块库 `listing_spus`/`listing_skus`**（repo 无对应落库方法调用）→ 候选池（DA-005 提供内容）关联查表为空。
- **影响**：DA-005「M4 → M5 候选池」的 title/category/价格区间字段恒空，M5 托管优选/预算决策缺字段（商品级仍可用）。
- **建议修复（M4 侧）**：pipeline 在 `create_spu`/`create_skus` 成功后将结果落 `listing_spus`（task_id/spu_id/title/category_id）+ `listing_skus`（spu_id/price_cents/product_sku_code）本库；M4 测试补充候选池价格聚合断言。
- **状态**：**已提请总控转达 M4 总工**；M0 冒烟测试已标注缺口断言（`price_min_cents is None or == 2990`），M4 修复后可收紧。
- **总控核对结论**：（待填）