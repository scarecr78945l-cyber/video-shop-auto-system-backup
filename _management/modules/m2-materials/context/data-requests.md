# M2 自动收集素材 · 跨模块数据需求登记（data-requests）

> 依据宪法第 5 节登记：本模块需要/提供其他模块的数据时，先在本文件登记，再写入 `_management/logs/data-audit.md`（**由 M2 总工追加**，子代理 B4-2 权限不含该文件），由总控转达相关模块总工。
> 字段口径以 `context/README.md` 数据字典为准（主键 asset_id；时间 ISO8601 UTC；金额单位分；评估枚举 exploring/efficient/potential）。
> 版本：v0.1 ｜ 撰写人：M2 子代理 B4-2 ｜ 日期：2025 体系建立日

---

## 一、向 M3（素材优化）提供 —— 原始素材（只读）

| 字段 | 口径 | 用途 |
|---|---|---|
| `asset_id` | 素材主键 | 二创任务关联 |
| `asset_type` / `source_platform` / `source_url` | 同数据字典 | 二创原料溯源/版权标记依据 |
| `file_path` | M2 存储键（本地相对键；M4 迁 MinIO 后为 MinIO 键） | M3 拉取原始素材做二创 |
| `tags_json` / `heat_score` | 标签数组 JSON / 热度 0~100 | 二创选题参考 |
| `derivation_note` | 二创义务标记 | 提示 M3 二创义务（去水印/混剪/换文案） |

- **用途**：视频二创原始输入 + 主图/详情图参考（context 3.1）。
- **频率**：按生成任务触发（每商品 1 次）+ 批量日更；提供方=M2，经总控 data-audit 核对后转达。
- **门禁**：仅 `compliance_status=passed` 素材可对外提供（context 3.2/3.4 口径）。

## 二、向 M5（投放）提供 —— 素材查询/绑定（只读）

| 字段 | 口径 | 用途 |
|---|---|---|
| `asset_id` | 素材主键 | 投放绑定关联 |
| `file_path` | M2 存储键 | 投放取料 |
| `platform_material_id` | 小店素材库 ID（上传成功后回填，唯一） | **绑定前提**：仅已上传素材可绑定投放 |
| `upload_status` | `uploaded`（枚举 local/uploading/uploaded/failed/disabled） | 过滤：仅 `uploaded` 且规格合格素材可绑定 |
| 规格字段 | `asset_type`/`duration`/`resolution`/`size`（5~300s、≥720×1280、≤500M） | 投放硬规格校验（context 1.3） |
| `evaluation` | exploring/efficient/potential（M5 回写值） | M5 按 高效>潜力>探索期 优选绑定（M5-REQ-03） |

- **用途**：素材优选绑定（context 3.3 M2→M5 方向）。
- **频率**：M5 每次执行前拉取（实时查询 M2 库或 data-exchange JSON，载体待总控定）。

## 三、从 M5（投放）接收 —— evaluation 评估标签回写

| 字段 | 口径 | 用途 |
|---|---|---|
| `asset_id` | 素材主键 | 回写定位 |
| `evaluation` | 枚举：`exploring`（探索期）/`efficient`（高效）/`potential`（潜力），非法值拒绝（PLATFORM_REJECT） | 更新 `asset_items.evaluation`（当前值） |
| `evidence` | 回流批次/报表快照摘要（JSON） | 写 `asset_evaluations` 审计留痕（含 source_agent=M5） |

- **用途**：评估标签回流审计（context 3.3 M5→M2 方向 + 1.4）。M2 不主动写 evaluation，仅 M5 回写。
- **实现**：`backend/materials/integration.py` `EvaluationFeedbackService.receive_evaluation`（幂等：重复回写同值收敛不报错，审计表为台账每次回写留痕）。
- **频率**：日快照回写（M5 投放效果聚合后批量）；拒审/源文件损坏走 `upload_status=disabled` + 拒审原因（非 evaluation）。

## 四、从 M3（素材优化）接收 —— 上传结果回填

| 字段 | 口径 | 用途 |
|---|---|---|
| `asset_id` | 素材主键 | 回填定位 |
| `platform_material_id` | 小店素材库 ID（唯一约束防重复回填；被其他素材占用 → PLATFORM_REJECT） | 回填 `asset_items.platform_material_id` + `upload_status=uploaded` + 写 `asset_uploads` 记录 |
| `upload_status` | `uploaded` | 供 M5 绑定过滤（见第二节） |

- **用途**：上传小店素材库成功结果回填（context 3.3；M2 侧抽象承担上传链路，`backend/materials/integration.py` `MaterialUploadService`）。
- **实现**：`repo.mark_uploaded`（幂等）+ `asset_uploads` 记录；失败分类 TIMEOUT/PLATFORM_REJECT/UNEXPECTED 结构化返回。
- **频率**：每次上传任务完成后回填；上传链路暂以 fixtures mock 交付（`MATERIALS_UPLOAD_MODE=mock`），真实小店素材库 API/登录态确认后切换 shop 模式。

---

## 口径约定（需总控 data-audit 全局核对）

1. 主键：`asset_id`（M2 素材库唯一）。
2. 时间：一律 ISO8601 UTC，时间戳字段名后缀 `_at`（DA-001 裁决）。
3. 枚举：`evaluation`=exploring/efficient/potential（M2 context 1.4 与 M5 context 三.3 同口径）；`upload_status`=local/uploading/uploaded/failed/disabled。
4. 金额单位：分（int）（DA-001 裁决，本模块素材侧不涉及金额字段）。

## 变更记录

| 日期 | 变更 |
|---|---|
| 2025 体系建立日 | 初始登记（B4-2：M3 提供 / M5 提供与回写 / M3 上传回填四类） |
