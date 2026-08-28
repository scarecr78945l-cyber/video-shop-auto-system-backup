# M1 自动选品 · 跨模块数据需求登记（data-requests）

> 依据宪法第 5 节：本模块需要其他模块数据时在此登记，并同步登记 `_management/logs/data-audit.md`，由总控转达对应模块总工。
> 每条：需求 ID ｜ 需要什么 ｜ 字段 ｜ 用途 ｜ 频率 ｜ 状态。

---

## 需求清单

| ID | 需要方 | 提供方 | 内容 | 关键字段 | 用途 | 频率 | 状态 |
|---|---|---|---|---|---|---|---|
| M1-REQ-01 | M1 选品 | **M5 投放** | 类目级托管转化数据回写 | `category`/`roi`/`sales_amount`/`sample_count`/`period`/`generated_at` | 打分第 5 维「投放转化」输入（无数据自动折算不生效） | M5 报表周期（建议每日或每周） | 待 M5 上线；契约草案见 context/README C-2 |
| M1-REQ-02 | M1 选品 | **M4 上架** | 商品池消费确认：哪些 `product_id` 已上架/拒审，类目通过率 | `product_id`/`listing_state`/`reject_reason`/`category` | ①`category_listing_memory` 类目记忆回流（选品偏好）；②闸门放松依据 | 上架事件驱动 | 契约待总控牵头定义（C-3 反向） |
| M1-REQ-03 | M1 选品 | **M0 基座** | 共享 Chrome CDP 端口/登录态就绪状态 | `cdp_port`/`login_state` | 真实采集前置条件 | 启动时探测 | 已具备（probe-browsers） |
| M1-REQ-04 | M1 选品 | **M0 基座** | `app_config` 类目白名单/打分权重运行时配置 | `key`/`value`(JSON) | 配置化改造（S1） | 每次打分 | 接线开发中 |

## 本模块对外提供（供其他模块登记引用）
- M1-OUT-01 → M4：商品池快照（`m1-pool-<date>.json`，C-3）— 上架输入。
- M1-OUT-02 → M2：淘宝参考素材 URL（C-4）— 素材收集输入。
- M1-OUT-03 → 总控：账本/熔断/漏斗统计（`source_runs`/`pipeline` 结果）— dashboard 监控。

## 变更记录
| 日期 | 变更 |
|---|---|
| 2026 体系建立日 | 初始登记（M1-REQ-01~04） |
