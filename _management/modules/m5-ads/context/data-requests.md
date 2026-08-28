# M5 自动小店投放（商品托管） · 跨模块数据需求登记（data-requests）

> 依据宪法第 5 节：本模块需要其他模块数据时在此登记，并同步登记 `_management/logs/data-audit.md`，由总控转达对应模块总工。
> 每条：需求 ID ｜ 需要什么 ｜ 字段 ｜ 用途 ｜ 频率 ｜ 状态。
> 版本：v0.1 ｜ 撰写人：M5 总工 ｜ 日期：2025 体系建立日

---

## 一、需求清单（M5 向其他模块申请）

| ID | 需要方 | 提供方 | 内容 | 关键字段 | 用途 | 频率 | 状态 |
|---|---|---|---|---|---|---|---|
| M5-REQ-01 | M5 投放 | **M1 选品** | 托管候选池：选品打分 TopN 且已上架 | `product_id`/`score`/`category`/`price_band`/`listing_state`(=销售中) | 自动进入托管队列（≤50/批）的输入 | 每次入队前拉取 | 待 M1 提供（契约草案见 M1 context C-2 反向） |
| M5-REQ-02 | M5 投放 | **M4/M1 上架** | 商品「销售中」状态确认（官方 API 口径） | `product_id`/`sale_status`/`category` | 候选过滤：仅销售中商品可托管 | 入队前校验 | 待总控牵头确认口径 |
| M5-REQ-03 | M5 投放 | **M2/M3 素材** | 素材库视频 + 评估标签 | `asset_id`/`file_path`/`duration`/`resolution`/`evaluation`(探索期/高效/潜力)/`audit_status` | 素材优选绑定（高效>潜力>探索期）；无素材跳过标「待素材」 | 每次执行前拉取 | 待 M2/M3 提供（assets 表属 M2） |
| M5-REQ-04 | M5 投放 | **M0 基座** | 共享 Chrome CDP 端口/登录态就绪状态 | `cdp_port`/`login_state` | Playwright 执行前置条件 | 启动时探测 | 已具备（probe-browsers 体系） |
| M5-REQ-05 | M5 投放 | **M0 基座** | `app_config` 预算/阈值/权重运行时配置 | `key`/`value`(JSON) | 预算三重硬约束/止损阈值/ROI 覆盖配置化 | 每次动作前读取 | 待 M0 接线（配置项清单见 database/README 第二节） |
| M5-REQ-06 | M5 投放 | **M1 选品** | 类目基准 ROI/成交均值（选品侧聚合） | `category`/`avg_roi`/`avg_gmv`/`sample_count` | ROI 取值合理性校验（R6 风险应对） | 每周 | 待协商 |

## 二、本模块对外提供（供其他模块登记引用）

| ID | 提供方 | 接收方 | 内容 | 关键字段 | 用途 | 状态 |
|---|---|---|---|---|---|---|
| M5-OUT-01 | M5 投放 | **M1 选品** | 类目级托管转化数据回写（打分第 5 维「投放转化」） | `category`/`roi`/`gmv_fen`/`spend_fen`/`sample_count`/`period`/`generated_at` | M1 打分第 5 维输入（金额单位**分**，与 M1 C-2 草案对齐确认） | 待 M5 上线；经总控 data-audit 核对 |
| M5-OUT-02 | M5 投放 | **M3 素材优化** | 素材评估标签回流（投放实际效果更新 evaluation） | `asset_id`/`evaluation`(高效/潜力/探索期)/`impressions`/`gmv_fen` | M3 素材优化模板参数按类目重训练 | 待 M5 上线 |
| M5-OUT-03 | M5 投放 | **M1 商品主表** | 托管失败/不可投放原因（资质/素材/价格带） | `product_id`/`review_reason`/`campaign_id` | 指导 M1 选品过滤规则 | 待协商写入权限 |
| M5-OUT-04 | M5 投放 | **前端** | 托管看板数据（对齐后台列表列） | 商品/目标出价/诊断/曝光/花费/成交/补贴/操作 | 前端托管页 | 待开发 |

## 三、口径约定（需总控 data-audit 全局核对）

1. **金额一律「分」（int）**：spend/gmv/subsidy/balance 均以分存储；后台回读（元）×100 入库；M1 回写口径同此（回应 M1 BLOCKER-003）。
2. **时间存储一律 UTC（ISO8601 带时区）**，展示层转 UTC+8；时间戳字段名后缀 `_at`（遵循 DA-001 裁决）。
3. **枚举口径**：`evaluation`=探索期/高效/潜力；`status`=待托管/托管中/已暂停/不可投放/已结束；诊断=优秀/良好/N项待优化；均以 08 文档后台事实为准。

## 变更记录

| 日期 | 变更 |
|---|---|
| 2025 体系建立日 | 初始登记（M5-REQ-01~06 / M5-OUT-01~04） |
