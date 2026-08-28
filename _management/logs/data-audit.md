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
