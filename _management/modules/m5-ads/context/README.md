# M5 自动小店投放（商品托管） · 上下文库（context）

> 模块的持久记忆，跨会话不丢失。任何代理重启后先读本目录。
> 必须维护：数据字典、API 契约、环境事实、跨模块数据契约。禁止写明文密钥。
> 版本：v0.1 ｜ 撰写人：M5 总工 ｜ 日期：2025 体系建立日
> 权威依据：`08-自动小店投放模块设计（商品托管）.md`（字段与流程以投放后台 2026-08 实测界面为基准）、`09`、`10`、`11`。

## 一、数据字典（核心实体）

> 通用口径（遵循总控 data-audit DA-001 裁决）：**金额一律以「分」（int）存储**，回读自后台（元）时 ×100；展示时 ÷100 转元。
> **时间一律 UTC（ISO8601 带时区）存储**（如 `2025-01-01T08:00:00+08:00` 或 `...Z`），展示层转 UTC+8；时间戳字段名后缀 `_at`；主键一律自增 INTEGER。

### 1. ad_campaigns（AdCampaign：一个托管计划 = 1 商品 + 1 组投放设置）

| 字段 | 类型 | 单位/枚举 | 说明 |
|---|---|---|---|
| id | INTEGER PK | — | 自增主键 |
| product_id | INTEGER | 与 products.id 对齐（M1/M4 口径） | 托管商品（仅销售中） |
| ad_mode | TEXT | `goods_trust` | 商品托管（本项目唯一模式） |
| target_type | TEXT | `成交ROI` / `净成交ROI` / `商品成交` | 投放设置目标三选一；默认成交ROI，秒退单多时切净成交ROI |
| target_roi | REAL | 如 2.00 | 默认取系统推荐值；可配置覆盖 |
| material_ids_json | TEXT(JSON) | 素材库 ID 列表 | 含视频号形象绑定；优选顺序 高效>潜力>探索期 |
| status | TEXT | `待托管` / `托管中` / `已暂停` / `不可投放` / `已结束` | 对齐后台投放管理列表 |
| diagnosis | TEXT | `优秀` / `良好` / `1项待优化` / `N项待优化` | 智能诊断回读值 |
| batch_id | INTEGER | 关联 ad_runs.batch_id | 批量托管批次 |
| created_at / updated_at | TEXT | UTC(展示转UTC+8) | — |

### 2. ad_runs（AdRun：单次执行，复用 WorkflowJob 机制）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| campaign_id | INTEGER FK | → ad_campaigns.id |
| attempt | INTEGER | 第几次尝试 |
| status | TEXT | running/success/failed/blocked |
| error_code | TEXT | 复用 09 码表：VERIFICATION_REQUIRED / AUTH_REQUIRED / RATE_LIMIT / TIMEOUT / NO_MATCH / PLATFORM_REJECT / UNEXPECTED（另加 page_changed 扩展码） |
| evidence_json | TEXT(JSON) | 操作留痕：截图路径/选择器命中/耗时/页面 URL（脱敏） |
| lease_owner | TEXT | 执行进程标识 |
| lease_expires_at | TEXT | 租约 45min 过期回收 |
| batch_id | INTEGER | 批次号（≤50/批） |

### 3. ad_report_snapshots（AdReportSnapshot：定时回读投放列表）

| 字段 | 类型 | 单位/枚举 | 说明 |
|---|---|---|---|
| id | INTEGER PK | — | 自增 |
| campaign_id | INTEGER FK | → ad_campaigns.id | — |
| recorded_at | TEXT | UTC(展示转UTC+8) | 回读时间，(campaign_id, recorded_at) 唯一约束幂等 |
| impressions | INTEGER | 次 | 商品曝光数 |
| spend | INTEGER | 分 | 花费 |
| gmv | INTEGER | 分 | 成交金额 |
| platform_subsidy | INTEGER | 分 | 平台补贴（补贴后 ROI 单独统计） |
| diagnosis | TEXT | 优秀/良好/N项待优化 | 智能诊断 |
| status | TEXT | 投放中/暂停/不可投放 | 投放列表状态 |

### 4. ad_account_states（AdAccountState：投放账户状态，仿 SourcePlatformState）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| balance | INTEGER | 可用余额（分） |
| status | TEXT | active / risk_control / waiting_login / waiting_verification / paused | 账户状态（默认 active；waiting_* 为人工接管断点续跑） |
| throttle_level | INTEGER | 0~4 节流级（间隔 ×1/2/4/8/16） |
| paused_until | TEXT | 暂停截止（人工接管后断点续跑） |
| pause_reason | TEXT | 暂停原因 |

### 5. ad_materials（AdMaterial：素材库视频，与 M2/M3 assets 打通）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| material_id | TEXT | 小店素材库 ID（后台素材库） |
| asset_id | INTEGER | → M2/M3 `assets.id`（跨模块口径，经 data-audit 核对） |
| file_path | TEXT | 本地路径（环境变量根目录下） |
| duration | REAL | 秒（5~300s） |
| resolution | TEXT | 如 1080x1920（9:16，≥720×1280） |
| evaluation | TEXT | `探索期` / `高效` / `潜力`（投放效果回流更新） |
| upload_status | TEXT | 上传中/已上传/审核中/审核通过/审核不通过/源文件损坏 |
| platform_material_id | TEXT | 平台侧素材 ID |

## 二、后台界面事实锚点（08 文档第一节，自动化输入/输出锚点）

| 页面 | 关键事实（自动化依赖的锚点） |
|---|---|
| 托管首页 | 已托管/托管中/待托管计数、**可用余额**、日预算（当前可不限）、「无转化不扣费」标识 |
| 添加托管商品 | **两步**：① 添加商品（**上限 50/批**、自动过滤投放中商品、仅展示销售中商品、分桶：机会品/热搜品/优质商品/潜力商品）→ ② 投放设置 |
| 投放设置 | 目标三选一：成交ROI / 净成交ROI（秒退不扣费）/ 商品成交；目标 ROI（如 2.00，可取系统推荐）；**素材与视频号形象**绑定 |
| 投放管理列表 | 全部/投放中/暂停投放/不可投放；列：商品名+ID+分桶标签、目标出价（如成交ROI 2.40）、**智能诊断**（优秀/良好/1项待优化）、商品曝光数、花费、成交金额、**平台补贴**、操作（查看详情/添加素材） |
| 素材库 | 9:16 视频 ≥720×1280 / MOV·MP4 / ≤500M / 5~300s；评估标签 探索期/高效/潜力；审核不通过或源文件损坏的素材投放时不支持选择 |

## 三、止损规则表（08 第五节 + 10 第一节，规则引擎实现依据）

| # | 规则（条件） | 动作 | 触发频率 | 备注 |
|---|---|---|---|---|
| S1 | 花费>0 且 成交=0 且 曝光≥阈值（默认 500） | 暂停该托管 + 打标签「换素材/调ROI」 | 每回读周期 | 阈值配置化 |
| S2 | 诊断=1项待优化 | 记录优化项到 evidence，标记优先重投 | 每回读周期 | 优先换素材重投 |
| S3 | 成交ROI < 目标×80%，持续 2 个快照周期 | 降素材优先级/建议调 ROI | 跨 2 周期 | 连续判定，防抖动 |
| S4 | 平台补贴>0 | 计入报表，补贴后 ROI 单独统计 | 每回读周期 | 不进止损判定 |
| S5 | 余额 < 阈值（默认 ¥100） | 暂停新托管 + 告警（人工充值点） | 投放前/每回读周期 | 余额检测四层防线之一 |
| S6 | 投放中商品数 > 上限（如 40/51） | 停止新增，等自然淘汰 | 每次入队前 | 与 ≤50/批并行约束 |
| S7 | 单笔/日总/计划总预算任一超限 | 立即停止相关投放动作 | 每次花钱动作前 | 预算三重硬约束同时生效 |
| S8 | 一键全停（后台总开关） | 秒级终止所有投放/托管/采集动作 | 随时 | 最高优先级 |

## 四、外部契约

### 4.1 平台（小店投放后台 · 无官方 API）

- 方式：Playwright + 共享 Chrome（CDP），**纯 UI 操作**；不走腾讯广告 Marketing API。
- 页面/URL、选择器：一律配置化（app_config 或环境变量），**不进代码硬编码**；页面结构特征变化 → page_changed 检测（特征元素缺失）留截图证据 → 人工接管。
- 失败分类：VERIFICATION_REQUIRED（验证码，单任务暂停 60min）/ AUTH_REQUIRED（登录失效，人工登录断点续跑）/ RATE_LIMIT（180s 退避）/ TIMEOUT（60s 退避）/ NO_MATCH（页面无目标元素）/ PLATFORM_REJECT（平台驳回，记录原因转人工）。

### 4.2 队列与调度（复用 M0 基座 WorkflowJob）

- stage：`shop_ads_run`（托管投放执行）、`shop_ads_report`（投放报表回读）。
- 幂等：(product_id, stage, generation_version) 唯一约束防重复入队。
- 租约：lease_owner + lease_expires_at（45min），进程重启 recover_after_process_restart 回收。
- 后继：上架完成（M4）才可入托管队列；shop_ads_run 完成才 enqueue shop_ads_report。

### 4.3 调度器节奏

- 节流：throttle 0~4 级（×1/2/4/8/16），失败次数逐级提升。
- 熔断：连续失败 ≥2 → risk_control 暂停平台，探针板恢复。
- 回读：默认 10~30min/次，间隔配置化；与执行动作错峰。

## 五、跨模块数据契约

| 方向 | 数据 | 字段口径 | 载体/方式 | 状态 |
|---|---|---|---|---|
| M1 → M5 | 托管候选池 | product_id、选品总分、状态=已上架/销售中、类目、价格带 | 经总控 data-audit 协调（本模块 context/data-requests.md 登记需求） | 待申请 |
| M4/M1 → M5 | 商品销售中状态 | products.status 枚举（销售中） | 只读共享表/接口（M0 协调） | 待确认 |
| M2/M3 → M5 | 素材库素材 + 评估标签 | asset_id、file_path、duration、resolution、evaluation（探索期/高效/潜力） | assets 表（M2 属主）只读 + data-audit | 待申请 |
| M5 → M1 | 投放转化维度（选品打分第 5 维） | 按类目聚合 ROI/成交额（分）、权重可配；无数据时权重=0 不生效 | ad_report_snapshots 汇总，经总控转达 | 待协商 |
| M5 → M3 | 素材评估标签回流 | 投放实际效果更新 evaluation（高效/潜力/探索期）→ 素材优化模板参数按类目重训练 | data-audit 记录提供方/校验结果 | 待协商 |
| M5 → 商品主表 | 托管失败/不可投放原因 | 资质/素材/价格带 → products.review_reason | 经总控协调写入（商品表属 M1） | 待协商 |
| M5 → 前端 | 托管看板 | 对齐后台列表列：商品/目标出价/诊断/曝光/花费/成交/补贴/操作 | 前端 API | 待开发 |

> 铁律：M5 不直接读其他模块库；所有跨模块数据经 `_management/logs/data-audit.md` 登记、总控转达。

## 六、环境事实

| 项 | 事实 |
|---|---|
| 本模块库文件 | `backend/data/db/m5-ads.db`（SQLite，不入 git；生产切 PostgreSQL 时迁移脚本在 database/） |
| 共享浏览器 | Playwright + 共享 Chrome，CDP 端口（环境变量，如 9222/9223 体系），复用已有标签页不重复开页 |
| Python | 3.12；依赖锁 requirements；Playwright 版本固定 |
| 测试命令 | 本模块测试一律 `python -m pytest <用例> -q --basetemp=".pytest-tmp-m5"`（P-001 默认临时目录 WinError 5 + P-011 多代理并行共享 `.pytest-tmp` 互相清理；本模块用独立 basetemp `.pytest-tmp-m5`，全量回归由总控统一执行） |
| ffmpeg | 素材规格校验依赖（时长/分辨率/大小），M3 产出规格锁定 |
| 环境变量（仅列名，不含值） | `M5_ADS_CDP_PORT`、`M5_ADS_PROFILE_DIR`（浏览器资料目录）、`M5_ADS_MIN_BALANCE`（余额阈值分）、`M5_ADS_BATCH_SIZE`（默认50）、`M5_ADS_BATCH_INTERVAL`（批间隔秒）、`M5_ADS_REPORT_INTERVAL`（回读秒）、`M5_ADS_STOPLOSS_IMPRESSION`（曝光阈值）、`M5_ADS_TARGET_ROI_OVERRIDE`（ROI覆盖，可空）、`M5_ADS_DAILY_BUDGET` / `M5_ADS_PLAN_BUDGET` / `M5_ADS_SINGLE_BUDGET`（预算三重约束，分） |
| 敏感信息 | 任何 API Key/Token/Cookie/密码**只走环境变量**，绝不在 md/代码/日志写明文；日志 `_redact_text` 脱敏 |
