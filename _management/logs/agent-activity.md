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

---

### 2026-08-28 | M0 总工程师 | m0-foundation | 角色：总工（开发阶段·小步进第 2 步【补记】+ 第 3 步）

- 完成任务（第 2 步补记）：在 `database/README.md` 落盘 **tasks 表最终 DDL（SQLite）v0.2 定稿**——替换 v0.1 骨架，含：`job_id` 任务归属（workflow_jobs.id，跨库不建 FK）、`stage` 与 workflow_jobs 同枚举、状态/错误码字段（error_code/error_message/retry_count/retry_after）、租约字段（lease_owner/lease_expires_at）、幂等唯一约束 `UNIQUE(job_id, task_type)`、证据字段 `evidence_json`、3 个索引（job/status/retry）；时间戳 `_at` 后缀 UTC、JSON 内金额按分 int（REC-005）。
- 完成任务（第 3 步）：① 完整复核 `database/README.md` 五表 DDL——workflow_jobs/tasks（v0.2 定稿）与 logs/app_config/error_codes 均无乱码、字段对齐 REC-005（时间戳全部 `_at` 后缀、JSON 金额按分 int）；② 修正 REC-005 落实检查段落过时字段名（next_retry_at→retry_after、result→evidence_json）；③ **`backend/foundation/tables.py` 字段命名对齐 DDL**：WorkflowJob 改 `next_retry_at`→`retry_after`、`result`→`evidence_json`，索引改显式 Index 对齐 DDL 命名（idx_wj_*）；Task 补全 stage/error_message/retry_count/retry_after/lease_owner/lease_expires_at、job_id 改 NOT NULL、加 `uq_tk_idempotency` 幂等键与 idx_tk_* 索引、result→evidence_json；LogEntry/AppConfigRow/ErrorCode/种子数据保持不变。
- 产出文件：`database/README.md`（tasks 小节 v0.2 + REC-005 检查修正）；`backend/foundation/tables.py`（对齐 DDL v0.2）；`progress.md`（A1-3 勾选，基座开发 A 进度 15%）；本日志追加条目。
- 待办（下一步）：`backend/foundation/repo.py` 中 `next_retry_at`/`result` 引用需随 tables.py 改为 `retry_after`/`evidence_json`（本步未跑测试，按总控指示不执行）。
- 当前阻塞：无。等待总控唤醒下一步（foundation 包对齐/队列 API）。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 2 · 子代理恢复与重派）

- 异常记录与处理（延续批次 2 派发条目）：
  ① E（4179c644）多次中断但产出在推进（dedup.py 已落盘，调试 phash 测试数据时中断——其「渐变图距离仅 6，改随机噪声图」的判断正确），已 send_message 恢复并附断点指令；
  ② C（487ca61b）两次中断，normalizer.py 已落盘、测试未出，已按产出进度发精确断点指令恢复（补齐 test_materials_normalizer.py + config/CLI 追加 + 验收）；
  ③ **A（475a06d1）连续 4 次中断（含 2 次恢复后），产出仅空 `collectors/__init__.py`，判定会话不稳定而非任务问题——按「产出为空则重新派发」策略弃用 A，重派 A2=7d9dc741**（任务书自包含不变，注明可复用空 __init__.py；已派发后台运行）。
- 当前状态：E running、C running、A2 新派发运行中；批次 2 三个任务均在执行。
- 当前阻塞：无。待完成通知后验收（读产出 + pytest --basetemp=".pytest-tmp"）→ 更新 progress.md/台账 → 通知总控备份 → 批次 3。

---

### 2026-08-28 21:56 | P2 子代理 | m4-listing | 角色：子代理（重派版 · listing_gate）

- 完成任务：实现 M4 上架前校验硬门禁 `backend/services/listing_gate.py`（P2）——六项硬门禁，任一不通过 → 商品不入队（结构化拒绝，不套 WorkflowJob 执行期错误码）：
  - `ListingGateConfig`（pydantic-settings，env_prefix `LISTING_` + 构造函数注入，参考 sourcing/config.py）：标题 15/35、主图 ≥5、1:1 容差 0.02、SKU 成本下限 0（校验 cost_cents > 下限 → 默认成本必须 > 0）、类目白名单默认 9 类（复用 sourcing.config.DEFAULT_CATEGORY_WHITELIST）；
  - `ListingCandidate/SkuInput/PurchaseSettings` 输入模型（字段对齐 context 跨模块契约 5.1/5.2：product_id/title/category_id/category_name/qualification/main_images/detail_images/skus{cost_cents,price_cents}/purchase_settings{限购 per_user+period/物流 freight_template_id/售后 after_sale}，缺字段按未提供拒绝）；
  - 12 个门禁项 → 12 个原因码：title_length/title_compliance/category/qualification/images_count/images_ratio/images_duplicate/detail_images/sku_cost/sku_price/purchase_settings/compliance_preview；`GateResult(passed, items, rejected_reason_codes)`；
  - 图片校验用 Pillow（宽高比容差）+ SHA256 去重（主图必须互不相同，R21「不全相同」）；合规规则复用 sourcing/compliance.py（词库单一事实源：BRAND_WORDS/PROHIBITED_WORDS/SUPPLY_CHAIN_WORDS/EFFICACY_WORDS/sanitize_title/ComplianceEngine 全量预审）——无任何真实平台调用（REC-004）。
- 产出文件：`backend/services/listing_gate.py`、`backend/services/__init__.py`（包入口 + 重导出）；`backend/tests/test_listing_gate.py`（25 例：happy path、六项各自失败、边界 15/35 字符与恰好 5 张互不相同主图、配置注入 title 区间/主图下限/SKU 成本下限/容差/类目白名单、结构化拒绝；测试图片 Pillow 在 tmp 生成，零大文件 fixtures）。
- 验收自测：① `python -m pytest tests/test_listing_gate.py -q --basetemp=".pytest-tmp"` → **25 passed**（首跑 2 例失败：all-identical 用例被 valid_candidate 默认图片覆盖文件导致哈希误判 + 配置注入用例数据笔误，已修复重跑全绿）；② 全量 `python -m pytest tests -q --basetemp=".pytest-tmp"` → **161 passed, 1 skipped**（既有 136 + 新增 25，无回归）。
- 当前阻塞：无。待总工验收（P-002 共享 Chrome 登录态/OpenAPI 契约核对不属本任务范围）。
- 备注：未运行任何 git 命令；未写任何明文密钥；未改动 sourcing/* 与 materials/*（仅只读复用 compliance.py/config.py）；全部产出 UTF-8 无 BOM（write/edit 工具）。

---

### 体系建立日 ｜ M1 总工程师 ｜ M1 自动选品（m1-sourcing） ｜ 角色：总工（批次 1 · S1a 验收 + S1b 处理）

- 完成任务：① **S1a 验收通过**（子代理 32dfb48b）——独立复跑全量测试 `python -m pytest tests -q --basetemp=".pytest-tmp"` → **186 passed, 1 skipped**（含 M2/M3 新测试，无回归）；代码抽查确认：config.py 默认 DSN=`sqlite:///data/db/m1-sourcing.db`（REC-007 注释完整、SOURCING_DB_URL 覆盖保留）、db.py 文件型 SQLite 自动 mkdir 父目录（仅目录不存在时执行，与 M2/M3 db.py 模式一致）、新增 test_db_dsn.py 2 例质量合格（默认 DSN 断言 + 父目录自动创建/建表验证）、backend/README 快速开始同步；未触碰 S1b 范围文件（pipeline/scoring/tables/models/compliance 时间戳核验无改动）；② **S1b 验收不合格**——子代理 58579182 连续 3 次运行中断（closing message 为空），核实**零产出落盘**（tables.py 无 m1_ 表、config.py 无 ad_data_max_age_days、pipeline.py 无改动、无 test_m1_*.py、migrations 未建），判为会话环境抖动（与 M2/M3 批次中断现象一致）；③ 已第 4 次 send_message 恢复，消息含任务澄清（config.py 现可安全修改——ScoringConfig 在 config.py 内新增 ad_data_max_age_days；pydantic v2 禁止 setattr 未声明字段，测试用 load_config(**overrides) 构造）。
- 产出文件：`progress.md`（S1a 勾选 100%、完成度 10%、S1b 标注待验收）；S1a 产出已验收：`backend/sourcing/config.py`/`db.py`、`backend/README.md`、`backend/tests/test_db_dsn.py`。
- 当前阻塞：无。待 S1b 第 4 次恢复结果——若仍零产出则按「产出为空则重新派发」策略弃用并重派（对齐 M2-A/M3 处理先例）；S1a 验收通过后已具备派发 S2（ad_backfill，依赖 S1b 的 m1 表与过滤逻辑，故 S2 随 S1b 落地后派发）。
- 备注：未运行任何 git 命令；未读写其他模块库（data/db 下 m2-materials.db 等仅发现未触碰）；全部文件经 write/edit 工具 UTF-8 无 BOM；无明文密钥。

---

### 2026-08-28 ｜ 子代理 C ｜ M2 自动收集素材（m2-materials） ｜ 角色：子代理（批次 2 · ffmpeg 标准化器）

- 完成任务：实现 ffmpeg 标准化器（任务书完整项），「先实现 + 测试用 mock，环境就绪后切换」模式（本机 ffmpeg/ffprobe 未安装，已探测确认，未尝试安装）：
  - `detect_ffmpeg()`：env MATERIALS_FFMPEG_PATH 优先 → PATH；返回版本字符串或 None，绝不抛异常；
  - `FFmpegRunner` 抽象（probe/transcode）+ `FFmpegProcessRunner` 真实实现（subprocess.run，超时配置化；ffmpeg/ffprobe 缺失 raise `NormalizerError` 含安装指引，R-M2-15 不静默）+ `MockFFmpegRunner` 测试注入（零真实 ffmpeg 依赖，R-M2-17）；
  - `validate_specs`：分辨率/比例(9:16±0.01)/格式/大小/时长 五维校验，返回 `{passed, failures:[{field,reason,value}]}` 逐项可解释；
  - `Normalizer`：probe 预检 → ffmpeg 转码（命令对齐 05 示例，参数集中 config.normalize）→ 转码后复检硬规格（双校验 R-M2-12）；输出目录自动建；ffmpeg 缺失时 probe/normalize 均 raise NormalizerError；
  - config.py **只追加** `NormalizeConfig` 子配置（嵌套 BaseSettings，MATERIALS_FFMPEG_PATH/FFPROBE_PATH 直接映射，已实测 pydantic-settings 2.15）；`__main__.py` **只追加** `normalize` 子命令（先探测 ffmpeg 缺失 → 清晰错误 exit 1；复检未通过 exit 1；输入不存在 exit 2），未覆盖 init-db/pool/download（并行子代理的 dedup-check 亦完好）。
- 产出文件：`backend/materials/normalizer.py`、`backend/materials/config.py`（追加 NormalizeConfig）、`backend/materials/__main__.py`（追加 normalize 子命令）、`backend/tests/test_materials_normalizer.py`（34 用例：validate_specs 边界 13、probe 透传 4、normalize mock 全链路 5、detect_ffmpeg 2、ProcessRunner 缺失路径 3、行为锁定 4（ffprobe JSON 解析/命令锁定 05 示例/超时/失败 exit）、config env 映射 2、真实转码 skipif 1）。
- 验收自测：① 单独 `python -m pytest tests/test_materials_normalizer.py -q --basetemp=".pytest-tmp"` → **33 passed, 1 skipped**；② 全量 `python -m pytest tests -q --basetemp=".pytest-tmp"` 连续两遍 → **186 passed, 1 skipped 全绿**（无回归）；③ `python -m materials normalize --input x.mp4`（ffmpeg 缺失）→ stderr 清晰错误（含「ffmpeg 缺失」+ 安装指引 winget/官网/brew/apt + MATERIALS_FFMPEG_PATH 提示），**EXIT_CODE=1**；④ 真实转码用例 `skipif(not detect_ffmpeg())` 本机自动跳过，环境就绪后自动启用无需改代码。
- 环境坑记录：全量运行出现间歇性失败（2 failed / 79 errors），连续串行重跑即稳定全绿——判为**并发 pytest 进程共享 `.pytest-tmp` 互相清理**所致（工作区多个子代理并行跑测试），非代码问题；已记入汇报，建议总工/总控知悉。
- 当前阻塞：无（ffmpeg 环境就绪由总控/运维处理；环境就绪后切换步骤见汇报）。
- 备注：未运行任何 git 命令；未安装任何软件（含 ffmpeg）；未改动 backend/sourcing/* 与既有 materials 文件语义（仅追加 config/CLI）；未写任何明文密钥；全部产出 UTF-8 无 BOM（write/edit 工具）。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（v0.2 数据层派发）

- 完成任务：① 落实总控验收与指示——DA-001 时间口径修订完成（context/README 数据字典、database/README、risks、data-requests 全部改为「时间存储 UTC（ISO8601 带时区）、展示转 UTC+8、时间戳 *_at」，与总控裁决一致）；② 勘察 backend 基线（sourcing/materials 包：config/db/tables/models/repo/conftest/requirements），确认 M5 落地模式（SQLAlchemy 2.0 + pydantic-settings + Database 封装 + 函数式 repo，包名 backend/ads/，D-M5-04）；③ 关键决策落档 decisions.md（D-M5-01~07：金额分/时间 UTC、英文枚举存储、evaluation 与 M2 共口径 exploring/efficient/potential、包名 ads、app_config 只读、快照幂等唯一约束、v0.3 抽象接口+fixtures 模拟）；④ 派发 v0.2 数据层子代理（id bc855a68，任务书自包含：必读文件/目标/输出路径/枚举口径/宪法纪律/验收标准）。
- 产出文件：`_management/modules/m5-ads/context/README.md`（+时间口径修订）、`database/README.md`（+时间口径修订）、`risks.md`（+时区行修订）、`context/data-requests.md`（+时间口径修订）、`decisions.md`（D-M5-01~07）、`progress.md`（v0.2 开发中标注）；本日志追加条目。
- **异常记录**：子代理 bc855a68 在完成前中断（closing message 为空，判为环境/会话抖动，与 M2/M3 批次中断现象一致）；核实**零产出落盘**（backend/ads/ 不存在）；已 send_message 恢复（ready 可续跑），恢复消息含任务要点重申（包结构/枚举/纪律/验收）已排队为下一回合。
- 当前阻塞：无。待续跑子代理完成通知 → 总工验收（读产出 + 跑 pytest --basetemp=".pytest-tmp"）→ 更新 progress.md/台账 → 通知总控备份（里程碑：ad_* 表可建）。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 2 · 子代理 C 验收）

- 完成任务：按宪法第 9 节验收子代理 C（id 487ca61b，ffmpeg 标准化器）——
  ① 独立复跑 `python -m pytest tests/test_materials_normalizer.py -q --basetemp=".pytest-tmp"` → **33 passed, 1 skipped**（与 C 自测一致；真实转码用例 skipif 本机自动跳过）；
  ② 抽查代码：config.py 追加 NormalizeConfig（MATERIALS_FFMPEG_PATH/FFPROBE_PATH 映射、transcode_timeout/output_format/crf/ratio_tolerance），既有配置零改动；__main__.py 追加 normalize 子命令（init-db/pool/download 完好）；
  ③ 行为验证：`python -m materials normalize --input x.mp4`（ffmpeg 缺失）→ stderr 清晰错误（含安装指引 winget/官网/brew/apt + 环境变量提示），**EXIT_CODE=1**；
  ④ 编码复核：normalizer.py/config.py/__main__.py/test_materials_normalizer.py 全部 UTF-8 无 BOM（PowerShell 只读复核）。
- 验收结论：**C 验收通过**。mock 模式交付（ffmpeg 未安装，环境待确认）；环境就绪后 detect_ffmpeg() 返回非 None，真实转码用例与 FFmpegProcessRunner 自动启用，无需改代码（切换步骤已记录）。
- 环境事实登记：**P-011**（工作区多代理并行跑 pytest 共享 `.pytest-tmp` 互相清理 → 间歇性 errors，串行复跑即全绿；验收结果以连续两次全绿为准）。
- 产出文件：`_management/modules/m2-materials/progress.md`（C 勾选 100%、A 行更新为 A2=7d9dc741）；`_management/logs/pitfall-log.md`（+P-011）；本日志追加条目。
- 当前阻塞：无。批次 2 剩余：E（4179c644）运行中、A2（7d9dc741）运行中；待二者完成通知后验收 → 批次 2 收官通知总控备份。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 2 · 子代理 E 验收）

- 完成任务：按宪法第 9 节验收子代理 E（id 4179c644，双去重器）——
  ① 验收命令首次复跑遇 50 errors（PermissionError，P-011 并发 pytest 共享 .pytest-tmp 互相清理）→ 按 P-011 纪律改**唯一 basetemp**（`.pytest-tmp-m2e`）串行复跑 → **55 passed**（test_materials_dedup 25 + tables 12 + repo 18），与 E 自测一致；
  ② 抽查代码：`image_phash` 直接调用 `sourcing.dedup.phash_from_bytes/phash_hex`（逐位一致，测试锁定）；`DedupService.check_video/check_image/claim_and_register` 与 `AssetRepo.claim_fingerprint` 集成、冲突抛 `DuplicateAssetError` 不静默吞；阈值默认 `config.dedup.phash_hamming_threshold`=8 与 sourcing 口径一致；`FrameExtractor` 抽象（FFmpeg/Mock）可插拔；
  ③ 验收 E 冒烟结论：临时库注册图片指纹 → 同图二次检查 is_duplicate=true reason=md5；视频 mock 帧路径由 pytest 覆盖；视频缺 ffmpeg 时 dedup-check CLI 清晰报错 exit 1（R-M2-15）。
- 验收结论：**E 验收通过**。阈值校准结论：8 对压缩/缩放鲁棒（同图距离 0、随机噪声异图 ≈30）；纯色/低纹理图 DCT 判别力弱（红 vs 蓝仅 6）→ 建议 fixtures 用真实素材校准；视频关键帧阈值待装 ffmpeg 后以真实转码样本校准。
- 产出文件：`_management/modules/m2-materials/progress.md`（E 勾选 100%）；本日志追加条目。
- 当前阻塞：无。批次 2 剩余：A2（7d9dc741）运行中；待其完成通知后验收 → 批次 2 收官（E/C 已验收）通知总控备份。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（v0.2 数据层验收·通过）

- 完成任务：按宪法第 9 节验收子代理 bc855a68（v0.2 数据层）产出——
  ① 读交付说明 `_management/modules/m5-ads/REPORT_v0.2.md`（文件清单/测试结果/偏差/纪律核对齐全）；
  ② 文件核验：backend/ads/ 7 文件（__init__/config/models/tables/db/repo/__main__）+ tests/test_ads_tables.py(19 例) + test_ads_repo.py(14 例) + conftest.py 仅末尾追加 cfg_ads/db_ads；
  ③ 代码抽查：tables.py 五表字段/枚举英文存储（status/target_type/diagnosis/evaluation 与 M2 共口径/upload_status/error_code 09 码表）全部正确，金额=int 分、时间=DateTime(timezone=True)+utcnow、时间戳 *_at、snapshot 唯一约束 uq_snapshot_campaign_time、material_id unique；repo.py 函数式（read_app_config 只读+原生 SQL+表不存在兜底、campaign CRUD、run 回写、snapshot/material 幂等 upsert、account 单例+节流 0~4 封顶、sum_spend_since/count_active_campaigns 预算止损辅助）；
  ④ **独立复跑**：定向 `pytest tests/test_ads_tables.py tests/test_ads_repo.py -q --basetemp=".pytest-tmp"` → **27 passed**；全量 `pytest tests -q --basetemp=".pytest-tmp"` → **258 passed / 5 failed / 1 skipped**（5 个失败均为 M0 foundation 既有问题：naive/aware 时间 TypeError×2、表断言列顺序、熔断时序，与 ads 无依赖，未改既有测试；子代理报告的 7 失败中 2 个 materials WinError 32 抖动本轮未复现）；
  ⑤ 口径对齐修订：context/README.md 数据字典 `ad_account_states.status` 枚举 normal→active（以任务书/代码为准）；
  ⑥ init-db 已建库：backend/data/db/m5-ads.db（5 表齐全）。
- 验收结论：**v0.2 数据层验收通过**。里程碑达成：**ad_* 表可建** ✅（5 表 + repo 层可测可跑 + CLI init-db 幂等）。
- 产出文件：`backend/ads/*`（7 文件）、`backend/tests/test_ads_tables.py`、`test_ads_repo.py`、`conftest.py`（追加）、`backend/data/db/m5-ads.db`（不入 git）、`_management/modules/m5-ads/REPORT_v0.2.md`、`progress.md`（v0.2 勾选、完成度 **30%**）、`context/README.md`（+status 枚举对齐）、本日志追加条目。
- 当前阻塞：无。已请总控提交备份（里程碑：ad_* 表可建）；待总控确认后推进 v0.3 执行层（托管执行器 Playwright·抽象接口 + fixtures 模拟，依赖总控待用户确认清单）。
- 备注：未运行任何 git 命令；未读写其他模块库；未写明文密钥；验收复跑测试命令均带 --basetemp=".pytest-tmp"（P-001）。

---

### 2026-08-28 ｜ S1b 子代理 ｜ M1 自动选品 ｜ 角色：子代理

- 完成任务：任务包 S1b（打分维度扩展 + app_config 白名单接线 + m1 投放转化表 DDL）——
  ① config.py ScoringConfig 新增 `ad_data_max_age_days=7.0`（投放转化新鲜度阈值，经总工澄清允许改动 config.py）；
  ② tables.py 新增 `M1AdConversionCache`（m1_ad_conversion_cache：唯一键 category+period_start+period_end，sales_amount INTEGER 分，category/period 索引）与 `M1AdConversionIngest`（m1_ad_conversion_ingests：唯一键 source_file+period_start+period_end+generated_at）；
  ③ pipeline.py：`_load_category_whitelist()` 读 app_config.category_whitelist 注入 ComplianceEngine（键缺失/类型非法/异常一律回落 config 默认，不抛异常，persist=False 兼容）；两处 ad_by_cat 组装统一走 `_fresh_ad_by_category()` 过滤（generated_at 超 ad_data_max_age_days 或 sample_count<5 → 置空视为无数据不传 ad_roi/ad_sales；fixtures 旧格式无元数据 → 可用，既有 39 测试行为不变）；ad_sales 优先取 sales_amount 回落 sales；
  ④ 迁移脚本 `_management/modules/m1-sourcing/database/migrations/v0.1_m1_ad_tables.sql`（SQLite 幂等 DDL：IF NOT EXISTS + 唯一约束，与 ORM 一致）+ 同目录 README.md（三种执行方式 + PG 类型映射）。
- 产出文件：`backend/sourcing/config.py`（+1 配置项）、`tables.py`（+2 ORM 类）、`pipeline.py`（白名单接线 + 新鲜度/弱样本过滤）、`migrations/v0.1_m1_ad_tables.sql`、`migrations/README.md`、`backend/tests/test_m1_ad_tables.py`(9)、`test_scoring_ad_freshness.py`(8)、`test_compliance_appconfig.py`(6)。
- 测试结果：新增 21 passed（2.47s）；全量 `python -m pytest tests -q --basetemp=".pytest-tmp"` → **258 passed / 5 failed / 1 skipped**（5 个失败均为 M0 foundation 既有问题，与 M5 总工台账记录一致：naive/aware 时间 TypeError×2、表断言列顺序、熔断时序；foundation 测试仅 import foundation 包，与 sourcing 零依赖，未改既有测试）；非 foundation 隔离运行 **234 passed + 1 skipped** 全绿。
- 当前阻塞：无（5 个 foundation 失败属 M0 范围，建议总工知悉并可向总控反馈）。
- 备注：未运行 git 命令；未写明文密钥；未修改 db.py / backend/README.md / scoring.py；写文件均用 write/edit 工具（UTF-8 无 BOM），未用 PowerShell 写中文。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（v0.3 执行层派发）

- 完成任务：总控批准 v0.3 执行层排期（2 子代理：托管执行器 + 投放设置，先抽象接口 + fixtures 模拟，不依赖真实登录态）；总工承担架构设计层——先落盘两个公共契约骨架：① `backend/ads/ui_config.py`（ShopAdsUiConfig：pages/selectors/batch_size/item_interval_s/page_timeout_ms/screenshot_dir/page_signature，选择器按页面分组含两步操作与投放管理列表预留，真实选择器值待实机校准，fixtures 阶段可为空）；② `backend/ads/interfaces.py`（PageOps Protocol 最小操作集 + PageChangedError，Playwright 语义子集，两子代理共用避免并行文件冲突）；随后并行派发两个自包含子代理任务书（背景/必读/目标/输出路径/验收标准/宪法要点/P-001/禁 git/禁明文密钥/UTF-8/禁改公共骨架与 v0.2 定稿）。
- 派发子代理：**① 托管执行器=861a44a5**（backend/ads/executor.py：ShopAdsSession 会话管理/check_login、BrowserConnector 抽象 + MockBrowserConnector + PlaywrightBrowserConnector 骨架(NotImplementedError)、MockPageOps、verify_page_signature page_changed 检测（PageChangedError 证据）、ShopAdsExecutor.add_product（≤50/批+间隔）与 run_batch 编排（延迟 import settings 用 getattr 兜底）、错误分类映射 page_changed/AUTH_REQUIRED/TIMEOUT + test_ads_executor.py）；**② 投放设置=91f77eec**（backend/ads/settings.py：pick_materials 素材优选纯函数（efficient>potential>exploring，仅 approved）、validate_submit 提交校验（余额/素材/预算→blocked+PLATFORM_REJECT）、SettingsForm（choose_target 三选一 roi/net_roi/goods、fill_roi、bind_materials {mid} 模板、submit 读 error_banner 关键词匹配）+ MockSettingsPage 独立实现不 import executor + config.py 仅尾部追加 target_roi_override/roi_recommended_source + test_ads_settings.py）。
- 产出文件：`backend/ads/ui_config.py`、`backend/ads/interfaces.py`（总工骨架）；`progress.md`（v0.3 开发中标注、两子代理已派发）；本日志追加条目。
- 当前阻塞：无。待两子代理完成通知 → 总工分别验收（读产出 + 跑 pytest --basetemp=".pytest-tmp"）→ v0.3 集成（executor↔settings 对接）→ 更新 progress.md/台账 → 通知总控备份 → 推进 v0.4 监控层。
- 备注：未运行任何 git 命令；未读写其他模块库；未写明文密钥；公共骨架与 v0.2 定稿文件由总工锁定，子代理只读/尾部追加。

---

### 2026-08-28 ｜ 子代理 A2 ｜ M2 自动收集素材（m2-materials） ｜ 角色：子代理（批次 2 · TikTokDownloader 二次封装）

- 完成任务：实现 TikTokDownloader 二次封装（抖音/快手/小红书批量下载 CLI 封装），「锁定版本设计封装 + fixtures 测试」模式（本机 TikTokDownloader 未安装，已探测确认，未尝试安装）：
  - `backend/materials/collectors/tiktok_wrapper.py`：`TikTokDownloaderError`（error_code + 脱敏证据）；`TikTokDownloaderCLI`（binary_path/timeout_seconds/output_dir/extra_args/config 可配，默认读 config.tiktok）；
    - `check_available()` 探测 binary（显式路径/PATH），缺失不抛异常返回 {available,version,error}（含安装指引 + 视频号不在范围声明 R-M2-05）；
    - `search_download(keyword,count,output_dir)` / `author_download(author_url_or_id,count,output_dir,platform)`：构造锁定 CLI 契约参数 → subprocess.run（超时、捕获 stdout/stderr、证据脱敏）→ 解析（文本/JSON 双模式）→ 返回 [{file_path,title,author,platform,source_url}]；
    - 错误分类映射对齐 downloader.py 码表：超时→TIMEOUT；登录失效/需要登录→AUTH_REQUIRED（不自动重试转人工，P-002）；频控/风控/验证码→RATE_LIMIT；签名/参数错误→PLATFORM_REJECT；无输出/无命中→NO_MATCH；其他→UNEXPECTED；
    - 脱敏（P-004）：redact_url（键集扩展 sec_uid/uid/user_id，urlencode %2A 还原为可读 ***）/ redact_text / redact_path（@作者 段掩码）；返回 source_url/title/author 即脱敏，file_path 保留真实路径；
    - 平台开关 `config.tiktok.enabled`（author_download 按达人 URL 平台校验，R-M2-21）；fake .py binary 用当前解释器启动（fixtures 模式）；
  - config.py **只追加** `TikTokConfig` 子配置（嵌套 BaseSettings + validation_alias 完整 env 名 MATERIALS_TIKTOK_BINARY/TIMEOUT_SECONDS/OUTPUT_DIR/VERSION_PIN/ENABLED，populate_by_name 保证字典覆盖；实测 pydantic-settings 2.15）；`__main__.py` **只追加** `tiktok-download` 子命令（--keyword/--author-url 二选一、--count、--output-dir、--json；binary 缺失清晰错误 exit 1），未覆盖 init-db/pool/download/normalize/dedup-check；
  - `backend/materials/collectors/README.md`：范围声明（视频号不在范围 R-M2-05）、版本锁定与安装说明（推荐版本线 TikTokDownloader 4.1.x，pip 安装命令示例，requirements 固定纪律，升级回归纪律 5 步）、CLI 契约、错误分类映射表、脱敏纪律、测试说明；
  - 测试 `backend/tests/test_materials_tiktok_wrapper.py`（34 用例）：fake CLI fixtures 全场景（临时 python 脚本按环境变量输出模拟文本/JSON 输出与退出码/超时）：①search_download 正常解析（files 模式 3 条 + JSON 模式 2 条）②author_download 参数构造（--mode author --target --count --output）③错误映射各分支（RATE_LIMIT/AUTH_REQUIRED/PLATFORM_REJECT 特征词参数化、TIMEOUT sleep、NO_MATCH 空输出、UNEXPECTED 非 0 无特征、证据脱敏）④binary 缺失（check_available=False + search 清晰错误）⑤脱敏（fake 输出含 sec_uid/a_bogus/token 敏感值，断言返回结果与日志无明文）+ redact_* 直接单测 + JSON 解析/去重 + 平台开关 + config env 映射 + CLI 子命令（缺失非 0 退出 / 注入 fake 跑通解析 / 失败特征词非 0 退出）。
- 验收自测：① 单独 `python -m pytest tests/test_materials_tiktok_wrapper.py -q --basetemp=".pytest-tmp"` → **34 passed**；② materials 相关定向 `-k "materials or db_dsn or listing_gate"` → **148 passed, 1 skipped**；③ 全量 `python -m pytest tests -q --basetemp=".pytest-tmp"` → 通过数 230+，**5 个失败均为 M0 foundation 既有问题**（naive/aware 时间 TypeError×2、熔断时序等，与 materials 零依赖，与 M5 总工/S1b 台账记录一致）；首轮全量出现的 28 errors 为并发 pytest 共享 .pytest-tmp 互相清理（P-011），串行复跑即消失。
- 文档同步：`decisions.md`（+子代理 A 决策行）、`context/README.md` 2.1（+实现快照：CLI 契约/配置/错误映射表/版本锁定/脱敏）、本日志追加条目。
- 当前阻塞：无（真实二进制安装由集成环境执行；对接步骤见 collectors/README.md「升级回归纪律」）。
- 备注：未运行任何 git 命令；未安装/下载任何软件（含 TikTokDownloader）；未改动 backend/sourcing/* 与既有 materials 文件语义（仅追加 config/CLI）；未写任何明文密钥（fake 输出中的假 Cookie/Token 同样脱敏，测试断言）；全部产出 UTF-8 无 BOM（write/edit 工具）。

---

### 体系建立日 ｜ M1 总工程师 ｜ M1 自动选品（m1-sourcing） ｜ 角色：总工（批次 1 · S1b 验收 + S1 收官）

- 完成任务：① **S1b 验收通过**（子代理 58579182，经 4 次中断后断点续跑完成，产出完整）——独立复跑全量测试 `python -m pytest tests -q --basetemp=".pytest-tmp"` → **331 passed, 4 failed, 1 skipped**，4 个失败全部为 **M0 foundation 既有问题**（test_foundation_queue ×2：naive/aware 时间、熔断时序；test_foundation_tables ×2：断言排序逻辑），与 sourcing 零依赖、与 M5 总工台账一致，**sourcing 域 62 passed 全绿（41 基线 + 21 新增）**；② 代码抽查通过：`tables.py` 两表 m1_ad_conversion_cache/ingests（唯一键 uq_m1_ad_cache/uq_m1_ad_ingest + 索引符合 database/README DDL）、`pipeline.py` `_load_category_whitelist()`（app_config 接线、异常回落 config 默认、persist=False 兼容）、`_ad_data_usable()`/`_fresh_ad_by_category()`（新鲜度+弱样本过滤、ISO 字符串含 Z 兼容、naive 按 UTC、旧格式无元数据按可用保既有 39 测试行为）、`config.py` ScoringConfig 新增 `ad_data_max_age_days=7.0`、迁移脚本 `migrations/v0.1_m1_ad_tables.sql`（幂等 SQL 镜像 + README 三执行方式 + PG 映射）、3 测试文件 21 例；③ 全量失败数随并行代理改动波动（4~17），sourcing 始终零失败；④ S1 收官：progress.md 完成度 10%→**20%**，里程碑达成（配置化/DSN 切换/m1 表/投放转化过滤链路，REC-007/008 落地）。
- 产出文件：S1b 产出 `backend/sourcing/tables.py`/`pipeline.py`/`config.py`（+1 配置项）、`database/migrations/`（v0.1 SQL + README）、`backend/tests/test_m1_ad_tables.py`/`test_scoring_ad_freshness.py`/`test_compliance_appconfig.py`；`progress.md`（S1b 勾选 100%、完成度 20%、S2 标注已派发）。
- 跨模块反馈：**M0 foundation 4~5 个测试失败（queue/tables）为既有问题**，非本模块引入（M5 总工台账亦记录一致数字）；已登记，提请总控转达 M0 总工。
- 当前阻塞：无。S2（ad_backfill，依赖 m1 表+过滤逻辑）已具备派发条件并已派发子代理；待完成验收后派发 S3（真实采集，需登录态就绪确认）。
- 备注：未运行任何 git 命令；未读写其他模块库；全部文件经 write/edit 工具 UTF-8 无 BOM；无明文密钥；验收复跑测试均带 --basetemp=".pytest-tmp"（P-001），并注意 P-011（并行 pytest 共享 basetemp 抖动，结果以串行复跑为准）。

---

### 2025 体系建立日（第 3 轮）｜ M4 总工程师 ｜ M4 自动上架（m4-listing） ｜ 角色：总工（P1/P2 开发推进）

- 完成任务：
  ① **P2 验收通过**（子代理 054c76d6，重派版）——独立复跑 `python -m pytest tests/test_listing_gate.py -q --basetemp=".pytest-tmp-m4"` → **25 passed**；代码抽查：`backend/services/listing_gate.py` 六项硬门禁（title 15–35+非虚构/category 白名单+资质/images ≥5 张 1:1 去重+详情图/sku_cost>0 且 price>cost/purchase_settings 全必填/compliance 复用 sourcing.compliance 单一事实源）+ `ListingGateConfig`（LISTING_ 前缀 pydantic-settings + 构造注入）+ 12 个结构化拒绝原因码（不套 WorkflowJob 执行期码）+ `GateResult.rejected_reason_codes`；未改动 sourcing/*（仅只读复用）；REC-004 零真实平台调用；
  ② **P1 三次派发均中断零产出**（0ed6ee31/cd2e6473/3a49a199，closing message 空，判为环境/会话抖动，与 M2/M3/M1 批次中断现象一致）；第二次中断根因确认为 **web_search 工具额度不足（Insufficient Balance）**——按 REC-003「不阻塞骨架」原则改由**总工亲自完成文档核对并落盘** `context/external-contracts.md`（接口清单/签名/配额/错误映射 + 待核对清单 T1~T7，来源标注 07/01 文档与项目契约，官方文档核对待额度恢复）；对三派（3a49a199）send_message 恢复续跑（消息自包含：P-011 新测试纪律 + 产出文件要点 + 契约基准 + 禁止项），已排队；
  ③ **P-011 纪律同步**：brief.md（验收总纲 4）/context/README.md（环境事实·测试行）/progress.md（二·五节通用宪法要点 + 验收门）全部改为模块独立 basetemp `--basetemp=".pytest-tmp-m4"`，注明全量回归由总控统一执行；
  ④ 全量回归观察：本回合一次全量跑 193 passed/2 failed（test_foundation_tables 列顺序断言），与 M5/M1 台账记录一致——**M0 foundation 既有问题，非 M4 引入**，提请总控转达 M0。
- 产出文件：`context/external-contracts.md`（新建，REC-003 核对稿）；`brief.md`/`context/README.md`/`progress.md`（P-011 纪律同步）；`progress.md`（P2 勾选 100%、完成度 **30%**、P1 标注恢复续跑中）；本日志追加条目。
- 当前阻塞：无。待 P1 三派续跑完成通知 → 验收（读产出 + `pytest --basetemp=".pytest-tmp-m4"`）→ 通知总控 v0.2 里程碑（薄封装骨架+单测可跑）→ 推进 P3 状态机与证据。
- 备注：未运行任何 git 命令；未读写其他模块库；未写任何明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM；PowerShell 仅做只读复核/测试运行。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（测试纪律更新 + 批次 2 · 子代理 A2 验收 + 批次 2 收官）

- 完成任务：
  ① **测试纪律更新落档**：总控下发宪法第 12 节（pytest 独立 basetemp，M2 用 `--basetemp=".pytest-tmp-m2"`，全量回归归总控）→ 已更新 `context/README.md`（环境事实）、`brief.md`（交付物表+子代理任务书条款）、`progress.md`（管理方式+里程碑注记），并 send_message 同步给运行中的 A2；
  ② **验收子代理 A2**（id 7d9dc741，TikTokDownloader 二次封装）：独立复跑 `python -m pytest tests/test_materials_tiktok_wrapper.py -q --basetemp=".pytest-tmp-m2"` → **34 passed**（fake CLI 全场景：正常解析/参数构造/错误映射各分支/超时/binary 缺失/脱敏）；抽查 tiktok_wrapper.py——错误映射特征词（AUTH_REQUIRED/RATE_LIMIT/PLATFORM_REJECT/NO_MATCH/TIMEOUT）对齐 downloader.py 码表、redact_url/redact_text/redact_path 三级脱敏（sec_uid/a_bogus/token 掩码）、版本锁定 4.1.x 写入 collectors/README.md（视频号不在范围声明 R-M2-05）；
  ③ **批次 2 收官**：E/C/A2 全部验收通过，progress.md 三任务 100%、完成度 30%→**45%**，里程碑 5 项达成。
- 产出文件：`progress.md`（批次 2 收官、完成度 45%）；`context/README.md`/`brief.md`（宪法第 12 节纪律落档）；本日志追加条目。
- 环境待确认（提请总控/运维）：**ffmpeg 未安装**（标准化器 mock 模式，就绪后自动切真实 runner）；**TikTokDownloader 未安装**（封装就绪，就绪后装 4.1.x）。
- 跨模块事项（提请总控转达 M0）：全量测试 5 failed 均为 M0 foundation 既有问题（与 M5/M1/M4 台账记录一致），本模块 sourcing+materials 范围始终全绿。
- 当前阻塞：无。**批次 2 收官，请总控提交备份**；批准后推进批次 3（B 视频号采集器自研签名+直链、淘宝/1688 采集复测、考古加/有米云榜单图缓存）。

---

### 2026-08-28 ｜ 子代理 A2 ｜ M2 自动收集素材（m2-materials） ｜ 角色：子代理（测试纪律更新后的复跑确认）

- 完成任务：按总控测试纪律升级（宪法第 12 节 / P-011：pytest 独立 basetemp，M2 统一 `--basetemp=".pytest-tmp-m2"`，禁止共用 `.pytest-tmp`，全量回归归总控统一执行）重跑本模块测试并同步文档：
  - `python -m pytest tests/test_materials_tiktok_wrapper.py -q --basetemp=".pytest-tmp-m2"` → **34 passed**（fake CLI 全场景 ①~⑤ 全绿）；
  - `python -m pytest tests/test_materials_tables.py tests/test_materials_repo.py -q --basetemp=".pytest-tmp-m2"` → **30 passed**（既有 materials 测试未破坏）；
  - `python -m pytest tests -q --basetemp=".pytest-tmp-m2" -k "materials or db_dsn or listing_gate"` → **191 passed, 1 skipped**（materials 模块范围全绿，含并行子代理 C/E 新增用例）。
- 文档同步：`backend/materials/collectors/README.md` 第七节测试命令改为 `.pytest-tmp-m2`（注明宪法第 12 节 / P-011 与全量回归归总控）；`backend/tests/test_materials_tiktok_wrapper.py` 文件头纪律行同步（独立 basetemp，禁止共用 `.pytest-tmp`）；context/README.md 环境事实·测试行已由总工落档（`.pytest-tmp-m2`）。
- 当前阻塞：无。其余任务书要求不变（fake CLI 全场景、禁 git、禁明文密钥、UTF-8 无 BOM 均已满足）。
- 备注：未运行任何 git 命令；未安装/下载任何软件；未写明文密钥；全部产出 UTF-8 无 BOM（write/edit 工具）。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（v0.3 · 投放设置验收通过 + 执行器 A2 重派）

- 完成任务：① **验收投放设置子代理 91f77eec 通过**——独立复跑定向 `pytest tests/test_ads_settings.py -q --basetemp=".pytest-tmp-m5"` → **25 passed**（0.05s，新纪律独立 basetemp）；读交付说明 REPORT_v0.3_settings.md（接口/对接/测试/偏差/纪律齐全）；代码抽查 settings.py：pick_materials（仅 approved、efficient>potential>exploring、同级 (impressions,gmv) 降序稳定排序、未知标签兜底）、validate_submit（余额>素材>预算优先级、PLATFORM_REJECT）、SettingsForm（choose_target 三选一 roi/net_roi/goods、fill_roi >0 校验两位小数、bind_materials {mid} 模板、submit 读 error_banner 关键词 blocked、banner 未配置按 TIMEOUT 语义）、MockSettingsPage 独立实现（零 import executor）、扩展 read_recommended_roi/resolve_roi（系统推荐优先/覆盖策略）——全部符合任务书；config.py 仅尾部追加 target_roi_override/roi_recommended_source；② **测试纪律更新（P-011，总控指示）**：M5 统一独立 basetemp `--basetemp=".pytest-tmp-m5"` 写入 context/README.md 环境事实（全量回归由总控统一执行）；③ **执行器子代理 861a44a5 ran out of room（上下文耗尽）且零产出** → 按 M2-A 先例弃用，重派 A2=ad45ec7a（任务书精简：内嵌 PageOps/ShopAdsUiConfig 契约、延迟 import settings 兜底、独立 basetemp 纪律、禁止改动既有文件），已后台运行。
- 产出文件：`progress.md`（投放设置勾选 100%、执行器 A2 标注）；`context/README.md`（测试命令 +P-011 独立 basetemp）；本日志追加条目。
- 当前阻塞：无。待执行器 A2 完成通知 → 验收（读产出 + 跑 pytest --basetemp=".pytest-tmp-m5"）→ v0.3 集成（executor↔settings 联调）→ 通知总控备份 → 推进 v0.4 监控层。
- 备注：未运行任何 git 命令；未读写其他模块库；未写明文密钥。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 3 派发）

- 完成任务：总控批准批次 3（v0.8 已备份推送）；**勘察**确认两项环境事实：① `fetch_taobao_references.py`/`fetch_1688_images.py` 半成品**不在当前工作区**（全工作区 glob 无 fetch_*.py，属旧半成品项目待迁移包对照）→ B2 任务由「复测」改为「按 05 文档与 R-M2-08 设计从零实现（配置化选择器+page_changed+视频降级只收图），命名对齐半成品便于后续合并」；② **考古加采集器未实现**（M1 REC-006 已裁决降级可选第四源）→ B3 任务改为「先做有米云榜单图缓存（sourcing 有米云链路已实测打通），BoardImageCache 多源接口化、kaogujia 预留」。
- 并行派发三个自包含子代理任务书（背景/必读/目标/输出路径/验收标准/宪法要点/宪法第 12 节独立 basetemp `.pytest-tmp-m2`/禁 git/禁明文密钥/UTF-8/环境事实）：
  - **B1=f331c395**（backend/materials/collectors/signer.py SignatureProvider 接口化 + wechat_video.py 页面层/直链层分离 + fixtures 离线 + wechat-collect CLI + test_materials_wechat_video.py）
  - **B2=03904cb8**（backend/materials/collectors/taobao_refs.py + alibaba_1688.py：同款图/商品视频、降级、page_changed 证据、fixtures + taobao-refs CLI + test_materials_taobao_1688.py）
  - **B3=f833480a**（backend/materials/collectors/board_image_cache.py：缓存键=source+board_id+item_id、幂等 hit、批量失败隔离、多源注册 youmi/kaogujia 预留 + board_cache 子配置 + test_materials_board_image_cache.py 本地 http.server）
- 产出文件：`_management/modules/m2-materials/progress.md`（批次 3 三任务「已派发」+子代理 id+环境事实标注）；本日志追加条目。
- 当前阻塞：无。待批次 3 完成通知 → 逐个验收（读产出 + pytest --basetemp=".pytest-tmp-m2"）→ 更新 progress.md/台账 → 通知总控备份 → 批次 4（标签合规、M3/M5 联调）。

---

### 2025 体系建立日（第 4 轮）｜ M4 总工程师 ｜ M4 自动上架（m4-listing） ｜ 角色：总工（P1 验收通过 · v0.2 里程碑达成 · P3 派发）

- 完成任务：
  ① **P1 验收通过**（子代理 6a582604，四派成功；前三派 0ed6ee31/cd2e6473/3a49a199 均中断零产出——根因 web_search 额度不足（Insufficient Balance）+ 会话抖动，已改由总工落盘 `context/external-contracts.md`（REC-003 核对稿，待核对项 T1~T7），四派任务书改为全内联契约 + 全新会话 + 强制第一动作写盘，成功）——独立复跑 `python -m pytest tests/test_wechat_openapi.py -q --basetemp=".pytest-tmp-m4"` → **6 passed**（0.21s）；代码抽查：`backend/adapters/wechat_openapi.py`（281 行）——`WechatOpenApiConfig`（WECHAT_ 前缀、mode 默认 mock）/`WechatApiError`（error_code 限定 WorkflowJob 码表）/`TokenBucket`（tokens/capacity/refill_rate/consecutive_failures/circuit_open_until + try_acquire 时间补充 + 连续失败≥2 熔断 300s）/`_sign`（SHA256+时间戳占位，注释待核对 T2）/`_call`（mock/live 分支、令牌桶、RATE_LIMIT 180s/TIMEOUT 60s/NO_MATCH 120s 退避、幂等重试 3 次、脱敏日志仅 api/task_id/error_code）/`_mock_dispatch`（9 接口 fixture，金额 int 分）/9 业务方法（task_id 透传）/`_get_token`（mock 假值 + live TODO 待核对 T1）；**v0.2 里程碑达成：薄封装骨架 + 单测可跑**；
  ② **P3 状态机与证据已派发**（子代理 b57d2057，全内联任务书：backend/listing/ 包 7 表 ORM 对齐 database/README.md DDL v0 + ListingStateMachine 9 态迁移 + R22 铁律断言（listed 必须带 link_verified 证据）+ 租约 45min 断点续跑 + 证据 JSON 写 listing_op_logs + init-db CLI + 双测试文件），运行中；
  ③ decisions.md 追加 D11（P1 mock 优先/live TODO 待核对）、D12（子代理派发策略：全内联契约任务书 + 第一动作写盘）；progress.md P1 勾选 100%、完成度 **45%**、里程碑节更新。
- 产出文件：`backend/adapters/wechat_openapi.py`、`backend/adapters/__init__.py`、`backend/tests/test_wechat_openapi.py`（子代理产出，已验收）；`decisions.md`（+D11/D12）、`progress.md`（P1 100%、完成度 45%、v0.2 里程碑）；本日志追加条目。
- 当前阻塞：无。待 P3 完成通知 → 验收（读产出 + `pytest --basetemp=".pytest-tmp-m4"`）→ 更新 progress.md/台账 → 推进 P4 拒审处理（依赖 P3）。
- 备注：未运行任何 git 命令；未读写其他模块库；未写任何明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM。

---

### 体系建立日 ｜ M1 总工程师 ｜ M1 自动选品（m1-sourcing） ｜ 角色：总工（批次 1 · S2 验收 + S1/S2 收官 + P-011 纪律落档）

- 完成任务：① 落实总控测试纪律更新（P-011/宪法第 12 节）：M1 模块 pytest 统一 `--basetemp=".pytest-tmp-m1"`，已 send_message 同步 S2 子代理，并落档 `context/README.md`（环境事实·测试行）、`risks.md`（R-40 更新）；② **S2 验收通过**（子代理 3e6fd497）——代码抽查：`ad_backfill.py` 错误分层（结构级抛 AdBackfillError / 文件级返回 None 优雅降级 / 类目级单条 skipped 不强杀整批）、幂等 upsert（cache 按 category+period 唯一键、ingests 按 source_file+period+generated_at 唯一键）、时间归一化（Z→+00:00、naive 按 UTC、其他时区转 UTC）、弱样本留痕（可用性由消费端 `_fresh_ad_by_category` 判定）、错误消息不含敏感值；`cli.py` ad-sync（--file 覆盖、缺省读 config.ad_exchange_file、错误 exit 1、统计输出）正确；`config.py` 仅追加 `ad_exchange_file`；**独立串行复跑 sourcing 域 11 文件 → 85 passed**（41 基线+21 S1b+23 S2 精确吻合）；子代理自测全量 417 passed, 1 skipped（skip=M2 ffmpeg 前置既有）；③ 验收过程 P-011 现场实录：首次/二次复跑与 S2 子代理并发共用 `.pytest-tmp-m1` 出现 PermissionError 抖动（84+1 error / 31+54 errors），S2 结束后串行复跑 85 passed 全绿——再次验证「结果以串行复跑为准，独立 basetemp 且避免并发」；④ S1+S2 收官：progress.md 完成度 20%→**25%**，投放转化第 5 维数据闭环里程碑达成（M5 回写接入器+消费端过滤全链路，REC-007/008）。
- 产出文件：S2 产出 `backend/sourcing/ad_backfill.py`、`backend/tests/test_ad_backfill.py`（23 例）、`backend/fixtures/m5-ad-conversion.example.json`、`config.py`（+ad_exchange_file）、`cli.py`（+ad-sync）；`progress.md`（S2 勾选 100%、完成度 25%）、`context/README.md`/`risks.md`（+P-011 纪律）。
- 当前阻塞：无。**S3（真实采集）待派发**——前置：① S1a/S1b/S2 已验收（满足）；② **共享 Chrome 登录态就绪确认（商机中心/抖店罗盘/1688/淘宝 9223 + 有米云 9555）** 需总控/用户确认；若未就绪可先行「launch-browsers/probe-browsers 探测 + 选择器校准」子任务（fixtures 对照，不依赖登录态）。
- 备注：未运行任何 git 命令；未读写其他模块库；全部文件经 write/edit 工具 UTF-8 无 BOM；无明文密钥。

---

### 2025 体系建立日（第 4 轮）｜ M3 总工程师 ｜ M3 自动素材优化 ｜ 角色：总工（文案/主图两路验收通过 · v0.3 派发）

- 完成任务：
  ① **子代理机制异常处置**：4 个 subagent 实例（首轮 829cdbb9/af860c10 + 重派 08a85d20/1cc57a9e，含 2 次 send_message 续跑）全部中断零产出（closing message 空）；改投 **workflow 工具**（全新 agent + 容错）两轮 4 次 agent 调用，虽最终 ok:false，但**产出逐轮累积落盘**——images 子包（5 文件 + 27KB 测试）与 copywriting 子包（cleaner/script/ads/llm + 收尾轮补 __init__.py + 21KB 测试）全部落盘；
  ② **验收文案管线 v0.2 通过**：`python -m pytest tests/test_optimization_copywriting.py -q --basetemp=".pytest-tmp-m3"` → **27 passed**；代码抽查 cleaner.py（清洗链：去标签/营销词/品牌词/广告禁用词/供应链词/功效词 + 15–35 长度策略 + removed 证据）、script.py（LLM 优先 + 规则降级仅拼接 SKU 真实规格 + sku_basis 审计）、ads.py（ad/badge 各 ≥2 套差异化 + 合规必过 + 规则补齐兜底）、llm.py（DeepSeek 结构化 JSON + 轻量 schema 校验 + 重试 + 无 Key 返回 None）——全部符合任务书，无明文密钥；
  ③ **验收主图/详情图管线 v0.4 通过**：`python -m pytest tests/test_optimization_images.py -q --basetemp=".pytest-tmp-m3"` → **38 passed**（planner 差异化 prompts/provider Pillow 占位图/quality_gate phash 判同图+打回重生成/memory 类目记忆）；
  ④ **全量回归**：`python -m pytest tests -q --basetemp=".pytest-tmp-m3"` → **417 passed, 1 skipped**（既有 sourcing/materials/ads 等全部无回归；期间因其他模块并发共用 `.pytest-tmp` 出现 WinError 32 文件锁误报，改用独立 basetemp 后全绿——与 P-011 纪律一致）；
  ⑤ progress.md 更新（文案/主图勾选 100%、完成度 **40%**）。
- 产出文件：`backend/optimization/copywriting/`（5 文件 + 27 用例）、`backend/optimization/images/`（5 文件 + 38 用例）、`backend/tests/test_optimization_copywriting.py`、`test_optimization_images.py`；`progress.md`（两路 100%、完成度 40%）；本日志追加条目。
- 里程碑：**M3 三路输出中两路代码+测试完成**（文案/主图详情图），全量 417 passed 无回归。
- 下一步：派发 **v0.3 视频二创流水线**（C1 ffmpeg 层：FFmpegRunner 抽象（Process/Mock）+ ffprobe 硬规格校验，本机 ffmpeg 未安装故 mock 模式 + skipif 保护；C2 编排层：LLM 拆解/模板三段式/文案叠加/多版本出片编排/落 opt_video_variants），沿用 workflow「进度累积」策略与 `.pytest-tmp-m3` 独立 basetemp。
- 当前阻塞：无。已请总控提交备份（里程碑：两路素材管线验收通过）。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 3 · 子代理中断处置）

- 异常记录与处理（延续批次 3 派发条目）：
  ① **B1（f331c395，视频号采集器）三次中断零产出**（closing message 空/「断点继续」），前两次恢复后仍中断；第 3 次恢复已改为「最小化阅读（只读 3 文件）+ 六步顺序落盘（signer.py → wechat_video.py → fixtures → config → CLI → 测试）」策略，指令已排队；
  ② **B2（03904cb8，淘宝/1688 采集）ran out of room（上下文耗尽）且零产出**——与 M5 执行器先例一致，**弃用 B2，重派 B2'=4b3c6002**（精简任务书：必读 3 文件、最小文件集 6 步落盘、明确 fixtures 离线为主/auto 仅骨架），已后台运行；
  ③ B3（f833480a，榜单图缓存）运行中。
- 当前阻塞：无。待 B1（第 3 次）/B2'/B3 完成通知 → 逐个验收（读产出 + pytest --basetemp=".pytest-tmp-m2"）→ 更新 progress.md/台账 → 批次 3 收官通知总控备份 → 批次 4。

---

### 2025 体系建立日 ｜ P3 子代理 ｜ m4-listing ｜ 角色：子代理

- 完成任务：**P3 上架状态机与证据留痕（listing 状态机 + listing_* 表落地 + 断点续跑）落地完成**：
  - 新建 `backend/listing/` 包 8 文件：`config.py`（LISTING_ 前缀 pydantic-settings：db_url=sqlite:///data/db/m4-listing.db、lease_minutes=45、audit_poll_interval_seconds=60、audit_poll_max_attempts=30、link_verify_timeout_seconds=10）；`models.py`（ListingTask 字段与 DDL 一致，`_at` 时间戳统一 ISO8601 UTC 文本）；`tables.py`（SQLAlchemy 2.0 ORM 严格对齐 database/README.md DDL v0 的 7 表：listing_tasks 唯一 UNIQUE(product_id,stage,generation_version)+status/product 索引、listing_spus、listing_skus 唯一(spu_id,product_sku_code)、listing_upload_assets 唯一(task_id,file_sha256)、listing_op_logs(task_id,created_at 索引)、listing_audit_records 唯一(task_id,audit_id)、listing_quota_states 主键 api）；`db.py`（ListingDatabase，create_all 幂等，默认 data/db/m4-listing.db，本验收用 LISTING_DB_URL 指临时目录未触碰真实库）；`repo.py`（create_task 重复抛 DuplicateTaskError、update_status 带 updated_at+附加字段、claim_task 仅非终态且租约空/过期可领（45min 过期回收）、release_task、append_op_log 证据留痕 payload_digest 脱敏、upsert_quota_state ON CONFLICT(api)）；`state_machine.py`（ListingStateMachine 9 态 ALLOWED_TRANSITIONS + IllegalTransitionError + **R22 断言固化：listed 必须携带 link_url 非空且 verified=True 证据否则抛 ListedLinkVerificationError** + 每次迁移写 listing_op_logs 一条证据 + is_terminal）；`__main__.py`（`python -m listing init-db` 幂等建表并打印清单）。
  - 追加 `backend/tests/conftest.py` 末尾 fixtures（cfg_listing/db_listing/repo_listing/machine_listing，仅末尾追加未改动既有内容）；
  - 新建 `backend/tests/test_listing_tables.py`（14 例：7 表存在、create_all 幂等、4 项唯一约束 set 比较、关键列、2 项索引、重复入队抛 DuplicateTaskError）与 `backend/tests/test_listing_state_machine.py`（17 例：合法链 pending→creating→draft→platform_auditing→listed 含证据、非法迁移 pending→listed/draft→listed、R22 三例断言（无证据/verified=False/空链接）、rejected→retry_candidate→creating、终态判定、迁移证据留痕可回查、payload_digest 不含敏感值、租约领取/过期回收/按 task_id 领取/终态不可领/release、update_status 时间戳）。
- 验收：`cd backend && python -m pytest tests/test_listing_tables.py tests/test_listing_state_machine.py -q --basetemp=".pytest-tmp-m4"` → **31 passed（2.41s）**；`LISTING_DB_URL=sqlite:///<临时目录>/m4-initdb-check-*.db python -m listing init-db` 连跑两次均 EXIT=0 且 7 表清单一致（幂等），临时库已清理，真实 m4-listing.db 未创建。
- 产出文件：`backend/listing/__init__.py`、`backend/listing/config.py`、`backend/listing/models.py`、`backend/listing/tables.py`、`backend/listing/db.py`、`backend/listing/repo.py`、`backend/listing/state_machine.py`、`backend/listing/__main__.py`；`backend/tests/test_listing_tables.py`、`backend/tests/test_listing_state_machine.py`；`backend/tests/conftest.py`（末尾追加 4 个 fixtures）。
- 当前阻塞：无。待总控验收（读产出 + 独立复跑 `--basetemp=".pytest-tmp-m4"`）→ 更新 progress.md/台账 → 推进 P4 拒审处理（依赖 P3）。
- 备注：未运行任何 git 命令；未读写其他模块库（m2-materials.db/m5-ads.db 未动）；未写任何明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM；零网络零真实平台调用。

---

### 2025 体系建立日（第 5 轮）｜ M3 总工程师 ｜ M3 自动素材优化 ｜ 角色：总工（v0.3 视频二创验收通过 · 三路输出收官）

- 完成任务：
  ① **v0.3 视频二创流水线开发**（沿用 workflow「进度累积」策略）：C1 ffmpeg 层成功（video/ffmpeg.py 19.9KB + __init__.py + test_optimization_video_ffmpeg.py 20KB，**39 passed, 1 skipped**——skip 为真实转码用例，本机 ffmpeg 未安装正确跳过，环境就绪后自动启用）；C2 编排层首派中断零产出，重派成功（video/breakdown.py + templates.py + composer.py + test_optimization_video_composer.py，**27 passed**）；
  ② **代码抽查**：ffmpeg.py（detect_ffmpeg env→PATH 双优先、VideoToolError error_code 限定码表、FFmpegProcessRunner 缺失 raise 含安装指引、MockFFmpegRunner 注入、validate_specs 五维硬规格校验、build_transcode_cmd scale+pad+libx264+crf 23+aac 参数全取 config.video）；composer.py（三段式模板规划、字幕/角标 drawtext extra_filters、文案合规预审命中换备选、spec 校验失败不落 uploaded、opt_video_variants 快照完整、run_pipeline 一站式 fixtures 可跑）；
  ③ **全量回归**：`python -m pytest tests -q --basetemp=".pytest-tmp-m3"` → **792 passed, 2 skipped**（59.6s，全模块无回归）；
  ④ progress.md 更新（v0.3 勾选 100%、**M3 三路输出全部完成**、完成度 **60%**）。
- 产出文件：`backend/optimization/video/`（ffmpeg.py/__init__.py/breakdown.py/templates.py/composer.py）、`backend/tests/test_optimization_video_ffmpeg.py`（39 例）、`test_optimization_video_composer.py`（27 例）；`progress.md`（v0.3 100%、完成度 60%）；本日志追加条目。
- 里程碑：**M3 三路输出（文案/主图详情图/视频二创）代码+测试全部验收通过**，全量 792 passed 无回归；M3 素材优化核心产出能力闭环就绪（opt_* 9 表可建、fixtures 离线全链路可跑）。
- 下一步（待总控批准）：**v1.0 集成**——审核闸门（review：规则预审/素材评估/人工抽检）+ A/B 闭环（ab：evaluation 回写/素材评分/模板按类目重训练）+ 上传素材库（upload：UploadService 双轨 api|ui|semi，REC-002，先 fixtures 模拟）→ 端到端测试。
- 当前阻塞：无。**已请总控提交备份（里程碑：M3 三路输出验收通过）**。

---

### 2025 体系建立日（第 5 轮·续）｜ M3 总工程师 ｜ M3 自动素材优化 ｜ 角色：总工（P-011 纪律同步 + test_optimization_images 2 个失败排查加固）

- 任务来源：总控全量回归报告 `test_optimization_images.py` 有 2 个失败（TestMemory::test_policy_injected、TestFullChain::test_plan_generate_gate_memory），要求先看失败详情、区分代码缺陷与测试断言问题，用 `.pytest-tmp-m3` 复跑确认全绿。
- 排查结论：
  ① **当前代码库无法复现**：单文件 38 passed、M3 全范围（-k "optimization or video or copywriting"）168 passed、两次全量（802 / 846 passed）M3 相关测试均全绿——总控报告时点大概率处于并发 pytest 抖动（P-011）或当时代码中间态；
  ② **根因假设（测试断言脆弱性）**：provider 占位图为确定性大色块图，dHash（9x8 相邻亮度比较）对低纹理图判别力弱（M2 双去重验收已记录「纯色/低纹理图距离仅 6」），不同 Pillow 渲染（字体/缩放）下 variant 组合汉明距离可能 ≤8 → full_chain 的 `similar_pairs == []` 断言裕量不足；test_policy_injected 存在 env 依赖窗口（M3_MEMORY_* 环境变量）。
- 修复（均属测试/占位数据加固，非业务逻辑缺陷）：
  ① `provider.py::_draw_placeholder` 叠加 **variant 相关确定性斜纹纹理**（密度 step=10+v*3、斜度 slant=8+v*6），显著拉开不同 variant 的 dHash 距离裕量，保持确定性不引入随机；
  ② `test_policy_injected` 加 monkeypatch.delenv(M3_MEMORY_REJECT_RATE_THRESHOLD/MIN_SAMPLES) 防御 + 双类目正反面断言（负面：通过不触发；正面：仅 1 次拒审 rate=1.0 ≥ 0.9 触发切换）——首版正面断言设计有误（1 通过+1 拒审=拒审率 0.5 < 0.9 不触发），已修正；
  ③ M3 测试 docstring 同步 P-011 纪律（`.pytest-tmp` → `.pytest-tmp-m3`，禁止共用）。
- 验证：`test_optimization_images.py` → **38 passed**；M3 全范围 → **168 passed, 1 skipped**；全量 → **848 passed, 2 skipped**（唯一失败 `test_materials_pipeline.py::test_daily_stats_aggregation` 为 **M2 materials 模块** DuplicateAssetError，与 M3 零依赖，提请总控转达 M2）。
- 产出文件：`backend/optimization/images/provider.py`（+斜纹纹理加固）、`backend/tests/test_optimization_images.py`（test_policy_injected 加固 + docstring 纪律同步）；本日志追加条目。
- 当前阻塞：无。M3 全部测试稳定全绿；待总控确认备份与 v1.0 集成排期。

### 2026-08-28 ｜ 子代理 B3（id f833480a）｜ M2 自动收集素材 ｜ 角色：子代理（批次 3 · 榜单图缓存 BoardImageCache）

- 完成任务：有米云榜单图缓存实现（多源接口化，考古加 kaogujia 预留）+ 本地 http.server fixtures 测试 + 可选 CLI。
- 产出文件：`backend/materials/collectors/board_image_cache.py`（BoardImageCache 全实现）；`backend/tests/test_materials_board_image_cache.py`（25 用例）；`backend/materials/config.py`（仅追加 `board_cache` 子配置）；`backend/materials/collectors/__init__.py`（导出 BoardImageCache）；`backend/materials/__main__.py`（仅追加 `board-cache` 子命令）；`decisions.md` 追加 B3 决策行；`context/README.md` 2.4 同步实现快照。
- 测试结果：新测试 `tests/test_materials_board_image_cache.py` → **25 passed**；既有回归 `test_materials_tables.py + test_materials_repo.py` → **30 passed**（任务书口径）；全 `test_materials_*` 套件 → **179 passed, 1 skipped**（skip 为真实 ffmpeg 保护用例）。全部 `--basetemp=".pytest-tmp-m2"`，零外网零登录态。
- 关键行为：缓存键 `board_cache/{source}/{board_id}/{item_id}.jpg`（组件消毒）；幂等（hit 不重复下载，计数器验证）；批量单条失败隔离（404→NO_MATCH/429→RATE_LIMIT 不影响其他条）；失败分类对齐 downloader.py 码表；本类任何异常不抛出。
- 上报事项：①考古加采集器未开发（M1 REC-006）→ 多源接口化预留 register_source("kaogujia")；②真实有米云下载需登录态环境，本任务以 fixtures 离线模式交付，真实下载仅留接口；③发现既有 `normalize` CLI 潜在 NameError（`Path` 未导入，仅在 ffmpeg 就绪后触发），已登记 pitfall-log P-013，建议总工安排一行修复。
- 当前阻塞：无。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（v0.3 执行层验收通过 · 收官）

- 完成任务：按宪法第 9 节验收执行器子代理 ad45ec7a（A2 重派版）产出——
  ① 读交付说明 REPORT_v0.3_executor.md（文件清单/接口/对接/测试/偏差/纪律齐全）；
  ② **独立复跑**：定向 `pytest tests/test_ads_executor.py -q --basetemp=".pytest-tmp-m5"` → **25 passed**（0.18s）；协同 `pytest tests/test_ads_settings.py tests/test_ads_executor.py -q --basetemp=".pytest-tmp-m5"` → **50 passed**（0.21s，含 run_batch ↔ 真实 settings.py 全链集成用例）；
  ③ 代码抽查 executor.py：ShopAdsSession（login_state 枚举校验、created_at naive 自动补 timezone.utc）、check_login 三态（logged_in/expired/unknown，锚点配置语义正确）、BrowserConnector ABC + Mock + PlaywrightBrowserConnector 骨架（NotImplementedError，零 playwright import/调用）、MockPageOps（脚本化行为字典+history/ops 时间戳+截图写临时文件）、verify_page_signature（多锚点、缺失抛 PageChangedError evidence={page_key,missing,current_url,screenshot_path}、目录自动创建、未配置不阻塞）、ShopAdsExecutor.add_product（{pid} 模板勾选、>batch_size 截断 truncated、item_interval_s 防风控间隔、空列表 NO_MATCH）+ run_batch（_load_settings_form 延迟 import + getattr 兜底、settings 缺失返回 settings_unavailable 不崩、choose_target→fill_roi(系统推荐/覆盖)→bind_materials→submit 全链、错误映射 page_changed/AUTH_REQUIRED/TIMEOUT/NO_MATCH/PLATFORM_REJECT/UNEXPECTED 按 09 码表）——全部符合任务书与决策 D-M5-07；
  ④ **v0.3 集成验证**：executor↔settings 通过 PageOps/ShopAdsUiConfig 契约对接，run_batch 真实 settings 全链跑通，无需改接口。
- 验收结论：**v0.3 执行层全部验收通过**（执行器 + 投放设置 + 集成）。里程碑达成：**托管执行器+投放设置可跑（fixtures 模拟）** ✅——托管两步 ①添加商品 ②投放设置（目标/ROI/素材绑定/提交校验）+ page_changed 检测 + 错误分类映射全链可测。
- 产出文件：`backend/ads/executor.py`、`backend/tests/test_ads_executor.py`（25 例）、`_management/modules/m5-ads/REPORT_v0.3_executor.md`、`progress.md`（v0.3 全部勾选、完成度 **45%**）；本日志追加条目。
- 当前阻塞：无。**已请总控提交备份（里程碑：v0.3 执行层验收通过）**；批准后推进 v0.4 监控层（监控回读 + 止损规则引擎，可拆 2 子代理）。
- 备注：未运行任何 git 命令；未读写其他模块库；未写明文密钥；ads 包现有测试 77 例（tables 19 + repo 14 + settings 25 + executor 25），全量回归请总控统一执行（建议独立 basetemp）。

---

### 2025 体系建立日（第 5 轮）｜ M4 总工程师 ｜ M4 自动上架（m4-listing） ｜ 角色：总工（P3 验收通过 · P4 派发）

- 完成任务：
  ① **P3 验收通过**（子代理 b57d2057，一次性完成）——独立复跑 `python -m pytest tests/test_listing_tables.py tests/test_listing_state_machine.py -q --basetemp=".pytest-tmp-m4"` → **31 passed**（2.33s，与子代理自测 2.41s 一致）；代码抽查 `backend/listing/state_machine.py`：9 态 STATUSES + ALLOWED_TRANSITIONS 严格对齐 context/README.md 第二节（pending→creating→draft→platform_auditing→listed/rejected→retry_candidate/manual/failed）、`IllegalTransitionError`、**`ListedLinkVerificationError`（R22 断言固化：listed 必须携带 link_url 非空且 verified=True 证据，否则抛错）**、rejected 落 reject_reason_code、每次迁移写 listing_op_logs 一条证据（api=state_machine/direction=transition/evidence_json 含 from/to/evidence）、TERMINAL_STATUSES=listed/manual/failed；抽查 repo.py（DuplicateTaskError 幂等防重复入队、claim_task 租约 45min 过期回收断点续跑、append_op_log payload_digest 脱敏、upsert_quota_state ON CONFLICT）；
  ② **P4 拒审处理已派发**（子代理 11d4d391，全内联任务书：backend/listing/platform_rejection.py——REJECT_CATEGORIES 七分类关键词表（title/category/qualification/image/price/content_compliance/other）、RejectFixCandidate/RejectionAnalysis/RejectionResult 模型、修复候选生成规则（title→改标题/image→重传主图·详情图/price→改价 均 gate_required=True；qualification→补资质 False；category/content_compliance/other→manual）、RejectionHandler.handle（迁移 retry_candidate|manual + 写 listing_audit_records）、requalify 二次门禁复用 ListingGate（只读 import backend.services.listing_gate）；测试 ≥12 例），运行中；
  ③ progress.md P3 勾选 100%、完成度 **60%**、P4 行更新；decisions 无需新增（沿用 D10/D11/D12）。
- 产出文件：`backend/listing/`（8 文件，子代理产出已验收）、`backend/tests/test_listing_tables.py`（14 例）、`test_listing_state_machine.py`（17 例）、`conftest.py`（末尾追加 4 fixtures）；`progress.md`（P3 100%、完成度 60%）；本日志追加条目。
- 当前阻塞：无。待 P4 完成通知 → 验收（读产出 + `pytest --basetemp=".pytest-tmp-m4"`）→ 更新 progress.md/台账 → 推进 P5 Playwright 兜底降级 + 集成（依赖 P1–P3 已满足）。
- 备注：未运行任何 git 命令；未读写其他模块库（m4-listing.db 真实库未创建）；未写任何明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM；零网络零真实平台调用。

---

### 2025 体系建立日 ｜ S3a 子代理 ｜ M1 自动选品（m1-sourcing） ｜ 角色：子代理

- 完成任务（S3 第一阶段：浏览器探测 + 选择器校准，fixtures 对照，不依赖登录态）：
  ① **环境探测（只读）**：Python 3.13.14 / Playwright **1.61.0** 已装；Chrome 可执行文件=标准路径 `C:/Program Files/Google/Chrome/Application/chrome.exe`（`SOURCING_CHROME_PATH` 未设置，PATH 无 chrome）；CDP 端口 socket 实测 **9223 ✓ / 9555 ✓ / 9222 ✓**；
  ② **launch-browsers** 幂等执行（9223/9555 均已存在→跳过，未启动新浏览器）；**probe-browsers** 5 来源全 `CDP ✓`：共享 9223 已打开商机中心 home 与抖店罗盘 rank-product 页、有米云 9555 已打开商品榜 URL → **浏览器已启动且持有登录态页面**（真实采集仍待登录态确认后批准，本任务未运行任何真实采集）；
  ③ **selector-log.md v1.0**（新建）：5 来源逐一对照 config/采集器/fixtures——关键发现：**5 来源 config.selectors 全为空 → 生效选择器=代码 DEFAULT_SELECTORS（配置化结构就位未落地）**；有米云 URL 日期硬编码待动态化；抖店飙升榜 URL 模板与 fixtures 均缺；有米云/抖店动态列定位分支被默认 columns 短路；商机中心 price/sales/category 恒空与 fixtures 口径有差异；alibaba/taobao 宽泛选择器需真实页面收敛；每来源含「待实测项」清单；
  ④ **test_page_changed.py**（新增 6 例）：detect_page_changed 5 场景全通过（任一可见→False/全不可见→True/空列表→False/locator 异常→True/is_visible TimeoutError→True）+ 短路补充用例；
  ⑤ **环境事实更新**：`context/README.md` 追加 S3a 探测快照表 + 测试基线更新为 91 passed。
- 产出文件：`_management/modules/m1-sourcing/context/selector-log.md`（新建）、`backend/tests/test_page_changed.py`（新增 6 例）、`_management/modules/m1-sourcing/context/README.md`（环境事实表追加）、本日志追加条目。
- 测试结果：`python -m pytest tests/test_pricing.py ... tests/test_page_changed.py -q --basetemp=".pytest-tmp-m1"` → **91 passed**（既有 85 + 新增 6，6.61s）。
- 当前阻塞：无。待总工验收；真实采集（S3 第二阶段）需登录态确认后另行批准。
- 备注：未运行任何 git 命令；未修改任何既有测试与既有采集器代码（selector-log.md 中 A1~A6 校准动作仅登记建议，未改代码）；未安装任何软件；未探测/读取登录态敏感信息（probe 仅读页面 URL，未读 cookie/localStorage/凭据）；全部文件经 write/edit 工具 UTF-8 无 BOM。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（v0.4 监控层派发）

- 完成任务：总控批准 v0.4 监控层排期（2 子代理：监控回读 + 止损规则引擎，总控已提交 v0.12 备份）；总工架构设计确定文件边界（避免并行冲突）——① `backend/ads/report.py`（监控回读：normalize_diagnosis/normalize_status/parse_amount_fen（str 按元→分、数值按分直取）/parse_snapshot_row/SnapshotCollector.run_once（幂等 upsert + 单行错误隔离）+ collect_missing（断点补快照，已存在跳过）+ next_run_hint（不做真实定时器，调度归后续集成）；config.py 仅该子代理可尾部追加）；② `backend/ads/stop_loss.py`（止损规则引擎：normalize_diagnosis 同口径独立实现 + rule_s1~s6 纯函数 + check_budget_triple 预算三重硬约束 + kill_switch_enabled 一键全停 + StopLossEngine.evaluate；**只读既有 config 字段 stoploss_impression/min_balance_fen/roi_floor_ratio/max_active_campaigns/budget_*/kill_switch，禁止改 config.py**）；并行派发两个自包含子代理任务书（背景/必读/目标/输出路径/验收标准/宪法要点/P-001+P-011 独立 basetemp `.pytest-tmp-m5`/禁 git/禁明文密钥/UTF-8/禁改既有文件清单）。
- 派发子代理：**① 监控回读=0702b611**（backend/ads/report.py + test_ads_report.py 15~25 例：诊断/状态枚举化、金额解析、快照入库幂等、单行失败隔离、断点补快照 skipped/补齐/since 过滤、next_run_hint UTC）；**② 止损规则引擎=9d0c8921**（backend/ads/stop_loss.py + test_ads_stop_loss.py 18~28 例：S1~S8 全规则命中+边界、预算三重硬约束、kill_switch、Engine.evaluate 集成、诊断枚举化）。
- 产出文件：`progress.md`（v0.4 开发中标注、两子代理已派发）；本日志追加条目。
- 当前阻塞：无。待两子代理完成通知 → 总工分别验收（读产出 + 跑 pytest --basetemp=".pytest-tmp-m5"）→ v0.4 集成（report↔stop_loss↔repo 联调）→ 更新 progress.md/台账 → 通知总控备份（里程碑：监控回读+止损引擎可跑）→ 推进 v0.5 回流层。
- 备注：未运行任何 git 命令；未读写其他模块库；未写明文密钥。

---

### 2026-08-28 | B1 子代理 | M2 自动收集素材（m2-materials） | 角色：子代理

- 完成任务：视频号采集器（自研签名+直链，R-M2-03/R-M2-05）——fixtures 离线模式全链路 + auto 骨架 + signer 接口化，零浏览器零登录态验收通过。
- 产出文件：
  - `backend/materials/collectors/signer.py`（SignatureProvider ABC：sign(params,url)->{"headers","query"}；MockSignatureProvider 可配置固定值；RealSignatureProvider 未校准前 raise NotImplementedError 不留假算法）
  - `backend/materials/collectors/wechat_video.py`（WechatVideoCollector：login_state 无浏览器返回 False 不抛 / list_hot_videos fixtures+auto 双模式 / resolve_direct_url signer 注入；错误分类 AUTH_REQUIRED/PLATFORM_REJECT/NO_MATCH/TIMEOUT 对齐 downloader.py 码表；输出字段 source_platform="视频号"）
  - `backend/fixtures/materials/wechat_video_hot.json`（新建 fixtures 目录，6 条样本含作者/标题/热度/视频 id/direct_url）
  - `backend/materials/config.py`（只追加 wechat_video 子配置：enabled/cdp_port 默认 9223/profile_dir=shared/fixtures_mode 默认 True/boards/selectors）
  - `backend/materials/__main__.py`（只追加 wechat-collect 子命令；cli() 入口统一 stdout/stderr UTF-8，Windows 管道 GBK 乱码实测修复）
  - `backend/materials/collectors/__init__.py`（追加 wechat 导出，未动既有）
  - `backend/tests/test_materials_wechat_video.py`（28 用例：fixtures 解析/热度排序/signer 注入/Real 未实现→PLATFORM_REJECT/错误分类各分支/login_state 不抛/auto fake page 注入全分支）
  - `_management/modules/m2-materials/decisions.md`（B1 决策行追加）
- 测试结果：`python -m pytest tests/test_materials_wechat_video.py tests/test_materials_tables.py tests/test_materials_repo.py tests/test_materials_tiktok_wrapper.py -q --basetemp=".pytest-tmp-m2"` → **92 passed**（28 新增 + 30 tables/repo 回归 + 34 tiktok 兼容）。
- CLI 验收：`python -m materials wechat-collect --mode fixtures --limit 5` → returncode 0，合法 UTF-8 JSON，5 条全 source_platform="视频号"，热度降序，零浏览器连接。
- 当前阻塞：无。auto 模式真实浏览器解析/真实签名待「共享浏览器登录态确认 + 抓包校准」（校准只改 config.selectors 与 signer.py）。
- 备注：未运行任何 git 命令；未安装任何软件；未连接真实浏览器（auto 模式仅骨架+配置，未验证）；未改动 backend/sourcing/*（仅只读参考）；未写明文密钥/真实签名算法；全部文件 write/edit 工具 UTF-8 无 BOM；pytest 独立 basetemp .pytest-tmp-m2。

---

### 2025 体系建立日 ｜ 子代理-C1（视频二创 ffmpeg 层） ｜ M3 自动素材优化 ｜ 角色：子代理

- 完成任务：实现 M3 视频二创流水线 ffmpeg 层（backend/optimization/video/）——① `detect_ffmpeg()`：env M3_FFMPEG_PATH/M3_FFPROBE_PATH 优先（兼容 FFMPEG_PATH/FFPROBE_PATH）→ PATH，两者齐备返回版本字符串，缺任一/版本查询失败均返回 None，绝不抛异常；② `VideoToolError`：error_code 限定 WorkflowJob 码表子集 TIMEOUT/UNEXPECTED/NO_MATCH（非法码归一 UNEXPECTED，带 evidence）；③ `FFmpegRunner` 抽象基类 + `FFmpegProcessRunner`（subprocess.run 超时配置化；ffprobe JSON 探测→{width,height,duration,size_bytes,format}，无视频流→NO_MATCH；转码 argv[0]="ffmpeg" 占位绑定真实二进制；二进制缺失即 raise VideoToolError 含安装指引 winget/ffmpeg.org 官网/brew/apt/M3_FFMPEG_PATH，不静默）+ `MockFFmpegRunner`（probe 返回注入预设，transcode 记录 (cmd,timeout) 供断言）；④ `validate_specs`：五维硬规格校验（分辨率 ≥720×1280／9:16 容差 ±0.01／mov·mp4 token 命中／≤500M bytes 换算／5~300s），返回 {'passed','failures':[{field,reason,value}]} 逐项可解释（对齐 05/06 硬规格与 P-007）；⑤ `build_transcode_cmd`：scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2 + -t 时长上限 + -c:v libx264 -crf + -c:a aac + extra_filters 拼接进 -vf，参数全部取 config.video（spec 覆盖生效，禁止硬编码散落）。
- 产出文件：`backend/optimization/video/__init__.py`（包 docstring + 7 项重导出）、`backend/optimization/video/ffmpeg.py`、`backend/tests/test_optimization_video_ffmpeg.py`（39 用例）。
- 测试：`python -m pytest tests/test_optimization_video_ffmpeg.py -q --basetemp=".pytest-tmp-m3"` → **39 passed, 1 skipped**（P-011 独立 basetemp；skip = 真实转码冒烟，本机 ffmpeg/ffprobe 未安装已探测确认，skipif(not detect_ffmpeg()) 保护，环境就绪后自动启用）；同模块回归 `tests/test_optimization_copywriting.py tests/test_optimization_images.py` → **65 passed** 无破坏。
- 当前阻塞：无。ffmpeg 层按「先实现 + Mock 测试，环境就绪后自动切换」交付；C2 编排层按共用接口契约调用（detect_ffmpeg/VideoToolError/FFmpegRunner/FFmpegProcessRunner/MockFFmpegRunner/validate_specs/build_transcode_cmd 签名严格一致）。
- 备注：未运行任何 git 命令；未安装任何软件（含 ffmpeg）；未读写其他模块库；未写明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 3 · B1/B3 验收 + P-013 修复）

- 完成任务：
  ① **验收子代理 B3**（id f833480a，榜单图缓存）：独立复跑 `python -m pytest tests/test_materials_board_image_cache.py -q --basetemp=".pytest-tmp-m2"` → **25 passed**；抽查 board_image_cache.py——缓存键 `board_cache/{source}/{board_id}/{item_id}.jpg`（组件消毒防穿越）、幂等 hit 不重复下载（计数器验证）、批量失败隔离（404→NO_MATCH/429→RATE_LIMIT 不影响其他条）、失败分类复用 downloader 码表、任何异常不抛出；多源白名单默认 ["youmi"] + register_source("kaogujia") 预留。**验收通过**；
  ② **修复 P-013**（B3 发现：`__main__.py` 第 156 行 normalize 用 `Path` 但模块顶部未导入，被 ffmpeg 缺失提前退出掩盖）——已在 `__main__.py` 顶部 import 区补 `from pathlib import Path`，验证 `python -c "import materials.__main__"` → IMPORT_OK、`normalize --input x.mp4` 仍清晰报 ffmpeg 缺失（exit 1）不回归；
  ③ **验收子代理 B1**（id f331c395，视频号采集器，第 3 次恢复后完成）：独立复跑 `python -m pytest tests/test_materials_wechat_video.py -q --basetemp=".pytest-tmp-m2"` → **28 passed**；CLI `python -m materials wechat-collect --mode fixtures --limit 5` → **EXIT_CODE=0**、合法 UTF-8 JSON、source_platform 全="视频号"；抽查 signer.py——SignatureProvider ABC + Mock（注入签名生效）+ Real（未校准 raise NotImplementedError 不留假算法，R-M2-03）；wechat_video.py——login_state 无浏览器不抛、错误分类对齐码表、fixtures/auto 双模式。**验收通过**（auto 模式待登录态+抓包校准）。
- 产出文件：`backend/materials/__main__.py`（+Path import，P-013 修复）；`_management/modules/m2-materials/progress.md`（B1/B3 勾选 100%、B2 行更新为 B2'）；本日志追加条目。
- 当前阻塞：无。批次 3 剩余：B2'（4b3c6002）运行中；待其完成通知后验收 → 批次 3 收官通知总控备份 → 批次 4（标签化+合规预审、M3/M5 数据联动联调）。

---

### 2026-08-28 22:52 ｜ P4 子代理 ｜ m4-listing ｜ 角色：子代理

- 完成任务：**P4 平台拒审处理（platform_rejection）落地完成**：
  - 新建 `backend/listing/platform_rejection.py`：`REJECT_CATEGORIES` 七分类 + `REJECT_KEYWORDS` 关键词表（title/category/qualification/image/price/content_compliance 按优先级顺序子串匹配，均未命中 → other；如「标题类目错误」→title、「品牌授权过期」→qualification、「品牌夸大宣传」→content_compliance）；`RejectFixCandidate`（action/param/gate_required）、`RejectionAnalysis`（category/reject_reason/fix_candidates/auto_fixable/resubmit_required）、`RejectionResult`（task_id/category/action/analysis）pydantic 模型；`_build_fix_candidates` 修复候选生成（title→改标题、image→按 reason 细分主图/详情图/都给、price→改价 均 gate_required=True，qualification→补资质 gate_required=False，category/content_compliance/other→无候选）；`RejectionHandler`（构造注入 repo/state_machine，gate 可选注入默认自建）——`analyze`（分类+候选+auto_fixable/resubmit_required 语义：qualification 有候选走重提但 auto_fixable=False）、`handle`（有候选→transition retry_candidate、无候选→transition manual，迁移证据带 reject_reason_code，并直接走本模块库 session INSERT listing_audit_records：task_id/audit_id 派生自 platform_spu_id（回退 task_id）/reject_reason/reject_category/fix_candidate(JSON)/resubmit_required(1/0)/evidence(JSON)）、`requalify`（二次门禁：仅 retry_candidate 任务可重提，复用 `services.listing_gate.ListingGate` 全量校验 passed 才 True，未通过返回 False 且不迁移任务状态，评估留痕 listing_op_logs 一条）。
  - 新建 `backend/tests/test_listing_rejection.py`（36 例）：分类映射参数化 7 分类 + 优先级 4 断言；修复候选生成参数化 10 分支（含 image 主图/详情图细分与都给）+ gate_required 4 分支；analyze 语义 3 分支；handle 全流程（title/qualification→retry_candidate、content_compliance→manual）+ 审核记录落库断言（reject_category/fix_candidate/resubmit_required）+ audit_id 派生 + transition op_log 证据含 reject_reason_code；requalify 二次门禁（合规候选→True、标题超长候选→False 且任务状态不变、rejected/manual 任务→False）。
- 验收：`cd backend && python -m pytest tests/test_listing_rejection.py -q --basetemp=".pytest-tmp-m4"` → **36 passed（1.73s）**；连带 P3 文件 `test_listing_tables.py + test_listing_state_machine.py + test_listing_rejection.py` → **67 passed（3.71s）** 无回归。
- 产出文件：`backend/listing/platform_rejection.py`、`backend/tests/test_listing_rejection.py`。
- 当前阻塞：无。待总控验收（读产出 + 独立复跑 `--basetemp=".pytest-tmp-m4"`）→ 更新 progress.md/台账 → 推进 P5 Playwright 兜底降级 + 集成（依赖 P1–P4 已满足）。
- 备注：未运行任何 git 命令；未改动 backend/sourcing|materials|optimization|ads|foundation|adapters|services 与 backend/listing/ 下任何既有文件（P3 产物只读引用）；`backend/tests/conftest.py` 未改动（fixtures cfg_listing/db_listing/repo_listing/machine_listing 已存在，直接复用）；零建库零网络零真实平台调用（requalify 图片由 Pillow 在 tmp_path 生成）；未写任何明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM。

---

### 2025 体系建立日（第 6 轮）｜ M4 总工程师 ｜ M4 自动上架（m4-listing） ｜ 角色：总工（P4 验收通过 · P5 派发）

- 完成任务：
  ① **P4 验收通过**（子代理 11d4d391，一次性完成）——独立复跑 `python -m pytest tests/test_listing_rejection.py -q --basetemp=".pytest-tmp-m4"` → **36 passed**（1.73s，与子代理自测一致）；代码抽查 `backend/listing/platform_rejection.py`：七分类关键词表（title/category/qualification/image/price/content_compliance 优先级子串匹配→other）、`RejectFixCandidate/RejectionAnalysis/RejectionResult` 模型、`_build_fix_candidates`（title→改标题/image→主图·详情图细分/price→改价 均 gate_required=True；qualification→补资质 False；category/content_compliance/other→无候选）、`RejectionHandler`（构造注入，handle 迁移 retry_candidate|manual + 写 listing_audit_records，requalify 二次门禁复用 ListingGate）——D10 决策落地（自动修复候选需二次门禁、不可修复转 manual）；
  ② **P5 Playwright 兜底降级 + 集成已派发**（子代理 d0e6e336，全内联任务书：backend/listing/ui_fallback.py——UiFallbackConfig（LISTING_UI_ 前缀：batch_size=50 串行/item_interval_s 防风控/signatures 锚点配置化）+ PageOps Protocol + MockPageOps + verify_page_signature（page_changed 检测留证据 PageChangedError）+ FallbackRunner（失败结构化返回不抛队列层，UI 失败不阻塞 OpenAPI 队列）；backend/listing/pipeline.py——ListingPipeline 端到端编排（gate 校验失败不入队 → 幂等防重复 → create_spu/create_skus/upload_image → submit_audit → query_audit_status → get_product_link + link_verifier → transition listed（R22 证据）| 驳回 → rejection.handle；requalify_and_resubmit；异常留痕断点语义）；零真实浏览器零真实平台（Mock 注入），测试 ≥18 例），运行中；
  ③ progress.md P4 勾选 100%、完成度 **75%**、P5 行更新。
- 产出文件：`backend/listing/platform_rejection.py`、`backend/tests/test_listing_rejection.py`（子代理产出，已验收）；`progress.md`（P4 100%、完成度 75%）；本日志追加条目。
- 当前阻塞：无。待 P5 完成通知 → 验收（读产出 + `pytest --basetemp=".pytest-tmp-m4"`）→ 更新 progress.md/台账 → P6 M5 衔接验收（销售中商品候选池只读视图 + 错峰参数 + data-audit 登记，依赖 P5 + M5 就绪）。
- 备注：未运行任何 git 命令；未读写其他模块库；未写任何明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM；零网络零真实平台调用。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 3 · B2' 验收 + 批次 3 收官）

- 完成任务：按宪法第 9 节验收子代理 B2'（id 4b3c6002，淘宝/1688 采集器）——
  ① 独立复跑 `python -m pytest tests/test_materials_taobao_1688.py -q --basetemp=".pytest-tmp-m2"` → **34 passed**；CLI `python -m materials taobao-refs --url https://item.taobao.com/item.htm?id=710000001 --mode fixtures --limit 3` → **EXIT_CODE=0**（合法 JSON）；验收命令（URL 不在 fixtures）→ NO_MATCH 结构化失败 exit 0（正确语义）；
  ② 抽查 taobao_refs.py——`_RefsCollectorBase.collect` 结构化返回、**降级 R-M2-08**（视频缺失/TIMEOUT → images 照常 + videos=[] + note）、**page_changed P-003**（选择器未命中 → HTML 快照落盘 data_dir/evidence/page_changed/ + PLATFORM_REJECT + missing_selectors 证据）、错误分类 align downloader 码表、URL 经 redact_url 脱敏（P-004）；alibaba_1688.py 同构复用（source_platform="1688"）。**验收通过**。
- **批次 3 收官**：B1（视频号采集器）+ B2'（淘宝/1688）+ B3（榜单图缓存）全部验收通过；progress.md 三任务 100%、完成度 45%→**60%**、里程碑 8 项达成；本日志追加条目。
- 环境待确认（提请总控/运维）：ffmpeg 未安装（mock，就绪自动切真实）；TikTokDownloader 未安装（就绪装 4.1.x）；**共享浏览器登录态**（三采集器 auto 模式待登录态+选择器/签名抓包校准）。
- 当前阻塞：无。**批次 3 收官，请总控提交备份**；批准后推进批次 4（标签化+合规预审、M3/M5 数据联动联调）→ 集成验收 v1.0。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 4 派发）

- 完成任务：总控批准批次 4（v0.16 已备份推送）：①标签化+合规预审 ②M3/M5 数据联动 ③完成后集成验收 v1.0；勘察确认：sourcing/compliance.py 词库（BRAND/PROHIBITED/EFFICACY/SUPPLY_CHAIN + sanitize_title + ComplianceEngine）可复用、materials/repo.py 已有 create_asset/claim_fingerprint/update_evaluation/mark_uploaded/record_compliance_check 五个方法可直接对接。
- 并行派发三个自包含子代理任务书（背景/必读/目标/输出路径/验收标准/宪法要点/宪法第 12 节 `.pytest-tmp-m2`/禁 git/禁明文密钥/UTF-8/环境事实/并行解耦说明）：
  - **B4-1=16e973e3**（backend/materials/tagger.py：generate_tags + MaterialCompliance 复用 sourcing.compliance 词库（不复制词表）+ evaluate_and_record 证据留痕（repo.record_compliance_check→compliance_status 同步）+ mark_platform_rejected 拒审下架（R-M2-20，repo 缺方法则追加 mark_disabled）+ config 追加 tagger 子配置 + test_materials_tagger.py）
  - **B4-2=684608a5**（backend/materials/integration.py：EvaluationFeedbackService.receive_evaluation（枚举校验/NO_MATCH/幂等审计）+ UploadProvider 抽象（Mock 全实现/ShopMaterialUploadProvider 骨架 TODO）+ MaterialUploadService（幂等 mark_uploaded+asset_uploads）+ config 追加 upload 子配置 + context/data-requests.md 跨模块需求登记（宪法第 5 节）+ test_materials_integration.py）
  - **B4-3=a052cdfd**（backend/materials/pipeline.py：MaterialPipeline.run_source 编排 采集→下载→去重→标准化→标签→合规→入库（组件可注入/延迟 import getattr 兜底，缺失降级 skipped 不崩）+ daily_stats 日采集量统计 + 可选 CLI pipeline/daily-stats + test_materials_pipeline.py）
- 产出文件：`_management/modules/m2-materials/progress.md`（批次 4 三任务「已派发」+子代理 id+集成验收待办行）；本日志追加条目。
- 当前阻塞：无。待批次 4 完成通知 → 逐个验收（读产出 + pytest --basetemp=".pytest-tmp-m2"）→ 更新 progress.md/台账 → **集成验收 v1.0（素材库可入库/去重/预览、日采集量可观测）** → 通知总控。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（v0.4 监控层验收通过 · 收官）

- 完成任务：按宪法第 9 节验收两个 v0.4 子代理产出——
  ① **监控回读（0702b611）验收**：独立复跑 `pytest tests/test_ads_report.py -q --basetemp=".pytest-tmp-m5"` → **24 passed**；读交付说明 REPORT_v0.4_report.md；代码抽查 report.py：normalize_diagnosis/normalize_status（中文→英文枚举、N项正则）、parse_amount_fen（str 元→分×100、数值分直取、千分位/非法容忍）、parse_snapshot_row（recorded_at 缺省 UTC、带偏移转 UTC、raw_json 副本、campaign_id 缺失抛 ValueError）、SnapshotCollector.run_once（repo.upsert_snapshot 幂等 + 每行独立 savepoint 失败隔离）、collect_missing（断点补快照 skipped/补齐/since 过滤/批内去重/rows 可选参数）、next_run_hint（UTC、interval 缺省读 config.report_interval_s、不做真实定时器）——全部符合任务书；
  ② **止损规则引擎（9d0c8921）验收**：独立复跑 `pytest tests/test_ads_stop_loss.py -q --basetemp=".pytest-tmp-m5"` → **28 passed**；代码抽查 stop_loss.py：rule_s1~s6 纯函数（S1 曝光阈值暂停+标签/S2 诊断记录 priority_retry/S3 ROI<目标×80% 连续 2 周期（花费=0→ROI=0 命中、=止损线不命中）/S4 补贴记录/S5 余额 halt_new/S6 活跃上限 stop_new）、check_budget_triple（S7 单笔/日/计划同时生效、0=不限、多超限取首个）、kill_switch_enabled（S8 app_config 覆盖、未识别字符串视为关防误触发）、StopLossEngine.evaluate（S1→S7 顺序稳定、kill_switch 短路只返回 S8、halt_all=kill_switch|S5|S6、budget 三形状兼容 v0.3 validate_submit）——全部符合任务书；
  ③ **集成口径统一（D-M5-08）**：交叉断言发现两模块 normalize_diagnosis 英文输入行为不一致（report「英文→unknown」vs stop_loss 幂等）→ 集成修整 report.py 加英文枚举幂等 + 测试断言同步（新增 test_normalize_diagnosis_english_idempotent，report 25 passed）；记入 decisions.md D-M5-08；
  ④ **v0.4 集成验证**：全 ads 套件 `pytest tests/test_ads_report.py tests/test_ads_stop_loss.py tests/test_ads_settings.py tests/test_ads_executor.py tests/test_ads_repo.py tests/test_ads_tables.py -q --basetemp=".pytest-tmp-m5"` → **130 passed**（2.15s）。
- 验收结论：**v0.4 监控层全部验收通过**。里程碑达成：**监控回读+止损规则引擎可跑** ✅——快照幂等入库+断点补快照+S1~S8 规则+预算三重硬约束+余额检测+一键全停全链可测。
- 产出文件：`backend/ads/report.py`、`backend/ads/stop_loss.py`、`backend/tests/test_ads_report.py`（25 例）、`test_ads_stop_loss.py`（28 例）、`_management/modules/m5-ads/REPORT_v0.4_report.md`、`REPORT_v0.4_stop_loss.md`、`decisions.md`（+D-M5-08）、`progress.md`（v0.4 全部勾选、完成度 **60%**）；本日志追加条目。
- 当前阻塞：无。**已请总控提交备份（里程碑：v0.4 监控层验收通过）**；批准后推进 v0.5 回流层（数据回写：选品「投放转化」维度 + 素材评估回流 + review_reason，可拆 1 子代理）。
- 备注：未运行任何 git 命令；未读写其他模块库；未写明文密钥；ads 包测试现 **130 例**（tables 19 + repo 14 + settings 25 + executor 25 + report 25 + stop_loss 28），全量回归请总控统一执行。

### 2026-08-28 23:04 ｜ P5 子代理 ｜ m4-listing ｜ 角色：子代理

- 完成任务：M4 自动上架模块 **Playwright 兜底降级通道 + 上架流水线编排 + 端到端模拟**（零真实浏览器/零真实平台调用，全部抽象接口 + Mock 注入）——
  ① **`backend/listing/ui_fallback.py`（新建）**：`UiFallbackConfig`（env_prefix `LISTING_UI_`，batch_size=50/item_interval_s=5.0/page_timeout_ms=15000/screenshot_dir/signatures）；`PageOps` Protocol（goto/click/fill/screenshot/current_url/has_selector）；`MockPageOps`（script 字典驱动行为 + ops 历史含时间戳 + 截图写盘自动建目录，独立实现不 import ads 包）；`PageChangedError`（evidence 含 page_key/missing/current_url/screenshot_path，P-003 改版留证）；`verify_page_signature`（锚点全过放行/缺失截图抛错）；`FallbackRunner`（verify→goto→操作序列 select_category/set_purchase_limit/fill_custom_param，成功 {ok:True,evidence} / 失败结构化 {ok:False,error_code:"page_changed"|"NO_MATCH"|"TIMEOUT"|"UNEXPECTED"} 不抛到队列层，连续失败 ≥2 → UNEXPECTED + 人工接管建议 R10/R11，run_batch ≤batch_size/批串行 + item_interval_s 防风控间隔 P-006）；
  ② **`backend/listing/pipeline.py`（新建）**：`ListingPipeline`（构造注入 gate/adapter/repo/state_machine/rejection/link_verifier 默认恒 True）；`submit`（门禁失败不入队 stage="gate" → 幂等复用 existing → 入队 pending→creating → SPU/SKU/主图×N+详情图 → draft → submit_audit → platform_auditing → 查审通过 + get_product_link + link_verifier → listed[R22 证据 link_url 非空+verified=True] / 驳回 → rejected → rejection.handle → retry_candidate|manual；全程异常 → 结构化失败留最近合法状态，断点续跑不伪造状态；op_log 证据留痕 payload_digest 脱敏）；`requalify_and_resubmit`（仅 retry_candidate 可重提，P4 二次门禁通过后复用原任务 retry_candidate→creating 继续全链）；
  ③ **测试（新建）**：`backend/tests/test_listing_fallback.py`（12 例：MockPageOps 历史/签名校验通过/缺失抛 PageChangedError 含 evidence+截图写盘/成功路径/改版结构化失败/NO_MATCH/TIMEOUT 映射/连续失败 UNEXPECTED 人工接管/batch_size 截断/item_interval 时间戳间隔/fill 参数落值/未知操作）、`backend/tests/test_listing_pipeline.py`（11 例：happy path 全链状态+product_link+link_verified_at+op_log 齐全/gate 失败不入队/驳回 retry_candidate/驳回 manual/幂等/R22 负面 link_verifier=False 停留 platform_auditing/requalify 全链（限流窗口重置）/requalify 非 retry_candidate/requalify 二次门禁不过/RATE_LIMIT 失败状态停 creating/op_log 脱敏摘要）；
  ④ 验收：`cd backend && python -m pytest tests/test_listing_fallback.py tests/test_listing_pipeline.py -q --basetemp=".pytest-tmp-m4"` → **23 passed**（fallback 12 + pipeline 11）；复用 conftest fixtures（cfg_listing/db_listing/repo_listing/machine_listing）+ tmp_path SQLite 零建库，P1 adapter 用 WechatOpenApiConfig(mode="mock")。
- 产出文件：`backend/listing/ui_fallback.py`、`backend/listing/pipeline.py`、`backend/tests/test_listing_fallback.py`（12 例）、`backend/tests/test_listing_pipeline.py`（11 例）；本日志追加条目。
- 当前阻塞：无。请总控统一执行 M4 全量回归（P1~P5 全部用例）。
- 备注：未运行任何 git 命令；未使用 web_search；未写明文密钥；未 import playwright / 无真实浏览器与网络调用；未改动 backend/sourcing|materials|optimization|ads|foundation|adapters|services 与 backend/listing/ 下既有文件及 tests/conftest.py；仅新建 4 个文件。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（v0.5 回流层派发）

- 完成任务：总控批准 v0.5 回流层排期（数据回写 1 子代理，总控已提交 v0.17 备份）；**契约勘察与会签准备**——通读 M1 消费端 `backend/sourcing/ad_backfill.py`（C-2 权威：schema_version=1/period{start,end:YYYY-MM-DD}/generated_at ISO8601/data{category:{roi>0,sales_amount 分int,sample_count}}，load_exchange 校验逻辑、弱样本留痕消费端过滤、导入幂等）、M1 C-2 契约草案（m1 context/README：sales_amount 分 int、generated_at 新鲜度>7 天、M5 按与 products.category 完全一致的类目名聚合、载体 `_management/data-exchange/m5-ad-conversion.json`）、M2 消费端 `backend/materials/integration.py`（EvaluationFeedbackService.receive_evaluation(asset_id,evaluation,evidence,source_agent="M5")，EVALUATION_VALUES=exploring/efficient/potential，幂等审计）——确认 M5 侧产出结构可与 M1 ad_backfill 直接对接（**避免双写冲突：M5 只产 data-exchange JSON 载体，绝不写 M1/M2 库**）；架构设计 feedback.py 五能力（aggregate_by_category 类目聚合含 spend=0 类目跳过/弱样本仍输出；build_exchange_file C-2 结构校验；write_exchange_file UTF-8 幂等写；build_material_evaluation_file M2 对齐 evidence；build_review_reason_file；load_category_map 映射加载）；派发自包含子代理任务书（背景/必读 8 文件/目标/验收含 **C-2 契约交叉验证（M1 load_exchange 读 M5 产出必须通过）**/宪法要点/禁改 sourcing·materials·ads 既有文件/`.pytest-tmp-m5`）。
- 派发子代理：**数据回写=cc1f830a**（backend/ads/feedback.py + test_ads_feedback.py 18~28 例 + REPORT_v0.5_feedback.md 含 data-audit 登记建议文本）。
- 产出文件：`progress.md`（v0.5 开发中标注、子代理已派发、v1.0 集成验收待办行）；本日志追加条目。
- 当前阻塞：无。待子代理完成通知 → 总工验收（读产出 + 定向 pytest + **C-2 契约交叉验证**）→ data-audit 登记（M5-OUT-01/02/03 提供记录）→ v1.0 集成验收 → 通知总控备份。
- 备注：未运行任何 git 命令；未读写其他模块库（本次仅勘察 M1/M2 源码与契约文档）；未写明文密钥。

---

### 2025 体系建立日（第 7 轮）｜ M4 总工程师 ｜ M4 自动上架（m4-listing） ｜ 角色：总工（P5 验收通过 · P6 派发）

- 完成任务：
  ① **P5 验收通过**（子代理 d0e6e336，一次性完成）——独立复跑 `python -m pytest tests/test_listing_fallback.py tests/test_listing_pipeline.py -q --basetemp=".pytest-tmp-m4"` → **23 passed**（7.41s，与子代理自测 7.44s 一致）；代码抽查 `backend/listing/pipeline.py`：ListingPipeline 构造注入（gate/adapter/repo/state_machine/rejection/link_verifier 默认恒 True）、submit 全链（门禁失败不入队 stage="gate" → 幂等复用 → pending→creating→draft→platform_auditing→listed（R22 证据 link_url+verified=True）| 驳回→rejection.handle→retry_candidate|manual）、全程异常结构化失败留最近合法状态（断点续跑不伪造状态）、requalify_and_resubmit（仅 retry_candidate 可重提）——07 文档「失败不阻塞队列」与 R22 铁律在编排层落地；ui_fallback.py 抽查（PageOps Protocol + MockPageOps + verify_page_signature page_changed 留证 + FallbackRunner 失败结构化返回不抛队列层 + run_batch ≤50 串行防风控）；
  ② **P6 M5 衔接已派发**（子代理 62253f5d，全内联任务书：backend/listing/candidate_pool.py——CandidatePoolConfig（LISTING_ 前缀：candidate_batch_max=50、peak_avoid_window 错峰互斥时段）+ CandidatePool.get_sale_candidates（只读查询 status=listed + link_verified_at 非空 + product_link 非空，仅销售中商品，关联 spus 标题/类目 + skus 价格区间聚合，≤batch_max 截断）+ in_peak_avoid_window（上架与 M5 托管错峰）；测试 ≥8 例；并在 _management/logs/data-audit.md 末尾登记 M4→M5 数据提供（宪法第 5 节）），运行中；
  ③ progress.md P5 勾选 100%、完成度 **90%**、P6 行更新。
- 产出文件：`backend/listing/ui_fallback.py`、`backend/listing/pipeline.py`、`backend/tests/test_listing_fallback.py`（12 例）、`test_listing_pipeline.py`（11 例）（子代理产出，已验收）；`progress.md`（P5 100%、完成度 90%）；本日志追加条目。
- 当前阻塞：无。待 P6 完成通知 → 验收（读产出 + `pytest --basetemp=".pytest-tmp-m4"`）→ **M4 模块级验收收官**（progress.md 100%、更新 brief/context 实现快照、台账）→ 通知总控备份（里程碑：M4 自动上架全链路可模拟跑通）并请总控统一执行 M4 全量回归。
- 备注：未运行任何 git 命令；未读写其他模块库；未写任何明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM；零网络零真实平台调用。

---

### 2025 体系建立日 ｜ 子代理-C2（视频二创编排层） ｜ M3 自动素材优化 ｜ 角色：子代理

- 完成任务：实现 M3 视频二创流水线编排层（backend/optimization/video/，对齐 06 文档第一节「LLM 拆解→模板化二创→文案叠加→ffmpeg 批量出片→字幕水印规范→预审」与 C1 ffmpeg 层接口契约，ffmpeg.py 只读不改）：
  ① **breakdown.py（LLM 拆解）**——输入 product_id/类目/sku_spec_json → 输出卖点镜头 selling_shots + 口播要点 voiceover_points 结构化列表；复用 copywriting/llm.py DeepSeekClient 结构化 JSON（BREAKDOWN_SCHEMA，失败重试 config.llm.max_retries 次）；无 Key/失败降级规则：仅按 sku_spec_json 真实字段切分要点（复用 copywriting.script._spec_facts 句式），source="rule_fallback"；任何要点产出后必过 compliance.check_text，命中剔除留 meta 证据（llm_dropped/dropped），全命中或空 → 通用安全兜底；
  ② **templates.py（模板参数规划）**——默认值取模板参数配置（对齐 tables.OptTemplate 列默认/context README 1.2：opening_seconds=3、subtitle_style={bottom,36,stroke}、badge_position=top-right、bgm_loudness=-16.0、cut_count=3、params_version=1）+ CATEGORY_ADJUSTMENTS 类目微调（数据驱动）+ overrides 覆盖；plan_segments 输出三段式结构（片头=商品+卖点卡点、中段=原片/混剪片段序列（cut_count 均分）、片尾=行动引导 2s）；template_id 按类目确定性生成（中文保留）；
  ③ **composer.py（编排器）**——输入（asset dict + CopywriteDraft 列表 + TemplatePlan）→ 每 variant_no（≥2 版，v1 模板原值、vN 片头+1≤5/混剪片段-1≥1/BGM-0.5 节奏差异化，v2+ 文案差异化优先投放文案 ad、v1 优先口播稿 script）生成 ffmpeg 命令（build_transcode_cmd + extra_filters：字幕 drawtext（subtitle_style 位置/字号/描边、24 字截断）与角标 drawtext（badge_position、box 底衬））；字幕内容取文案候选并过 check_text 预审，命中该版作废改用备选（rejected 留证据），全部命中 → 跳过（composer.skipped 不落库）；经 MockFFmpegRunner 出片（detect_ffmpeg() 就绪自动切 FFmpegProcessRunner，fixtures 离线可跑）；出片后 validate_specs 五维硬规格校验（失败记录 failures，upload_status 不落 uploaded）；落 opt_video_variants（product_id/source_asset_id/variant_no/template_id/copywrite_ids/template_params_snapshot（含 params+segments）/file_path/spec_check_json（含 probe 证据）/spec_ok/compliance_json/evaluation=exploration）；VideoVariantRepo 同骨架 CopywriteRepo 幂等模式；run_pipeline(asset, product, variants=2) 一站式入口（拆解→模板→口播稿+投放文案+角标候选→多版出片落库，db 缺省内存库不碰真实 m3-optimization.db）。
- 产出文件：`backend/optimization/video/breakdown.py`、`backend/optimization/video/templates.py`、`backend/optimization/video/composer.py`（新增）；`backend/optimization/video/__init__.py`（追加 C2 重导出，C1 内容未破坏）；`backend/tests/test_optimization_video_composer.py`（27 用例）。
- 测试：`python -m pytest tests/test_optimization_video_composer.py -q --basetemp=".pytest-tmp-m3"` → **27 passed**（P-011 独立 basetemp）；同模块回归 `tests/test_optimization_copywriting.py tests/test_optimization_images.py tests/test_optimization_video_ffmpeg.py tests/test_optimization_video_composer.py` → **131 passed, 1 skipped**（skip = C1 真实转码冒烟，本机 ffmpeg 未安装，环境就绪自动启用）无回归。
- 当前阻塞：无。编排层按「Mock 出片 + 环境就绪自动切 FFmpegProcessRunner」交付；待总工验收后可衔接 M3 后续（审核闸门/上传素材库/A-B 评估回写）。
- 备注：未运行任何 git 命令；未安装任何软件（含 ffmpeg）；未改动 backend/sourcing/ 与公共骨架（config/db/tables/models/repo/compliance）及 copywriting/images 子包；未读写其他模块库；未写明文密钥（密钥仅环境变量名 DEEPSEEK_API_KEY）；全部文件经 write/edit 工具 UTF-8 无 BOM；零网络零真实平台调用。

---

### 2025 体系建立日 ｜ M2 总工程师 ｜ M2 自动收集素材 ｜ 角色：总工（批次 4 · B4-1/B4-2 验收）

- 完成任务：按宪法第 9 节验收批次 4 前两任务——
  ① **B4-2（id 684608a5，M3/M5 数据联动）验收通过**：独立复跑 `python -m pytest tests/test_materials_integration.py -q --basetemp=".pytest-tmp-m2"` → **17 passed**；抽查 integration.py——EvaluationFeedbackService.receive_evaluation（非法枚举→PLATFORM_REJECT 不落库/素材不存在→NO_MATCH/合法→审计+更新当前值，服务层不抛出）、UploadProvider 抽象（Mock 全实现/ShopMaterialUploadProvider 骨架 NotImplementedError 不留假凭据）、MaterialUploadService（已上传幂等 already_uploaded/失败分类结构化返回）；**已在 data-audit.md 追加 DA-004**（M2 四类数据联动登记：从 M5 收 evaluation 回写、从 M3 收上传回填、向 M3/M5 提供素材——宪法第 5 节）；context/data-requests.md 由子代理新建（四类含字段口径/用途/频率）；
  ② **B4-1（id 16e973e3，标签化+合规预审）验收通过**：独立复跑 `python -m pytest tests/test_materials_tagger.py -q --basetemp=".pytest-tmp-m2"` → **31 passed**；抽查 tagger.py——词库全部 import 自 sourcing.compliance（BRAND/PROHIBITED/EFFICACY/SUPPLY_CHAIN，测试 is 断言同一 list 对象，materials 内零词表副本）、check_material 四类检查（供应链 6 词参数化全 reject，多类同中取最严重：禁售>品牌>供应链>功效）、evaluate_and_record 证据留痕（asset_compliance_checks 落库 + compliance_status 同步）、mark_platform_rejected（R-M2-20：upload_status=disabled + asset_uploads 台账，幂等）；repo.py 仅追加 mark_disabled。
- 产出文件：`_management/logs/data-audit.md`（+DA-004）；`_management/modules/m2-materials/progress.md`（B4-1/B4-2 勾选 100%）；本日志追加条目。
- 当前阻塞：无。批次 4 剩余：B4-3（a052cdfd，pipeline 编排）运行中；待其完成通知后验收 → **集成验收 v1.0（素材库可入库/去重/预览、日采集量可观测）** → 通知总控。

---

### 2026-08-28 23:13 ｜ P6 子代理 ｜ m4-listing ｜ 角色：子代理

- 完成任务：**M5 衔接——销售中商品候选池只读视图 + 错峰参数 + data-audit 登记落地完成**：
  ① 新建 `backend/listing/candidate_pool.py`：`CandidatePoolConfig`（pydantic-settings，env_prefix `LISTING_`：`candidate_batch_max=50`（≤50 错峰批量，P-006）、`peak_avoid_window={"start":"10:00","end":"12:00"}` 上架批次与 M5 托管提交互斥时段）；`CandidatePool`（构造注入 repo）——`get_sale_candidates(limit=None)` **只读查询** listing_tasks 中 `status=="listed"` 且 `link_verified_at` 非空 且 `product_link` 非空（含空串排除）的任务（仅销售中商品，07 文档六节；草稿/审核中/驳回/人工/待重提一律不出现），关联 listing_spus 取 title/category_id（无 SPU 置 None）、关联 listing_skus 聚合 price_min_cents/price_max_cents（分，无 SKU 置 None），返回 {product_id/task_id/title/category_id/product_link/link_verified_at/price_min_cents/price_max_cents}，按 link_verified_at 升序（先上架先出），limit 生效且不超过 candidate_batch_max（超出截断并附 evidence 提示 → self.last_evidence）；`in_peak_avoid_window(now=None)` 左闭右开 [start,end)，跨天窗口（start>end，如 22:00→02:00）按环形处理，比较粒度 HH:MM；配置缺键/非法格式构造时 fail-fast ValueError；纯只读幂等；
  ② 新建 `backend/tests/test_listing_candidate_pool.py`（10 例）：仅返回 listed 且链接验证过（含异常数据直接 UPDATE 模拟：listed 但 link_verified_at/product_link 清空、空串链接均不出现）/非 listed 五状态（draft/platform_auditing/rejected/manual/retry_candidate）不出现/字段完整性/价格聚合（多 SKU min/max、无 SKU None、无 SPU title/category None）/link_verified_at 升序/limit 与 candidate_batch_max 截断（含 last_evidence 断言）/空库空列表幂等/默认窗口边界（start 含 end 不含、分钟粒度）/跨天窗口环形/配置错误 fail-fast；造数走 P3 state_machine 合法迁移链到 listed（R22 证据 link_url+verified=True）；
  ③ `_management/logs/data-audit.md` 末尾追加 **DA-005｜M4 → M5 数据提供登记**（提供内容=销售中商品候选池 status=listed+链接已验证、字段口径、提供方式=CandidatePool.get_sale_candidates 只读查询、频率=按需/批次错峰、负责人=M4 总工、校验=仅已上架商品（07 文档六节），对齐 context/README.md 5.3 节）。
- 验收：`cd backend && python -m pytest tests/test_listing_candidate_pool.py -q --basetemp=".pytest-tmp-m4"` → **10 passed（1.51s）**（首跑 10 失败为测试造数缺 task_id 与 candidate_pool.py `import time as _time` 误用函数作 isinstance 类型参数两处笔误，已修复重跑全绿）。
- 产出文件：`backend/listing/candidate_pool.py`、`backend/tests/test_listing_candidate_pool.py`（10 例）；`_management/logs/data-audit.md`（+DA-005）；本日志追加条目。
- 当前阻塞：无。待总工验收（读产出 + 独立复跑 `--basetemp=".pytest-tmp-m4"`）→ M4 模块级验收收官。
- 备注：未运行任何 git 命令；未使用 web_search；未写明文密钥；零建库零网络零真实平台调用（全部 tmp_path SQLite + Mock）；未改动 backend/sourcing|materials|optimization|ads|foundation|adapters|services 与 backend/listing/ 下任何既有文件及 backend/tests/conftest.py（fixtures cfg_listing/db_listing/repo_listing/machine_listing 直接复用）；仅新建 2 个代码文件 + 登记 2 处日志；全部文件经 write/edit 工具 UTF-8 无 BOM。

---

### 2025 体系建立日（第 8 轮）｜ M4 总工程师 ｜ M4 自动上架（m4-listing） ｜ 角色：总工（P6 验收通过 · M4 模块级收官）

- 完成任务：
  ① **P6 验收通过**（子代理 62253f5d，一次性完成）——独立复跑 `python -m pytest tests/test_listing_candidate_pool.py -q --basetemp=".pytest-tmp-m4"` → **10 passed**（1.50s）；代码抽查 `backend/listing/candidate_pool.py`：CandidatePoolConfig（LISTING_ 前缀、candidate_batch_max 1~50 校验、peak_avoid_window 错峰互斥时段）、get_sale_candidates（只读查询 status=listed + link_verified_at 非空 + product_link 非空，关联 spus 标题/类目 + skus 价格区间聚合，link_verified_at 升序，limit ≤ batch_max 截断附 evidence）、in_peak_avoid_window（左闭右开/跨天环形/配置 fail-fast）、纯只读幂等；data-audit.md **DA-005（M4→M5 候选池数据提供登记）**已确认落盘；
  ② **M4 模块级收官**：P1~P6 全部验收通过（模块单测 **131 passed**：6+25+31+36+23+10，`--basetemp=".pytest-tmp-m4"`）；progress.md 完成度 **100%**、验收门全部勾选、迭代 v1.3；brief.md（+实现快照 v1.3）、context/README.md（+实现快照与代码位置映射）更新。
- 产出文件：`backend/listing/candidate_pool.py`、`backend/tests/test_listing_candidate_pool.py`（10 例）、`_management/logs/data-audit.md`（+DA-005）（子代理产出，已验收）；`progress.md`（100%、验收门勾选、v1.3）、`brief.md`（+实现快照）、`context/README.md`（+实现快照）；本日志追加条目。
- **里程碑达成：M4 自动上架全链路可模拟跑通**（门禁→SPU/SKU/图→审核→真实链接验证 R22→已上架|拒审处理→M5 候选池），mock 模式零网络零真实平台，全程不提交真实商品（REC-004）。
- 当前阻塞：无。**已请总控提交备份（M4 模块级收官里程碑）**；请总控统一执行 M4 全量回归（test_listing_* 8 文件 + test_wechat_openapi + test_listing_gate 共 131 例）；M4 侧剩余仅外部条件：官方 OpenAPI 契约核对（T1~T7，web 额度恢复后销项，live 模式依赖 T1/T2）+ 企业主体/类目资质开通（用户确认后切 live）。
- 备注：未运行任何 git 命令；未读写其他模块库（m4-listing.db 真实库未创建）；未写任何明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM；零网络零真实平台调用。

---

### 2025 体系建立日 ｜ M5 总工程师 ｜ M5 自动小店投放（商品托管） ｜ 角色：总工（v0.5 回流层验收通过 · v1.0 集成验收收官）

- 完成任务：按宪法第 9 节验收数据回写子代理 cc1f830a（v0.5 回流层）产出——
  ① 读交付说明 REPORT_v0.5_feedback.md（文件清单/接口/测试/C-2 交叉验证/M5-OUT-01~03 结构/偏差/data-audit 登记建议文本齐全）；
  ② **独立复跑**：定向 `pytest tests/test_ads_feedback.py -q --basetemp=".pytest-tmp-m5"` → **28 passed**（0.55s）；
  ③ **C-2 契约交叉验证（总工独立执行）**：`aggregate_by_category`（多商品同类目聚合 roi=3.33/sales=500000 分/sample=9）→ `build_exchange_file`（+08:00 时间转 UTC）→ `write_exchange_file` → M1 消费端 `sourcing.ad_backfill.load_exchange` 校验通过（schema_version=1、category 保留、roi>0）——**C-2 会签成立：M1 可直接消费，M5 未写任何对方库**；
  ④ 代码抽查 feedback.py：aggregate_by_category（spend=0 类目跳过入 skipped、未知 product_id 跳过、弱样本仍输出）、build_exchange_file（period YYYY-MM-DD 校验、roi≤0/非 int 抛 ValueError、naive 补 UTC）、write_exchange_file（UTF-8 ensure_ascii=False 无 BOM、父目录自动创建、幂等覆盖）、build_material_evaluation_file（evaluation 枚举镜像 M2 EVALUATION_VALUES、evidence 四字段 source_agent=M5）、build_review_reason_file（product_id/review_reason 非空、failed_at 默认 UTC）、load_category_map（dict/list 双形状、坏文件返回 {}）——全部符合任务书；
  ⑤ **v1.0 集成验收**：全 ads 套件 7 文件 `pytest tests/test_ads_feedback.py tests/test_ads_repo.py tests/test_ads_tables.py tests/test_ads_settings.py tests/test_ads_executor.py tests/test_ads_stop_loss.py tests/test_ads_report.py -q --basetemp=".pytest-tmp-m5"` → **158 passed**（2.35s，零回归）；跨模块契约会签：C-2（M1 ad_backfill 消费端 ✅）、M2 evaluation 回流（receive_evaluation 对齐 ✅，DA-004 对端）、DA-005 M4 候选池（M4 侧已提供，M5 消费接入归运行期编排）；全自动闭环 fixtures 全链路可测（候选→托管两步→监控回读→止损→数据回写）。
  ⑥ **data-audit 登记**：`_management/logs/data-audit.md` 追加 **DA-006｜M5 数据回写提供登记**（M5-OUT-01 C-2 投放转化 / M5-OUT-02 素材评估回流 / M5-OUT-03 review_reason，含 C-2 会签校验结果）。
- 验收结论：**v0.5 回流层验收通过 + v1.0 集成验收完成**。里程碑达成：**数据回写可产可会签** ✅（C-2 契约交叉验证通过）→ **v1.0 集成验收** ✅（ads 158 测试 + 跨模块契约对齐）。
- 产出文件：`backend/ads/feedback.py`、`backend/tests/test_ads_feedback.py`（28 例）、`_management/modules/m5-ads/REPORT_v0.5_feedback.md`、`_management/logs/data-audit.md`（+DA-006）、`progress.md`（v0.5+v1.0 勾选、完成度 **75%**）；本日志追加条目。
- 当前阻塞：无。**已请总控提交备份（里程碑：M5 v1.0 集成验收完成）**；剩余仅真实实投验证 v1.1（依赖账号/余额/登录态/素材/实机探针就绪——11 文档第一节前置条件，总控待用户确认清单；真实 Playwright 适配器/真实回读/实机选择器校准均为此前置的后续）。
- 备注：未运行任何 git 命令；未读写其他模块库（仅勘察 M1/M2 源码契约 + 只读 load_exchange 校验）；未写明文密钥；ads 包测试现 **158 例**（tables 19 + repo 14 + settings 25 + executor 25 + report 25 + stop_loss 28 + feedback 28），全量回归请总控统一执行。
