# 代理工作台账（Agent Activity Log）

> 记录每一个代理（总工/子代理）完成的任务与产出。格式见宪法第 3 节。只追加，不改写。

---

### 2025 体系建立日 ｜ 总控 Agent ｜ 全局 ｜ 角色：总控

- 完成任务：勘察工作区，通读 11 份方案文档与 backend 基线；建立 `_management` 管理体系；初始化 git；登记踩坑日志 P-001~P-007。
- 产出文件：`AGENT_CONSTITUTION.md`、`master-session.md`、`org-chart.md`、`dashboard.md`、`logs/pitfall-log.md` 等。
- 基线测试：39 passed（`--basetemp=".pytest-tmp"`）。
- 当前阻塞：GitHub 备份仓库接入方式待用户决策。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工

- 完成任务：通读必读文档（宪法/pitfall-log P-001~P-007/05-自动收集素材模块设计/09-数据模型与任务编排/10-风险合规与风控清单/11-里程碑与落地路线/03-系统总体架构设计/backend README）；完成 M2 首轮筹备交付物。
- 产出文件：
  - `_management/modules/m2-materials/brief.md`（任务书：目标/范围边界/交付物清单/四阶段里程碑 v0.1~v1.0/六个可拆子代理任务）
  - `_management/modules/m2-materials/risks.md`（风险预判 R-M2-01~24：覆盖视频号/抖音/快手/小红书签名与反爬、登录态、TikTokDownloader 视频号支持弱、ffmpeg 环境、素材版权、MinIO 暂缺存储过渡、去重准确率、浏览器自动化、数据口径、风控合规）
  - `_management/modules/m2-materials/context/README.md`（数据字典：Asset 实体字段、双去重规则、素材硬规格 ≥720×1280/9:16/MOV·MP4/≤500M/5~300s、评估标签 exploring/efficient/potential；外部契约；M3/M4/M5 跨模块数据契约；环境事实）
  - `_management/modules/m2-materials/database/README.md`（Schema 规划：asset_* 7 表 DDL——asset_items/asset_download_jobs/asset_sources/asset_dedup_fingerprints/asset_evaluations/asset_compliance_checks/asset_uploads，SQLite 语法，v0.1 暂不建库）
  - `_management/modules/m2-materials/progress.md`（筹备任务全部勾选，模块完成度 15%，剩余排期与子代理拆分见看板）
- 当前阻塞：无。待总控验收筹备交付物并批准子代理排期后派发开发任务。
- 备注：未运行任何 git 命令；未读写其他模块库；未写任何明文密钥。pytest 纪律（--basetemp=".pytest-tmp"）已写入子代理任务书模板。

### 2026-08-28 20:53 | M0-总工 | m0-foundation | 角色：总工

- 完成任务：通读宪法/踩坑日志（P-001~P-007 已确认）与设计文档 09/10/11/02/03/01 + backend 基线（sourcing/tables.py、config.py、db.py、README.md）；确认 `workflow_jobs`/`tasks`/`logs` 当前 backend 树未实现（迁移包才有，属 M0 规划范围）；撰写筹备轮四件套（任务书/风险/上下文/DB 规划）；记录 6 项关键决策；制定开发排期 A1~A7（A1~A5 可拆子代理）；落实 P-001 到 backend/README.md 测试命令。
- 产出文件：`_management/modules/m0-foundation/brief.md`、`risks.md`、`progress.md`、`decisions.md`、`context/README.md`、`database/README.md`；修改 `backend/README.md`（测试命令补 `--basetemp=".pytest-tmp"`）。
- 当前阻塞：无（GitHub 备份接入为总控事项，不属于 M0）。

---

### 2025 体系建立日 ｜ M4 总工程师 ｜ M4 自动上架 ｜ 角色：总工

- 完成任务：通读必读文档（宪法 AGENT_CONSTITUTION.md、pitfall-log P-001~P-007、07-自动上架模块设计、09-数据模型与任务编排、10-风险合规与风控清单、11-里程碑与落地路线、03-系统总体架构设计、01-开源项目盘点与借鉴上架部分）与 m4-listing 模板；完成 M4 首轮筹备交付物（P0 全部落地）。
- 产出文件：
  - `_management/modules/m4-listing/brief.md`（任务书：目标/范围边界/交付物清单/里程碑 P0~P6，P1~P5 可拆子代理）
  - `_management/modules/m4-listing/risks.md`（风险预判 R1–R24：覆盖 OpenAPI 准入条件（企业主体/类目资质/接口配额/签名）、令牌与密钥、审核状态轮询、Playwright 兜底选择器脆弱、真实链接验证铁律、上架与托管错峰防风控等，引用 P-001~P-007）
  - `_management/modules/m4-listing/context/README.md`（数据字典：listing_tasks/spus/skus/upload_assets/op_logs/audit_records/quota_states 字段口径、状态机 9 态与迁移条件、WorkflowJob 错误码映射、channels OpenAPI 外部契约、与 M1/M3/M5/M0 跨模块数据契约、环境事实含环境变量名）
  - `_management/modules/m4-listing/database/README.md`（Schema 规划：listing_* 7 表 DDL v0，表归属决策——upload_history/wechat_upload_logs 归属基座 M0 只读参照、M4 以 listing_upload_assets/listing_op_logs 留痕，生产 PostgreSQL 迁移说明）
  - `_management/modules/m4-listing/progress.md`（筹备任务全部勾选，模块完成度 15%，开发排期 P1~P6 与子代理拆分、验收门）
- 当前阻塞：无。待总控验收筹备交付物、核对官方 channels OpenAPI 契约（签名/接口字段/配额阈值）并批准子代理排期后派发 P1/P2 开发任务。
- 备注：未运行任何 git 命令；未读写其他模块库文件；未写任何明文密钥（AppID/Secret 仅环境变量名）；pytest 纪律（`--basetemp=".pytest-tmp"`）已写入任务书与上下文环境事实。

---

### 2025 体系建立日（第 2 轮）｜ M3 总工程师 ｜ M3 自动素材优化 ｜ 角色：总工

- 完成任务：通读必读文档（宪法、踩坑日志 P-001~P-007、03/06/09/10/11、05 M2 素材契约、backend/sourcing/compliance.py 基线、backend README）；完成 v0.1 筹备：模块任务书、风险预判（覆盖 LLM 密钥配额/ffmpeg 硬规格/生图拒审/供应链词品牌词合规/评估标签回流口径/上传素材库接口与 UI 方式）、数据字典与跨模块契约、opt_* Schema 规划、跨模块数据联动申请登记。
- 产出文件：
  - `_management/modules/m3-optimization/brief.md`（任务书：目标/范围边界/交付物清单 8 项/里程碑 v0.1~v1.1+/5 个可拆子代理任务包）
  - `_management/modules/m3-optimization/risks.md`（风险预判八节 ★重点：LLM API 密钥与配额、ffmpeg 输出硬规格校验、生图质量与平台拒审、供应链词/品牌词合规、评估标签回流口径、上传小店素材库接口/UI 方式、数据口径与污染、环境依赖；关联 P-001~P-007）
  - `_management/modules/m3-optimization/context/README.md`（数据字典：素材输出硬规格/模板参数/文案四类/评估标签/A/B 版本结构；外部契约；跨模块数据契约；环境事实）
  - `_management/modules/m3-optimization/context/data-requests.md`（对 M1/M2/M5 的数据需求明细）
  - `_management/modules/m3-optimization/database/README.md`（Schema 规划：opt_* 8 表 DDL v0——opt_templates/opt_video_variants/opt_image_batches/opt_images/opt_copywrites/opt_review_records/opt_category_memory/opt_evaluation_feedback/opt_upload_records，SQLite 语法，暂不建库）
  - `_management/modules/m3-optimization/progress.md`（筹备任务全部勾选，模块完成度 10%，剩余排期与 5 个可拆子代理任务包）
  - `_management/modules/m3-optimization/decisions.md`（4 项初始决策 + 2 项待总控裁定）
- 台账登记：`_management/logs/data-audit.md` 追加 M3 数据联动申请（M2 原始素材 / M1 商品信息 / M5 效果回写 / 对 M4·M5 输出）。
- 当前阻塞：无（2 项待总控决策：① 09 文档 image_batches/image_assets 归属；② 小店素材库上传 OpenAPI 可用性确认）。
- 备注：未运行任何 git 命令；未读写其他模块数据库；未写任何明文密钥（仅环境变量名）。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（补充·编码纪律）

- 完成任务：落实宪法第 11 节编码纪律——用 PowerShell 只读复核本模块全部产出文件编码（brief/risks/context-README/database-README/progress/decisions/agent-activity 共 7 处，实测全部 **UTF-8 无 BOM、严格回读一致、无 ANSI/GBK 污染**）；将编码纪律显式写入 `context/README.md`（环境事实表新增"文件编码"行）与 `brief.md`（子代理任务书必含条款），确保 M2 子代理产出不犯 GBK 污染事故。
- 产出文件：`_management/modules/m2-materials/context/README.md`、`brief.md`（各 +1 行纪律条款）；本日志追加补充条目。
- 当前阻塞：无。仍待总控验收筹备交付物并批准子代理排期。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（确认·会话管理模式）

- 完成任务：确认总控下发「会话管理方式」（开发阶段：总工用 `subagent` 每任务一子代理、任务书自包含；总工负责架构/拆解/进度/验收/集成，不批量自写；验收不合格退回；阻塞先自判，判断不了写 BLOCKERS.md 结束回合）；将确认内容落档 `progress.md`（新增「开发阶段管理方式（总控已确认）」5 条）；核验筹备交付物完整性（brief/risks/context/database/progress/decisions/BLOCKERS 共 7 文件在位，无并发损坏）。
- 产出文件：`_management/modules/m2-materials/progress.md`（+5 条管理方式）；本日志追加确认条目。
- 当前阻塞：无。筹备交付物全部完成，**等待总控验收并批准批次 1 子代理排期（D 素材库表、F 下载中台）**，批准后进入开发阶段。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工

- 完成任务：通读必读文档（宪法 AGENT_CONSTITUTION.md、踩坑日志 P-001~P-007、08-自动小店投放模块设计（商品托管）、09-数据模型与任务编排、10-风险合规与风控清单、11-里程碑与落地路线、03-系统总体架构设计）与 m5-ads 模板全套；完成 M5 首轮筹备交付物（v0.1 筹备，模块完成度 15%）。
- 产出文件：
  - `_management/modules/m5-ads/brief.md`（任务书：目标=商品托管全自动闭环；范围边界（负责 8 项/不负责 Marketing API 对接）；交付物清单 9 项+验收标准；里程碑 v0.1 筹备→v0.2 数据层→v0.3 执行层→v0.4 监控层→v0.5 回流层→v1.0 集成验收→v1.1 实投验证）
  - `_management/modules/m5-ads/risks.md`（风险预判 R1~R8 总览 + 八节详表：覆盖必查项——小店投放无官方 API（纯 UI 自动化）/后台改版/登录态/素材硬规格与审核/目标 ROI 取值/资金风控（余额·预算·止损）/批量错峰/诊断回读；关联 P-001~P-007）
  - `_management/modules/m5-ads/context/README.md`（数据字典：ad_campaigns/ad_runs/ad_report_snapshots/ad_account_states/ad_materials 五实体字段表，金额统一「分」int、时间 UTC+8；后台界面事实锚点 5 页；止损规则表 S1~S8；外部契约（无 API/WorkflowJob 码表/调度节奏）；跨模块数据契约 7 条（M1/M2/M3/M4/M0）；环境事实含环境变量名清单（不含值））
  - `_management/modules/m5-ads/database/README.md`（Schema 规划：ad_* 5 表 SQLite DDL v0.1——ad_campaigns/ad_runs/ad_report_snapshots/ad_account_states/ad_materials，含索引与唯一约束（campaign_id+recorded_at 幂等）；app_config 扩展配置项 10 条；迁移记录表；生产 PostgreSQL 迁移说明）
  - `_management/modules/m5-ads/progress.md`（筹备任务全部勾选，模块完成度 15%，后续排期 v0.2~v1.1 与子代理拆分：托管执行器（Playwright）/投放设置/监控回读/止损规则引擎/数据回写/测试验收 6 类可拆子代理任务）
- 当前阻塞：无。待总控验收筹备交付物并批准子代理排期后派发 v0.2 数据层 / v0.3 执行层开发任务。
- 备注：未运行任何 git 命令；未读写其他模块数据库文件（本模块库 backend/data/db/m5-ads.db 仅规划暂不建库）；未写任何明文密钥（投放账号凭证仅环境变量名）；中文文件全部经 write/edit 工具 UTF-8 无 BOM 写入；pytest 纪律（--basetemp=".pytest-tmp"）已写入 context 环境事实。

---

### 体系建立日 ｜ M1 总工 ｜ M1 自动选品（m1-sourcing） ｜ 角色：总工

- 完成任务：①按宪法顺序通读 AGENT_CONSTITUTION / pitfall-log（P-001~P-007）/ 04 / 09 / 10 / 11 / 03 / backend README / 基线代码（config / scoring / pipeline / models / tables / compliance / scheduler / collectors / fixtures / repo）；②后台复跑基线测试确认 **39 passed**（`--basetemp=".pytest-tmp"`，P-001 遵守）；③完成首轮全部文档交付。
- 产出文件（`_management/modules/m1-sourcing/`）：
  - `brief.md`（v1.0 任务书：目标 / 范围边界 / 基线复用 vs 新增清单 / 交付物验收标准 / S0~S5 里程碑 / 纪律约束）
  - `risks.md`（R-01~R-54 六域风险：登录态账号 / 外部 API（选品无官方 API）/ 浏览器自动化（CDP·选择器）/ 数据口径 / 环境依赖 / 风控合规，全部引用 P-001~P-007）
  - `context/README.md`（数据字典：SourceItem / ProductCandidate / ScoreBreakdown 字段表 + 五维满分与数据来源 + C-2 M5 回写契约草案 + C-3 M4 出池契约草案 + C-1 类目口径 + 环境事实）
  - `context/data-requests.md`（跨模块需求登记 M1-REQ-01~04 + 对外提供 M1-OUT-01~03）
  - `database/README.md`（库文件关系说明 + 现有 12 表 + 新增 `m1_ad_conversion_cache` / `m1_ad_conversion_ingests` DDL + 迁移记录 v0/v0.1/v1.0）
  - `progress.md`（筹备任务全部勾选，模块完成度 **5%**，S1~S5 排期与 4 个可拆子代理任务）
  - `decisions.md`（D-0~D-6：投放转化数据结构先行 / 第三源口径 / 库路径 / M5 回写类目口径 / m1_ 前缀与幂等键 / R 编号体系）
  - `BLOCKERS.md`（BLOCKER-001 第三源口径：考古加 vs 抖店罗盘；BLOCKER-002 库默认路径切换授权；BLOCKER-003 M5 回写契约确认——均附建议）
- 关键发现：①基线已实现投放转化第 5 维（无数据权重折入四维，和=100），缺「真实 M5 回写接入」+ 数据新鲜度判定；②app_config 白名单运行时接线未落地（ComplianceEngine 支持注入但 pipeline 未传）；③04 文档「考古加」与基线「抖店罗盘」口径不一致（BLOCKER-001）；④旧 sourcing.db 无数据，切 m1-sourcing.db 零迁移成本。
- 待总控裁决后启动 S1：BLOCKER-001（第三源口径）/ BLOCKER-002（改默认 DSN + 更新 backend/README 授权）/ BLOCKER-003（M5 回写契约，发现 M5 金额口径为「分」，本模块 C-2 草案需对齐，详见 context/README 修订）。
- 纪律自查：未运行任何 git 命令；未读写其他模块库（含 m5-ads.db）；全部文件经 write/edit 工具 UTF-8 无 BOM；无明文密钥/Token/Cookie。

---

### 2025 体系建立日（第 2 轮）｜ M4 总工程师 ｜ M4 自动上架 ｜ 角色：总工

- 完成任务：① 确认宪法第 11 节编码纪律已落档，用 PowerShell 只读复核本模块全部产出文件编码——复核结果 8 文件全部 **UTF-8 无 BOM、无替换字符/无 ANSI 污染**，并修复模板自带 BOM 的 `BLOCKERS.md`（重写为同内容无 BOM）；② 补写宪法固定交付物 `decisions.md`（D1~D10 关键决策 + 2 项待总控裁定 PEND-1/PEND-2）；③ progress.md 新增「子代理任务书要点」小节（P1~P5 自包含任务书模板：背景/输入/输出/验收/宪法要点，总控批准后可直接派发）。
- 产出文件：`_management/modules/m4-listing/decisions.md`（重写为决策记录）、`progress.md`（+子代理任务书模板小节）、`BLOCKERS.md`（去 BOM 修复）；本日志追加条目。
- 当前阻塞：无。筹备交付物齐备（brief/risks/progress/decisions/BLOCKERS/context/database 共 7 文件在位且编码合规），**等待总控验收并批准 P1/P2 子代理排期**（PEND-1 官方 channels OpenAPI 契约核对为 P1 定稿前置；PEND-2 企业主体/类目资质开通状态确认）。
- 备注：未运行任何 git 命令；未读写其他模块库；未写任何明文密钥（AppID/Secret 仅环境变量名）；全部文件由 write/edit 工具产出（自动 UTF-8 无 BOM），PowerShell 仅做只读复核（未用 Add-Content/Set-Content/重定向写任何文件，遵守宪法第 11 节）。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（确认·会话管理模式）

- 完成任务：确认总控下发「会话管理方式」（开发阶段：总工用 `subagent` 每任务一子代理、任务书自包含（背景/目标/输入输出路径/验收标准/宪法要点）；总工负责架构/拆解/进度/验收/集成，**不批量自写**；验收不合格退回；子代理阻塞先由总工判断，判断不了写 BLOCKERS.md 结束回合）；将确认内容落档 `progress.md`（新增「开发阶段管理方式（总控已确认）」6 条，含编码纪律 UTF-8 无 BOM）；核验筹备交付物完整性（brief/risks/context-README/database-README/progress/decisions/BLOCKERS 共 7 文件在位，无并发损坏）。
- 产出文件：`_management/modules/m5-ads/progress.md`（+6 条管理方式）；本日志追加确认条目。
- 当前阻塞：无。筹备交付物全部完成，**等待总控验收并批准子代理排期（v0.2 数据层 / v0.3 托管执行器 Playwright / 投放设置）**，批准后进入开发阶段。
- 备注：M1 总工 BLOCKER-003 涉及 M5 回写口径（金额「分」），本模块 context/README.md 跨模块数据契约已按「分」定义，待总控协调时与 M1 C-2 草案对齐确认。

---

### 体系建立日 ｜ M1 总工程师 ｜ M1 自动选品（m1-sourcing） ｜ 角色：总工（确认·会话管理模式）

- 完成任务：确认总控下发「会话管理方式」（开发阶段：总工在会话内用 `subagent` 每任务一子代理、任务书自包含（背景/目标/输入输出路径/验收标准/宪法要点，含 P-001 pytest 纪律与 UTF-8 编码纪律）；总工负责架构/拆解/进度/验收/集成，**不批量自写**；验收不合格退回；子代理阻塞先由总工判断，判断不了写 BLOCKERS.md 结束回合）；将确认内容落档 `progress.md`（新增「开发阶段管理方式（总控已确认）」5 条 + 「可拆子代理任务排期」批次 1/批次 2 共 4 个任务包，各含交付物与验收标准及前置条件）；核验首轮筹备交付物完整性（brief/risks/context-README/data-requests/database-README/progress/decisions/BLOCKERS 共 8 文件在位，无并发损坏）。
- 产出文件：`_management/modules/m1-sourcing/progress.md`（+管理方式 5 条 + 子代理排期 4 包）；本日志追加确认条目。
- 当前阻塞：无新增。仍待总控验收筹备交付物并裁决 BLOCKER-001（第三源口径）/ BLOCKER-002（默认 DSN 修改授权）/ BLOCKER-003（M5 回写契约，M5 侧已按「分」口径就绪，双方可对齐），批准批次 1 排期后派发 S1a/S1b/S2 子代理。
- 备注：未运行任何 git 命令；未读写其他模块库；全部文件经 write/edit 工具 UTF-8 无 BOM；无明文密钥/Token/Cookie。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 1 派发）

- 完成任务：总控批准批次 1（D 素材库表+F 下载中台）；勘察 backend 实际结构（sourcing 包/config/db/tables/conftest/requirements 无 FastAPI）；编写两份自包含子代理任务书（背景/目标/输入输出路径/验收标准/宪法要点/P-001 纪律/禁 git/禁明文密钥/UTF-8 纪律）；并行派发子代理：**D=02d5fe74**（backend/materials 包：config 含硬规格常量/models/tables 7 表 ORM/db/repo 含指纹认领·租约·evaluation 审计/CLI init-db + test_materials_tables/repo），**F=ecc646f4**（storage.py Local/MinIO 骨架接口化 + downloader.py 断点续传·错误码映射·退避熔断·租约回收 + downloader_api.py stdlib 多实例 HTTP API + CLI + test_materials_storage/downloader，与 D 通过 DownloadJobRepo 协议解耦并行）。
- 产出文件：`_management/modules/m2-materials/progress.md`（批次 1 两任务标记「已派发」+子代理 id，任务书撰写 35%）；`backend/materials/*` 待子代理产出；本日志追加条目。
- 异常记录：两子代理首次运行在完成前中断（closing message 为空，判为环境/会话抖动），已 send_message 恢复（ready 状态可续跑），消息已排队为下一回合。
- 当前阻塞：无。待批次 1 子代理完成通知 → 总工验收（读产出+跑 pytest --basetemp=".pytest-tmp"）→ 更新 progress.md/台账 → 通知总控备份 → 推进批次 2。

---

### 体系建立日 ｜ M1 总工程师 ｜ M1 自动选品（m1-sourcing） ｜ 角色：总工（收尾核验）

- 完成任务：核验首轮筹备交付物最终状态——① `progress.md` 筹备任务全勾选、模块完成度 5%、可拆子代理排期批次 1（S1a/S1b/S2，子代理-1~3）/批次 2（S3，子代理-4）已列，文件头补「收尾核验」标记；② 台账已含本模块首轮与确认管理模式两条记录（见上）；③ `context/data-requests.md` 已存在（M1-REQ-01~04 + M1-OUT-01~03，格式对齐 M0/M2/M3/M4 登记规范）。
- 产出文件：`progress.md`（+收尾核验标记）；本日志追加收尾条目。
- 当前阻塞：无。等待总控验收与裁决（BLOCKER-001/002/003），批准批次 1 后派发子代理进入开发阶段。

---

### 2026-08-28 | 子代理 D（id 02d5fe74）| M2 自动收集素材 | 角色：子代理（素材库基座）

- 完成任务：实现 M2 素材库基座 `backend/materials/` 包（config/models/tables/db/repo/__main__/__init__）——7 表 ORM 严格对齐 `_management/modules/m2-materials/database/README.md` DDL（asset_items/asset_download_jobs/asset_sources/asset_dedup_fingerprints/asset_evaluations/asset_compliance_checks/asset_uploads）；`AssetRepo` 数据访问层（指纹认领防并发重复→DuplicateAssetError、查询过滤、evaluation 回流审计、mark_uploaded 幂等、下载任务租约领取/过期回收/完成回写、采集源账本、合规预审同步）；CLI `init-db`（幂等）与 `pool`；硬规格常量集中在 config.py（MIN_WIDTH=720/MIN_HEIGHT=1280/MIN_RATIO=9/16/MAX_SIZE_BYTES=524288000/MIN_DURATION=5/MAX_DURATION=300/ALLOWED_FORMATS=["mp4","mov"]）。配套 30 个新用例（test_materials_tables.py 12 + test_materials_repo.py 18）；conftest.py 仅追加 cfg_materials/db_materials fixtures（未动 sourcing fixtures）。
- 产出文件：`backend/materials/{__init__,config,models,tables,db,repo,__main__}.py`；`backend/tests/test_materials_tables.py`、`backend/tests/test_materials_repo.py`；`backend/tests/conftest.py`（追加）；`_management/modules/m2-materials/database/README.md`（v0→v1 迁移记录 + 实现说明，无表结构差异）。
- 验收自测：① `python -m pytest tests -q --basetemp=".pytest-tmp"` → **69 passed**（既有 39 + 新增 30）；② `python -m materials init-db` 在 `backend/data/db/m2-materials.db` 建出 7 表、重复执行不报错（幂等），inspector 验证 7 表 + 唯一约束（指纹 type+value、源 platform+key、platform_material_id×2）；③ `python -m materials pool --limit 5` 空库输出空列表不报错；④ repo 集成冒烟：插 1 视频+1 图片，重复 claim 同一 md5 第二次返回重复标记，update_evaluation 写审计+更新当前值（SMOKE_OK）。
- 差异：与 DDL 无表结构差异；实现细节（TEXT ISO8601 UTC 时间戳、认领事务语义、blocked 人工接管、合规同步）已记入 database/README.md v1 说明。
- 备注：未运行任何 git 命令；只操作本模块库（m2-materials.db）与 pytest 临时库；未改动 backend/sourcing/*；未写明文密钥；全部产出 UTF-8 无 BOM；子代理 F 并行产出的 downloader.py/storage.py 未触碰，其配置读取用 getattr 兜底与基座兼容。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 1 · 子代理 D 验收）

- 完成任务：按宪法第 9 节验收子代理 D（id 02d5fe74）产出——① 核验文件齐全（backend/materials/ 7 文件 + test_materials_tables 12 例 + test_materials_repo 18 例 + conftest 追加 fixtures + database/README.md v0→v1）；② 独立复跑全量测试 `python -m pytest tests -q --basetemp=".pytest-tmp"` → **82 passed**（39 sourcing + 30 materials 基座 + 13 F 并入的 storage 用例），既有测试未破坏；③ 复核 D 自测关键项：init-db 幂等、7 表+唯一约束 inspector 验证、DuplicateAssetError 认领语义、evaluation 审计回流（D 报告中 SMOKE_OK，已重置开发库为纯净 7 表）。
- 验收结论：**D 验收通过**。硬规格常量集中 config.py（对齐 context/README 数据字典与 database/README DDL），repo 接口与 F 的 DownloadJobRepo 协议兼容（getattr 兜底延迟导入）。
- 产出文件：`_management/modules/m2-materials/progress.md`（D 任务勾选 100%，模块完成度更新）；本日志追加验收条目。
- 当前阻塞：无。F（ecc646f4）仍在执行（storage/downloader/downloader_api 已落盘，test_materials_downloader 未出、未报完成）；待 F 完成通知后验收并通知总控备份（里程碑：asset_* 表可建）。

---

### 2026-08-28 | 子代理 F（id ecc646f4）| M2 自动收集素材 | 角色：子代理（素材下载中台 v0.1）

- 完成任务：实现素材下载中台 v0.1（与 D 的 ORM 解耦并行）——
  - `backend/materials/storage.py`：Storage ABC（put/put_file/read/exists/delete/stat + key_for 分层 `asset_type/YYYYMM/`）；LocalStorage（默认 MATERIALS_STORAGE_DIR 或 data/materials，自动 mkdir，防路径穿越）；MinIOStorage 骨架（凭据只读 MATERIALS_MINIO_* 环境变量，构造不报错，IO 方法明确 NotImplementedError，R-M2-22）。
  - `backend/materials/downloader.py`：fetch_file（requests 流式 + Range 断点续传 + content-length 校验 + 416 全量重下）；错误分类（429/403→RATE_LIMIT、401→AUTH_REQUIRED、404/410→NO_MATCH、其他 4xx→PLATFORM_REJECT、5xx/网络→UNEXPECTED）；compute_md5；退避（RATE_LIMIT 180s/TIMEOUT 60s/NO_MATCH 120s/其他 60s，节流 0~4 ×1/2/4/8/16，AUTH_REQUIRED 转 blocked 人工）；熔断（连续失败 ≥2 → asset_sources.risk_control=1，冷却后探针自动恢复）；DownloadJobRepo 协议 + InMemoryDownloadJobRepo（fake）+ SqlAlchemyDownloadJobRepo（延迟对接 D 的 repo，strict 门禁未就绪给清晰报错，自包含 SQL 实现直接跑 D 的表）；DownloadWorker（租约 45min 过期回收 + 同 worker 重启恢复 + 500M 硬规格预警 + 证据脱敏 redact_url）；DownloaderService 集成入口。
  - `backend/materials/downloader_api.py`：标准库 ThreadingHTTPServer 多实例 HTTP API（POST/GET /jobs、GET /jobs/<id>、/jobs/<id>/retry、/health，JSON 全 UTF-8，幂等入队）。
  - `backend/materials/__main__.py`：**只追加** `download` 子命令（--once/--loop/--serve --port，--repo auto|memory），未覆盖 D 的 init-db/pool（已读 D 内容后编辑合并）。
  - `backend/tests/test_materials_storage.py`（11 例）+ `backend/tests/test_materials_downloader.py`（21 例：本地 http.server 场景 ①成功+MD5 ②断点续传/416 ③错误分类 ④退避 next_run_at ⑤熔断+探针恢复 ⑥租约过期回收+重启恢复 ⑦fake repo 零 DB + 入队幂等/retry + worker 全链路 + HTTP API 冒烟）。
- 决策记录：`_management/modules/m2-materials/decisions.md` 追加 9 行（DownloadJobRepo 协议扩展、错误码→退避基表、熔断持久化+探针、两级断点、入队幂等口径、stdlib API 零依赖、finish_success 三字段入 evidence_json、priority 不落库、熔断默认阈值 3→2 对齐任务书）。
- 验收自测：① 全量 `python -m pytest tests -q --basetemp=".pytest-tmp"` → **101 passed**（39 sourcing + 30 D 基座 + 32 F）；② 本地场景 ①~⑦ 全过；③ SqlAlchemyDownloadJobRepo 真实 SQLite 冒烟 8 项全过（D 的 ORM 建表 + strict=False 直连，修掉 2 个 INSERT NOT NULL 列缺漏）；④ `python -m materials --db-url sqlite:///./.pytest-tmp/cli-serve.db download --serve` 启动成功，/health 200 JSON（worker_id=hostname-随机后缀），POST /jobs 201 + 详情/列表/retry 200，worker 真实处理任务并退避记账，测后已关停无残留进程。
- 对接说明（待总工集成验收）：SqlAlchemyDownloadJobRepo 为自包含 SQL 实现（协议实现者），D 的 repo.py 就绪后 strict 门禁通过即在其 asset_* 表上运行；finish_success 的 file_path/md5/size 写 evidence_json（DDL 无列），asset_id 回填归 AssetRepo；priority 仅接受不落库；熔断用合成 source_key='__circuit_breaker__' 行写 asset_sources。
- 备注：未运行任何 git 命令；只操作 backend/materials/* 与 backend/tests/test_materials_*；对 D 的 config.py 仅改 1 行（circuit_breaker_failures 3→2，已记 decisions 待总工裁定）；未写明文密钥（MinIO 测试值用环境变量注入）；全部产出 UTF-8 无 BOM（write/edit 工具）；发现 **端口 8787 被工作区另一服务（captcha-vision-gateway）占用**，默认端口冲突需总控协调（建议改 8788 或与占用方错开）。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 1 · 子代理 F 验收 + 批次 1 收官）

- 完成任务：按宪法第 9 节验收子代理 F（id ecc646f4）产出——
  ① 独立复跑全量测试 `python -m pytest tests -q --basetemp=".pytest-tmp"` → **101 passed**（39 sourcing + 30 D + 32 F），与 F 自测一致；
  ② 抽查代码：`config.py` 硬规格常量齐全、`DownloadConfig`（circuit_breaker_failures=2）；`__main__.py` 保留 D 的 init-db/pool、F 仅追加 download 子命令（先读后编辑合并）；
  ③ **真实库集成冒烟（总工独立执行）**：D 的 ORM 建表 + F 的 SqlAlchemyDownloadJobRepo 全链路——入队幂等（同 URL 二次入队返回同任务）、claim_next 领取、finish_failure 退避记账、finish_success 回写 evidence_json（file_path/md5/size 按设计落 evidence）、熔断写读 asset_sources.risk_control、DownloaderService.run_once 空队列不崩 → **INTEGRATION_SMOKE_OK**；
  ④ 裁定 F 对 config.py 的改动（circuit_breaker_failures 3→2）**通过**（对齐 09 文档「连续失败≥2」与 sourcing 基线口径），记入 decisions.md；
  ⑤ **端口冲突处理**：8787 被 captcha-vision-gateway 占用（P-008）→ 已改 `__main__.py` 默认端口 **8788**、登记全局踩坑日志 P-008、环境事实表标注，记 decisions。
- 产出文件：`backend/materials/__main__.py`（默认端口 8787→8788）；`_management/modules/m2-materials/progress.md`（F 100%、批次 1 收官、完成度 **30%**）；`decisions.md`（+2 行总工裁定）；`_management/logs/pitfall-log.md`（+P-008）；`context/README.md`（+端口环境事实）；本日志追加条目。
- 验收结论：**批次 1 全部验收通过**。里程碑达成：`asset_* 表可建` ✅（data/db/m2-materials.db 7 表）+ `下载中台可跑` ✅（本地场景 + 真实库集成冒烟 + HTTP API /health 200）。
- 当前阻塞：无。已请总控提交备份（里程碑）；等待总控确认后推进批次 2（E 双去重 / C ffmpeg / A TikTokDownloader）。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 2 派发）

- 完成任务：总控确认批次 1 验收 + v0.3 备份已提交（101 测试），批准推进批次 2；**环境探测**（PowerShell 只读）：ffmpeg/ffprobe **未安装**、TikTokDownloader **未安装**（pip 仅 tiktoken）；按总控指示调整任务模式并写入任务书——C「先实现+测试用 mock，环境就绪后切换（禁止安装 ffmpeg）」、A「锁定版本设计封装+fixtures 测试（fake CLI 零外网，禁止联网安装）」、E 正常实现（关键帧抽取用 FrameExtractor 抽象，Mock 测试，零真实 ffmpeg）。
- 并行派发三个自包含子代理任务书（背景/必读/目标/输出路径/验收标准/宪法要点/P-001/禁 git/禁明文密钥/UTF-8/环境事实）：
  - **E=4179c644**（backend/materials/dedup.py：compute_md5 + image_phash 复用 sourcing 口径 + FrameExtractor 抽象(FFmpeg/Mock) + hamming + DedupService 与 AssetRepo.claim_fingerprint 集成 + test_materials_dedup.py）
  - **C=487ca61b**（backend/materials/normalizer.py：detect_ffmpeg + FFmpegRunner 抽象(Process/Mock) + validate_specs 边界校验 + Normalizer 预检/转码/复检双校验 + config 追加 normalize 子配置 + __main__ 追加 normalize 子命令 + test_materials_normalizer.py，真实 ffmpeg 用例 skipif 保护）
  - **A=475a06d1**（backend/materials/collectors/tiktok_wrapper.py：TikTokDownloaderCLI search/author 下载 + 错误映射对齐下载中台码表 + config 追加 tiktok 子配置 + collectors/README.md 版本锁定与安装说明 + __main__ 追加 tiktok-download + test_materials_tiktok_wrapper.py fake CLI 全场景）
- 产出文件：`_management/modules/m2-materials/progress.md`（批次 2 三任务标记「已派发」+子代理 id + 环境待确认标注，任务书撰写 100%）；本日志追加条目。
- 当前阻塞：无。待批次 2 子代理完成通知 → 总工验收（读产出+跑 pytest --basetemp=".pytest-tmp"）→ 更新 progress.md/台账 → 通知总控提交备份 → 批次 2 收官后推进批次 3（B 视频号采集器、淘宝1688 复测）。

---

### 2025 体系建立日（第 3 轮）｜ M3 总工程师 ｜ M3 自动素材优化 ｜ 角色：总工

- 完成任务：① 落实总控两项裁决——REC-001（图片资产域归 M3，自建 opt_image_*；迁移包遗留表由 M0 评估归档）与 REC-002（上传双轨 UploadService，M3_UPLOAD_MODE=api|ui|semi，默认 api，先 fixtures 模拟）写入 decisions.md；② 按宪法第 9.2 节承担核心/骨架代码：新建 `backend/optimization/` 公共包（__init__/config.py（M3_* 环境变量配置：视频硬规格/图片规格/文案规格/LLM 参数/审核抽检/上传双轨）/models.py（领域模型 7 类）/tables.py（opt_* 9 表 ORM，对齐 database/README.md）/db.py（本模块独立库 data/db/m3-optimization.db）/compliance.py（复用 sourcing.compliance 词库 + 素材专用扩展：供应链词扩展、AD_BADGE_FORBIDDEN）/repo.py（CopywriteRepo/ImageRepo/CategoryMemoryRepo/EvaluationRepo 共享数据访问））；③ fixtures/optimization/ 落 3 个离线样本（product_fixture.json 家居日用含脏词、product_fixture_pet.json 宠物用品含供应链词、source_asset_fixture.json 原始素材契约）；④ 更新 progress.md（排期已批准、骨架完成、子代理 A/B 派发中）；⑤ 派发两个并行子代理。
- 产出文件：`backend/optimization/`（7 文件）、`backend/fixtures/optimization/`（3 JSON）、`_management/modules/m3-optimization/decisions.md`（+REC-001/REC-002）、`progress.md`（开发阶段状态）；本日志追加条目。
- **异常记录**：首轮派发的子代理-A（文案管线 v0.2，id 829cdbb9）与子代理-B（主图/详情图管线 v0.4，id af860c10）均在完成前中断（closing message 为空，判为环境/会话抖动，与 M2 批次 1 现象一致）；验收检查确认两子代理**均未落盘任何产出**（backend/optimization/copywriting/ 与 images/ 子包、test_optimization_*.py 均不存在，仅总工骨架在位）。
- 处理：按总控指示「产出为空则重新派发」——将重新派发子代理-A'（文案管线 v0.2）与子代理-B'（主图/详情图管线 v0.4），任务书保持自包含（背景/必读/目标/输出路径/验收标准/宪法要点/P-001/禁 git/禁明文密钥/UTF-8）。
- 当前阻塞：无。待重派子代理完成通知 → 总工验收（读产出 + 跑 pytest --basetemp=".pytest-tmp"）→ 更新 progress.md/decisions.md/台账 → 通知总控备份 → 验收通过后推进视频二创流水线（v0.3）。

---

### 2025 体系建立日（第 3 轮·续）｜ M3 总工程师 ｜ M3 自动素材优化 ｜ 角色：总工

- 异常记录（续）：重派的子代理-A'（id 08a85d20）与子代理-B'（id 1cc57a9e）亦在完成前中断（无 closing message，未落盘）。list_agents 显示 4 个实例（首轮 829cdbb9/af860c10 + 重派 08a85d20/1cc57a9e）均处于 **ready（可续跑）** 状态，产出仍为空——与 M2 批次 1 完全一致（环境/会话抖动导致首轮中断，send_message 可恢复）。
- 处理：按 M2 验证过的恢复路径——仅对**重派两个实例**发 send_message 续跑（消息已排队为下一回合）：08a85d20（文案管线 v0.2）、1cc57a9e（主图/详情图管线 v0.4）；**首轮两个实例不再唤醒**（任务重复，避免双写 backend/optimization/copywriting 与 images/ 冲突）。恢复消息重申：骨架只读、禁 git、禁明文密钥、UTF-8 无 BOM、pytest --basetemp=".pytest-tmp"。
- 当前阻塞：无。等待续跑子代理完成通知 → 验收（读产出 + 跑 pytest）→ 更新 progress.md/台账 → 通知总控备份 → 验收通过后推进视频二创流水线（v0.3）。

---

### 2026-08-28 | M0 总工程师 | m0-foundation | 角色：总工（开发阶段·小步进第 1 步）

- 完成任务（本步仅 1 件事，按总控极小程序化指示）：在 `_management/modules/m0-foundation/database/README.md` 落盘 **workflow_jobs 最终 DDL（SQLite）v0.2 定稿**——替换 v0.1 骨架，含：租约字段 `lease_owner`/`lease_expires_at`（45min 过期回收）、幂等唯一约束 `UNIQUE(product_id, stage, generation_version)`、错误码字段 `error_code`/`retry_after`（由 error_codes.backoff_seconds 计算）、证据字段 `evidence_json`（09/02 文档留痕）、`retry_count`、stage/status 枚举注释、4 个索引（status/stage/retry/lease）；时间戳 `_at` 后缀 UTC、JSON 内金额按分 int（REC-005/DA-001）。
- 产出文件：`database/README.md`（workflow_jobs 小节 v0.2）；`progress.md`（新增 A1-1 任务勾选 100%，基座开发 A 标注小步进 5%）；本日志追加条目。
- 前置说明（上轮中断前遗留）：`backend/foundation/` 包（tables.py/config.py/db.py/repo.py/__init__.py）已初步落盘，但字段命名为 `next_retry_at`/`result`，与总控指示的 `retry_after`/`evidence_json` 不一致；后续小步进到「foundation 包」步骤时将对齐为总控命名并重跑测试。A1 首个子代理（ae8c8544）中断无产出，不再恢复，改由总工直接小步进执行（总控指示）。
- 当前阻塞：无。等待总控唤醒第 2 步（tasks 表 DDL）。
