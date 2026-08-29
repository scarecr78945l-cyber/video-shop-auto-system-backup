# M3 自动素材优化 · 跨模块数据需求登记（data-requests）

> 依据宪法第 5 节登记：本模块需要其他模块的数据时，先在本文件登记，再写入 `_management/logs/data-audit.md`，由总控转达相关模块总工。
> 字段口径必须与对方 context 数据字典一致，最终由总控核对。

## 1. 从 M2（素材收集）获取 —— 原始素材（只读）

- **字段**：asset_id、asset_type(video/image)、source_platform、source_url、md5、phash、file_path、duration、resolution、size、tags_json、heat_score、evaluation（初始探索期）
- **用途**：视频二创原始输入；主图/详情图参考；热度用于素材排序
- **频率**：按生成任务触发（每商品 1 次）+ 批量日更
- **口径**：主键 asset_id；时间 UTC；file_path 为 M2 存储键；只读 assets 表或经 data-exchange JSON

## 2. 从 M1（选品）获取 —— 商品信息（只读）

- **字段**：product_id、taobao_original_title（淘宝原始标题，标题清洗唯一来源）、category（类目）、sku_spec_json（1688 SKU 规格/材质，口播稿依据）
- **用途**：标题机械清洗、口播稿生成、类目记忆 key、生图规划输入
- **频率**：按生成任务触发
- **口径**：主键 product_id；类目对齐 M1 类目口径（含白名单）

## 3. 从 M5（投放）回写 —— 投放效果

- **字段**：platform_material_id（= M5 素材记录 material_id）、report_date（UTC YYYY-MM-DD）、impressions（曝光）、clicks（点击，可选缺省 0）、**spend_cents / gmv_cents（金额「分」int，DA-001 M5 口径）**、orders（可选缺省 0）、diagnosis（M5 中文枚举：优秀/良好/1项待优化/N项待优化）
- **用途**：计算 evaluation 标签（探索期/潜力/高效）、素材评分（f(ROI, CTR, 诊断)）、模板参数按类目重训练
- **频率**：日快照回写（report_date 聚合）
- **消费入口**：`backend/optimization/ab/ingest.py`（ingest_m5_record / ingest_m5_batch，v1.1-① 联调已验收，5 用例）
- **换算**：spend 元 = spend_cents/100；roi = gmv_cents/spend_cents（spend>0）；诊断字符串 → {"level": ...} 字典形状
- **载体**：经总控协调的 data-exchange JSON（规划 `_management/data-exchange/m5-to-m3-evaluation.json`）；unmatched material_id 不落库（失败隔离）
- **口径**：经 opt_evaluation_feedback 落库；M3 不直写 M2 assets.evaluation，由总控协调同步

## 4. 提供给 M4（上架）—— 优化素材

- **内容**：主图 5 张（1:1 不全相同）+ 详情图 ≥3（标准 3+3）+ 标题（15–35 字符，已机械清洗）+ 可选口播稿
- **载体**：file_path（经 M0 存储层）或 data-exchange JSON（待总控定）

## 5. 提供给 M5（投放）—— 投放素材

- **内容**：9:16 视频多版本（A/B 候选，file_path + platform_material_id）+ 投放文案/角标（≥2 套）+ evaluation 排序（高效 > 潜力 > 探索期）
- **载体**：M3 库 opt_video_variants（M5 只读）或 data-exchange JSON（待总控定）
