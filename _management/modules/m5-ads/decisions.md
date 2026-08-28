# M5 自动小店投放（商品托管） · 决策记录（decisions）

> 记录本模块关键技术决策：决策内容、理由、备选方案、日期、决策人。

| 日期 | 决策 | 理由 | 备选方案 | 决策人 |
|---|---|---|---|---|
| 2025 体系建立日 | D-M5-01：金额一律「分」（int）存储、时间 UTC（ISO8601 带时区）存储 + 展示转 UTC+8、时间戳字段名 `*_at` | 总控 data-audit DA-001 裁决（REC-005），与微信小店 channels API/投放后台口径一致；浮点金额误差归零 | 元(float)/本地时区存储 | 总工（遵循总控裁决） |
| 2025 体系建立日 | D-M5-02：枚举值**英文存储 + 中文注释/展示映射**（status=pending/active/paused/not_eligible/ended；diagnosis=excellent/good/optimize_1/optimize_n；evaluation=exploring/efficient/potential） | 基线惯例（sourcing 状态 active、M2 EVALUATION_VALUES 全英文）；避免中文枚举在跨库/JSON/排序中编码不一致 | 中文枚举直存 | 总工 |
| 2025 体系建立日 | D-M5-03：`ad_materials.evaluation` 枚举与 **M2 完全一致**（exploring/efficient/potential），M5 只消费不另立口径 | data-audit DA-002/DA-003 口径统一；评估标签回流（M5→M3）与素材入库（M2→M5）同词表 | 中文「探索期/高效/潜力」 | 总工 |
| 2025 体系建立日 | D-M5-04：代码落地包名用 `backend/ads/`（顶层包，同 sourcing/materials/optimization 平级），对应 03 文档「services/shop_ads/」模块划分 | 与基线包结构一致（conftest sys.path 注入 backend 根即可导入）；短名清晰 | backend/services/shop_ads/ | 总工 |
| 2025 体系建立日 | D-M5-05：`app_config`（M0 共享表）**只读**：repo 提供 `read_app_config`，禁止 INSERT/UPDATE；本模块预算/阈值配置走 `ADS_*` 环境变量默认值 + 运行时只读覆盖 | 宪法第 4 节共享表只读铁律；写入经总控协调 | 本模块自建配置表 | 总工 |
| 2025 体系建立日 | D-M5-06：`ad_report_snapshots` 以 `(campaign_id, recorded_at)` 唯一约束实现幂等 upsert（同周期只保留最新快照） | 回读重试/断点续跑不产生重复快照；报表口径稳定 | 应用层去重 | 总工 |
| 2025 体系建立日 | D-M5-07：v0.3 执行层（Playwright）先做**抽象接口 + fixtures 模拟**，真实 UI 依赖登录态与实机探针（总控待用户确认清单） | 无登录态/无实机时开发与测试不阻塞；接口稳定后接真实适配器 | 等登录态就绪再开发 | 总工（遵循总控指示） |
| 2025 体系建立日 | D-M5-08：`normalize_diagnosis` 英文枚举**幂等原样返回**（report.py 与 stop_loss.py 统一口径；excellent/good/optimize_1/optimize_n/unknown 输入输出不变） | v0.4 集成交叉断言发现两模块英文输入行为不一致（report 原「英文→unknown」、stop_loss 幂等）；统一为幂等防已归一化快照回流丢失枚举 | report 保持 unknown / 两模块都 unknown | 总工（集成修整） |
