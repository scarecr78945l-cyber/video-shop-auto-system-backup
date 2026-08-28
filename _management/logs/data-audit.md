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
