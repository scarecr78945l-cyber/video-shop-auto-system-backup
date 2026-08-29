# M3 自动素材优化 · 上下文库（context）

> 模块的持久记忆，跨会话不丢失。任何代理重启后先读本目录。
> 必须维护：数据字典、API 契约、环境事实、跨模块数据契约。禁止写明文密钥。
> 关联：brief.md（任务书）、risks.md（风险预判）、database/README.md（Schema）、data-requests.md（数据需求登记）。

## 一、数据字典

### 1.1 素材输出规格（硬性，不可协商 —— 对齐 05/06/09 文档）

| 项 | 要求 |
|---|---|
| 分辨率 | ≥720×1280 |
| 比例 | 9:16（竖屏） |
| 格式 | MOV / MP4 |
| 大小 | ≤500M |
| 时长 | 5 ~ 300 秒 |
| 主图 | 5 张 1:1，且**不能全部相同**（phash 相似度校验） |
| 详情图 | ≥3 张（最低门槛 1 主图 + 1 细节图可放行，标准 3+3） |

> ffmpeg 输出参数参考：`ffmpeg -i in.mp4 -vf scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2 -t 300 -c:v libx264 -crf 23 -c:a aac output.mp4`（按素材源微调，出片后必须 ffprobe 校验）。

### 1.2 模板参数（opt_templates，可配置）

| 参数 | 说明 | 默认 |
|---|---|---|
| opening_seconds | 片头秒数 | 3 |
| subtitle_style | 字幕样式 JSON（位置/字号/描边） | `{"position":"bottom","font_size":36,"stroke":true}` |
| badge_position | 角标位 | top-right |
| bgm_loudness | BGM 响度（LUFS） | -16.0 |
| cut_count | 混剪片段数 | 3 |
| params_version | 参数版本（模板重训练后 +1） | 1 |
| stats_json | 训练统计（avg_roi / ctr / 样本数） | — |

### 1.3 文案（opt_copywrites）

| copy_type | 规则 | 关键字段 |
|---|---|---|
| title 商品标题 | 15–35 字符；以**淘宝原始标题为唯一来源**，机械去标签/去重/截断，不虚构卖点 | content, char_len |
| script 卖点口播稿 | 基于 1688 SKU 真实规格/材质生成；禁止来源未证实的承诺（如「送200木棍」须所选 SKU 明确支持） | content, sku_basis_json |
| ad 投放文案 | 多套候选（≥2），合规预审 | content, variant_no |
| badge 角标 | 多套候选（≥2），合规预审 | content, variant_no |

### 1.4 评估标签（evaluation）

| 标签 | 定义 | 用途 |
|---|---|---|
| 探索期（exploring） | 新素材/无回写数据 | 默认起步标签 |
| 潜力（potential） | 曝光/点击有正向信号，成交待观察 | 次级推荐 |
| 高效（efficient） | 成交 ROI / 点击率达标 | 投放绑定首选 |

> **口径**：枚举与 M2/M5 共口径（exploring/efficient/potential，DA-008 会签统一）；标签由 M3 依据 M5 回写数据（曝光/花费/成交/诊断）计算并落 opt_evaluation_feedback；M2 的 assets.evaluation 由总控协调同步，M3 不直写 M2 库。

### 1.5 A/B 版本结构

```
(product_id, variant_no) 唯一 —— 同一商品 ≥2 版
├── variant_no: 1..N（不同片头/文案/节奏 = 不同 template_id + copywrite_ids 组合）
├── template_params_snapshot: 出片参数快照（防模板更新后历史数据失真）
├── copywrite_ids: 该版使用的文案候选
├── file_path / platform_material_id
└── evaluation + stats（回写聚合：exposure/clicks/spend/orders/roi/diagnosis）
```

## 二、外部契约

| 外部 | 契约摘要 | 环境变量（名，不含值） |
|---|---|---|
| DeepSeek | 结构化输出（JSON Schema 校验）：卖点拆解 / 口播稿 / 文案候选；失败重试 2 次 | DEEPSEEK_API_KEY |
| Kimi | KimiImagePlanner：主图视觉策略规划；失败降级默认策略 | KIMI_API_KEY |
| Wan | WanImageProvider：生图；RATE_LIMIT 180s 退避 + 日配额熔断 | WAN_API_KEY |
| Qwen-VL | **素材相关性门（REC-迁移-03 C3）**：前 15 秒抽帧相关性判定（related/unrelated/multi_style）+ 款式聚类；无 API Key 时 fixtures mock 判定器，环境就绪（mode=auto）自动启用真实模式；真实判定器骨架待 API 契约确认（QwenVLRelevanceJudge 抛错不静默） | QWEN_VL_API_KEY（relevance.api_key_env，仅变量名） |
| ffmpeg / ffprobe | 出片 + 硬规格校验（ffprobe JSON 输出留证据）；相关性门真实抽帧复用 | FFMPEG_PATH / FFPROBE_PATH |
| 小店素材库 | 上传（api/ui 待验证）→ platform_material_id + 平台评估标签 | M3_UPLOAD_MODE |

## 三、跨模块数据契约

| 方向 | 字段 | 口径 |
|---|---|---|
| 从 M2 获取（只读） | asset_id, asset_type(video/image), source_platform, source_url, md5, phash, file_path, duration, resolution, size, tags_json, heat_score, evaluation | 主键 asset_id；时间 UTC；file_path 为 M2 存储键；见 05 文档 |
| 从 M1 获取（只读） | product_id, taobao_original_title, category, sku_spec_json（1688 SKU 规格/材质） | 主键 product_id |
| 提供给 M4 | 主图 5 张 + 详情图 ≥3（file_path/URL）+ 标题 15–35 字符 | 标题已机械清洗；图片路径经 M0 存储层 |
| 提供给 M5 | 9:16 视频多版本（file_path + platform_material_id）+ 投放文案/角标 + evaluation 排序 | 素材 ID 为小店平台素材 ID |
| 从 M5 回写 | platform_material_id, exposure, clicks, spend, orders, roi, diagnosis_json | 经 opt_evaluation_feedback，按 report_date 日快照聚合 |

> 明细登记：`context/data-requests.md` + `_management/logs/data-audit.md`（宪法第 5 节）。

### 3·B 素材相关性门契约（M2↔M3↔M4，REC-迁移-03 C3 / DA-010）

- **M3 侧**：`review/relevance.py`（Qwen-VL 判定抽象 + mock 判定器 + 前 15 秒抽帧 + StyleClusterer 款式聚类）+ `review/gate.py` `RelevanceGate` 编排落 `opt_review_records`（gate_type=relevance，target_type=material，target_id=M2 asset_id）；判定三态 related（pass）/ unrelated（reject）/ multi_style（manual_review，`reasons_json.manual_note` 留证「多款式需人工确认目标款，禁止自动创建衍生商品」）。
- **消费端（M2）**：`backend/materials/integration.py` `RelevanceGateService.receive_relevance`（result pass/reject/manual_review → relevance_status passed/failed/manual_review，幂等回写）；仅 `passed` 可进入询价/上架链（`is_ready_for_chain`）。
- **M4 侧**：待派工——候选池/上架前置校验读取 M2 `relevance_status`（见 data-audit DA-010）。
- **正式载体**：`_management/data-exchange/m2-m3-m4-relevance-gate.json`（字段契约 + 三态映射，待 M2/M3/M4 总工会签）。

## 四、环境事实

| 项 | 值/名 |
|---|---|
| 数据库 | `backend/data/db/m3-optimization.db`（SQLite 开发，不入 git；生产 PostgreSQL，迁移脚本在 database/） |
| 环境变量（名，不含值） | M3_DB_URL, DEEPSEEK_API_KEY, KIMI_API_KEY, WAN_API_KEY, FFMPEG_PATH, FFPROBE_PATH, M3_DATA_DIR, M3_LOG_LEVEL, M3_UPLOAD_MODE(api/ui), M3_REVIEW_SAMPLE_RATE, M3_UPLOAD_BATCH_SIZE(≤50), M3_GEN_CONCURRENCY |
| Python | 3.12+（当前 3.13 已验证基线） |
| 测试 | `python -m pytest tests -q --basetemp=".pytest-tmp"`（P-001） |
| 共享浏览器 | CDP 9223（共享 Chrome：小店后台/素材库上传用）；登录态归属 M0 管理 |
| 错误码 | VERIFICATION_REQUIRED / AUTH_REQUIRED / RATE_LIMIT / TIMEOUT / NO_MATCH / PLATFORM_REJECT / UNEXPECTED（复用 09 文档错误码表） |
| 合规词库 | 复用 backend/sourcing/compliance.py：BRAND_WORDS / PROHIBITED_WORDS / EFFICACY_WORDS / SUPPLY_CHAIN_WORDS / sanitize_title |
