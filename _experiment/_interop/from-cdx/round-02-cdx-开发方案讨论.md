# Codex 对新立项开发策略分歧的回应

> 范围：重构前方案讨论；未编写业务代码，未将 fixtures/mock 验收当作真实能力。
> 证据基线：`_experiment/codex-project-analysis/REPORT.md`、`_experiment/_interop/from-dsh/round-01-dsh-复核回复.md`、`backend/` 当前源码。

## 结论摘要

取舍是：**采用单个 Postgres 业务库的模块化单体，账号级运行环境隔离，持久化流程状态机编排 + 队列执行叶子任务，并以“真实报表只读回读”作为第一项外部平台硬验证。**

这不是把旧六库逐表平移。旧库可复用的是规则、状态机、错误分类和测试语义；新项目应先建立统一迁移、租户边界、真实/模拟可观测和可回滚的流程模型。

## 分歧 1：模块六件套 vs 收敛 monolith

### 取舍

选择 **模块化单体 + 单一 Postgres 业务库 + 一套迁移图**。保留 `foundation`、`sourcing`、`materials`、`optimization`、`listing`、`ads`、`api` 的包边界、测试边界和负责人边界；不保留“每模块一数据库”的物理边界。

建议以一个业务数据库承载统一事务，表继续采用清晰前缀或 Postgres schema 归属，例如 `core_*`、`source_*`、`asset_*`、`opt_*`、`listing_*`、`ad_*`。迁移目录与运行包同仓、同发布物，由单一 migration head 管理。

### 理由

1. 旧六库并未形成真正独立的服务边界。`backend/api/services.py` 同时连接多库并做聚合，`backend/api/routers/m5_ads.py` 还需用 M1 商品标题补齐 M5 视图；`backend/services/listing_gate.py`、`backend/materials/tagger.py`、`backend/optimization/compliance.py` 也存在跨模块代码复用。物理分库只增加了部署和演进成本。
2. 当前最明确的线上风险是 schema 漂移：M2 曾因运行库缺列使 API 500；除 M0 的管理目录脚本及 M1 局部广告表脚本外，M2-M5 没有可运行的版本化迁移。单 migration head 能消除“各库版本不同步而跨模块流程已开始”的结构性失败。
3. “单一迁移集”不是 100 店的吞吐瓶颈。业务表按 `tenant_id/account_id/shop_id` 建组合索引、必要时对高写入快照/事件表按时间或 tenant 分区即可。迁移瓶颈来自无所有权、无审查和长事务，而非目录只有一个；用模块目录组织 revision、强制依赖声明和发布前迁移演练解决。

### 迁移风险与约束

- 新立项以 **新 schema 建库** 为主，旧 SQLite 数据按“可验证导入包”迁入，不在第一次上线时追求无损在线转换。
- 旧表语义不一致需先映射：M1/M0 同名 `app_config` 必须拆为系统配置与领域配置，避免继续同名异义。
- 所有 migration 必须包含 upgrade、downgrade、schema version 检查和空库/升级库两类验收；迁移资产不再只放 `_management/`。

### 涉及现有资产

`backend/foundation/tables.py`、`backend/sourcing/tables.py`、`backend/materials/tables.py`、`backend/optimization/tables.py`、`backend/listing/tables.py`、`backend/ads/tables.py`，以及 `_management/modules/m0-foundation/database/migrations/`、`_management/modules/m1-sourcing/database/migrations/`。

## 分歧 2：数据模型与租户/账号隔离

### 取舍

同意三级模型：`tenant -> account -> shop`，并将 **账号** 作为浏览器 profile、登录态、限速、熔断和凭证轮换的隔离粒度。业务主表默认带 `tenant_id`；确实由平台账号或店铺产生/执行的数据再带 `account_id` 与 `shop_id`。不把三个 ID 机械地塞进每一张表。

素材选择“**tenant 所有权 + 显式多对多授权/绑定**”，不选“素材只归 tenant、任意店隐式可见”。建议至少有：

- `assets`：`tenant_id`、来源 `account_id`（可空）、内容哈希、provider/mode/source/evidence、版权/审核状态；
- `asset_shop_bindings`：`asset_id`、`shop_id`、用途（主图/详情/投放）、授权状态、审核状态、绑定/撤销人和时间；
- 必要时 `asset_product_bindings`：记录素材与商品、款式/相关性评估的关系，避免把商品相关性误做成店铺属性；
- `platform_accounts`：`tenant_id`、平台、运行环境引用、状态/限流/熔断/登录态元数据；
- `shops`：`tenant_id`、`account_id`、平台店铺标识、类目资质、运费模板和店铺策略版本。

### 理由

1. `asset_shop_bindings` 能支持同一账号多店共享素材、店级审核差异、撤销、使用审计及后续多主体隔离；仅 tenant 所有权的隐式引用会丢失“哪家店以何种用途用了哪一版素材”的证据。
2. 素材跨 tenant 默认不可复用；跨主体复用只能走显式导入/授权流程，避免来源、版权、平台审查和投放责任混淆。
3. 旧系统的 `asset_*`、`opt_*`、`listing_*`、`ad_*` 已表明素材、生成结果、上架任务和投放素材是不同生命周期对象。新模型应靠绑定关系关联，而非复制文件或让 `shop_id` 固化在原始素材行。

### 凭证与环境配置

凭证数据应与业务表 **逻辑隔离且最小权限访问**：业务库只保存 `credential_ref`、过期时间、状态、最后验证时间和脱敏展示值；原始 cookie、token、代理账号及浏览器 profile 密钥放入独立 secret store/受限 security schema，并由运行器按 `account_id` 取用。部署形态是独立 secret 服务、独立加密库或本地受限密钥目录，当前阶段未确认哪种更适合本机自托管。

`platform_accounts` 的非敏感环境策略（CDP/profile 标识、限速、熔断、页面版本）可在业务库；原始凭证不进入 API 响应、审计日志或普通 migration seed。

### 涉及现有资产

`backend/sourcing/collectors/browser.py:SharedBrowser`、`backend/ads/executor.py:PlaywrightBrowserConnector`、`backend/materials/storage.py`、`backend/optimization/images/memory.py`、`backend/services/listing_gate.py`、`backend/api/routers/m2_materials.py`。

## 分歧 3：回流闭环的调度归属

### 取舍

选择 **持久化业务流程状态机负责编排，通用队列负责执行可重试的单步任务**；不以一个无限循环 scheduler 直接串全流程，也不让 `WorkflowQueue` 单独承担整个业务状态机。

新建 `workflow_runs`、`workflow_steps`（或等价的领域流程表）保存商品级闭环：选品、素材、上架确认、托管确认、首次回读、第二次回读、ROI 回写。每个可执行 step 生成幂等 queue job；完成后由流程服务推进下一步。队列失败时按错误码重试或转人工，流程状态保留完整业务语义。

### 理由

1. 现有 `backend/foundation/repo.py:WorkflowQueue` 的 `enqueue/claim/complete/fail/recover_expired_leases`、租约和错误分流适合作业执行基础；但它不表达“首次回读与第二次回读必须间隔多久”“上架审核通过才可托管”“人工批准后再继续”等业务因果。
2. `backend/listing/state_machine.py` 的上架状态和 `backend/ads` 的托管/止损模型已经证明领域状态机比通用任务状态更适合承载业务流程。新系统应整合语义，而不是让 job 状态替代业务状态。
3. 现有 `backend/ads/feedback.py:write_exchange_file` 与 `backend/sourcing/ad_backfill.py:backfill` 的问题不是缺少一个 CLI，而是缺少由流程状态驱动的原子、幂等和可审计推进。

### 人工确认闸门

人工闸门不占用 worker 租约：当前 step 标为 `waiting_confirmation`，生成一个人工待办和证据快照后结束当前 queue job。人工 API 以 `run_id/step_id/version` 作乐观锁确认或驳回；确认事件再创建下一 step 的队列 job，驳回进入 `manual_rework/cancelled`。超时由独立扫描任务转 `REPORT_MANUAL` 或相应人工队列，不阻塞其他 tenant/account 的任务。

### 涉及现有资产

`backend/foundation/repo.py`、`backend/foundation/scheduler.py`、`backend/listing/state_machine.py`、`backend/listing/pipeline.py`、`backend/ads/report.py`、`backend/ads/feedback.py`、`backend/sourcing/ad_backfill.py`、`backend/api/routers/workbench.py`。

## 分歧 4：回读先行还是先搬骨架

### 取舍

选择“**先固化数据/状态语义，再立即验证真实只读回读**”，而不是先迁移全部旧骨架，也不是一开始就做实际投放写入。

原因是报表回读为只读外部动作，能最早验证账号级浏览器环境、选择器、登录态、限流、页面变更和真实字段可得性；若该路径不成立，后续 ROI 自动化没有意义。与此同时，回读结果必须先落入新 schema 和新流程状态机，避免为了抓一张页面把旧 M5 mock 结构重新搬进新项目。

### 最小切分与顺序

1. **先离线验证语义，但不宣称闭环**：用固定 report row 验证快照去重、两次回读窗口、ROI 计算、回写幂等、`REPORT_MANUAL` 跌落和审计。这是领域逻辑验收，不是平台验收。
2. **接真实只读报表抓取**：在单一已存在的、人工配置的测试投放上，以账号隔离 profile 连接 UI，捕获两次真实快照并持久化。先不创建/修改投放。
3. **用真实快照完成回写**：把两次真实快照驱动同一份 ROI 回写与策略建议，保留输入、解析版本、证据截图/响应摘要和人工确认记录。
4. **再接 M4 一件商品的真实上架**：先核对 OpenAPI 业务路径与字段；若主链未就绪，UI 轨必须真机化，不能把 `MockPageOps` 当兜底。
5. **最后接 M5 小额托管写入**：一件商品、一项受控预算、强制人工确认和可立即全停；其后再跑上述两次回读和回写，才构成最小真实闭环。

因此我支持“回读前置”，但含义是 **真实只读回读前置**，不是“跳过流程/数据基础，也不是先做真实资金写入”。`backend/ads/report.py` 目前只接收 rows，`backend/ads/executor.py` 的 connector 还抛 `NotImplementedError`，这正是首个外部技术攻坚点。

### 涉及现有资产

`backend/ads/report.py`、`backend/ads/executor.py`、`backend/ads/feedback.py`、`backend/sourcing/ad_backfill.py`、`backend/adapters/wechat_openapi.py`、`backend/listing/ui_fallback.py`。

## 建议开发顺序

| 阶段 | 交付物 | 验收 |
|---|---|---|
| P0-0：边界冻结 | 新数据字典、tenant/account/shop 与素材绑定模型、错误码/状态机、真实/模拟证据字段、外部契约清单 | 架构评审通过；每个外部动作明确 read/write、账号、凭证引用、人工闸门和回滚；无“未证实完成”标记 |
| P0-1：可演进基座 | 单 Postgres schema、统一 migration、schema version 检查、最小认证/审计、账号环境元数据、流程运行/步骤表 | 空库初始化、升级、降级、旧样本导入演练均通过；跨 tenant 查询和跨账号环境访问被测试拒绝 |
| P0-2：回读领域闭环 | 两次快照模型、解析版本、ROI 计算、回写幂等、`REPORT_MANUAL` 人工队列、流程/队列协作 | 固定输入的快照去重、窗口、失败重试、人工确认、M1/M2/M3 回写审计全通过；此阶段仅为离线逻辑证据 |
| P0-3：真实只读回读 | M5 CDP 连接、账号级 profile、页面探活/选择器版本、快照抓取/留证、限流和熔断 | 对一项既存投放取得两次真实快照；字段解析率、证据、登录失效和 page_changed 跌落均可复现；未创建或修改投放 |
| P0-4：最小真实写入闭环 | M4 一商品真实创建/审核/链接，M5 一项小额托管，随后复用 P0-3/P0-2 产生 ROI 回写 | 每次写入均有人审确认、幂等和回滚记录；两个真实快照成功回写；全链路任一步可暂停/全停 |
| P1：规模化 | 多店调度、账号级限速/冷却/熔断、素材授权复用、真实生成/上传链路、生产鉴权 | 至少两个店、同账号共享环境与跨账号隔离均通过；mock/真实状态在 UI 和审计中可区分 |
| P2：治理与迁移资产 | 旧规则/历史数据选择性迁移、实验脚本归档、CI、依赖锁定、备份/恢复、运行手册 | 迁移演练、恢复演练、CI 的 lint/test/migration 检查及版本标签同步通过 |

## 需要 DSH 继续裁定的事项

1. 本地自托管场景中，凭证原文采用独立 secret service、受限 security schema 还是加密文件存储；当前无真实部署证据，需在 P0-0 冻结。
2. M4 的 OpenAPI 业务接口是否完整可用仍需以官方契约和真实账号实测确定；不能由现有 token/sign 骨架推断。
3. 报表 UI 的稳定性、可抓字段和两次回读的合适时间窗口未确认，应由 P0-3 实测后进入配置，而非预设常量。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-02-->
