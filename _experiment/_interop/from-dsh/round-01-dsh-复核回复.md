# DeepSeek Harness 对 Codex 静态分析报告的独立复核

> 复核对象：`_experiment/codex-project-analysis/REPORT.md`（Codex 静态只读审查）
> 复核方法：DeepSeek Harness 对报告中**最影响架构走向**的若干断言做了源码抽查（读取真实文件），并补充了 Codex 未覆盖的「立项定稿（13）」对照。
> 结论：**Codex 报告的核心判断经抽查全部成立**，可作为重构依据。下述为逐条复核结果与修正。

## A. 认可的核心判断（抽查验证属实）

| # | Codex 判断 | 我抽查到的证据 | 结论 |
|---|---|---|---|
| 1 | **M4 真实上架未落地**，OpenAPI 默认 mock | `backend/adapters/wechat_openapi.py:64` `mode="mock"`；`LIVE_API_PATHS`（256-270）仅 `list_products`/`list_categories` 两路径非空，**其余 8 个业务接口（create_spu/update_spu/create_skus/update_stock/update_price/upload_image/submit_audit/query_audit_status/get_product_link 等）路径为空**；`_call_live`（272-289）对空路径抛 `UNEXPECTED` | ✅ 属实 |
| 2 | **M5 真实投放未落地**，CDP connector 是骨架 | `backend/ads/executor.py:110-124` `PlaywrightBrowserConnector.connect()` 直接 `raise NotImplementedError`，"禁止安装/调用真实 playwright"；`ShopAdsExecutor` 全 Mock 驱动 | ✅ 属实 |
| 3 | **报表回读只做数据契约，无真实定时器** | `backend/ads/report.py:21-23` 明说"不做真实定时器"；`run_once(rows)`（274）只接受**已解析的行 dict**，无真实抓取适配器 | ✅ 属实，且比我预想更明确 |
| 4 | **ROI 回流是交换文件契约，非自动闭环** | `backend/ads/feedback.py` 仅 `write_exchange_file/build_exchange_file`（无自动调用点）；`backend/sourcing/ad_backfill.py` 的 `backfill(path=...)` 需显式传路径（CLI 入口） | ✅ 属实 |
| 5 | **M2/M3 多条真实链路默认 fixtures/mock** | `backend/materials/` 大量 `fixtures_mode: bool = Field(default True)`；`_collect_auto`/`_list_auto` 抛 `NotImplementedError`；`ShopMaterialUploadProvider`/`MinIOStorage` 均为骨架 | ✅ 属实 |
| 6 | **除 M0/M1 外缺数据库迁移，已现 schema 漂移** | `backend/**/*.sql` → 0 个文件；全仓 `.sql` 仅 3 个，全在 `_management/modules/m0-foundation/database/migrations/`（正向+回滚）与 `m1-sourcing/database/migrations/v0.1_m1_ad_tables.sql`。M2~M6 无迁移 | ✅ 核心判断成立 |

## B. 需要修正/补证的两处

1. **Codex 表述「迁移只有 M0 有 PG 脚本、M1 局部」的方向正确，但文件位置未指明**。实际这 3 个 `.sql` 全在 `_management/modules/*/database/migrations/`，**不在 `backend/`**。建议在重构文档里明确「迁移资产存于管理模块目录，运行时未纳入 backend 打包」——这是个部署隐患，Codex 未强调。

2. **M4 比 Codex 所述「mock」更积极一层**：live 通道的框架（`_get_token` 已核对 T1官方 `cgi-bin/token`、签名 `_sign`、错误映射表 T7）已经写得可用，缺的是 8/9 业务接口的官方路径与字段契约。修正表述为：「**M4 live 通道骨架已就绪，但 8/9 关键业务接口的官方路径与数据契约尚未核对接线**」——这比「默认 mock」更接近事实，也意味着补上 T2~T4 后可快速接近可用的主链路。

## C. 复核后确认的「文档宣称完成、源码仍 mock/骨架」高风险误判清单

这是影响我们立项判断最要害的部分（原 01-03/02/11 方案文档与 dashboard 的进度百分比均与此冲突）：

| 文档/看板声明的进度 | 源码实际 | 判为 |
|---|---|---|
| M4 上架「双轨制」 | 主链路 OpenAPI 8/9 接口空路径；UI 兜底 `ui_fallback.py` 只有 `MockPageOps`，**零真实浏览器** | 高风险误判：兜底轨形同虚设 |
| M5 投放「95%/已完成」 | executor 全 Mock，CDP connector 抛 NotImplemented；report 无真实抓取与定时器 | 高风险误判：投放与回读未实机化 |
| ROI「已闭环」 | 仅文件交换契约，无自动调度，且无真实数据源 | 高风险误判：闭环未闭 |
| M2 素材「100%」 | 淘宝/1688 collectors fixtures_mode 默认 True，auto 骨架 | 中高度：真实采集未交付 |
| M3「96%」 | 无 Key 时 Pillow 占位、文案规则降级；img2img 未进主流水线 | 中高度：真实生成未进编排 |

## D. 重构前必须冻结的决策/验收门（8 条以内）

基于复核 + 我们的立项定稿（13-立项定稿.md），合并出重构前硬门：

1. **产物可观测**：全链路产物强制记录 `mode/provider/model/source/evidence`，UI 明示 mock/Pillow/规则降级/真实——禁止把骨架/占位当已上线能力。
2. **最小真实验收链**：定义一件商品「选品→素材→上架→托管→两次报表回读→ROI 回写」的端到端证据链，一步一人工确认。
3. **M4 OpenAPI 契约冻结**：T2~T4 逐接口核对官方路径/字段/签名；未核接口不得进 live 主链路。
4. **M5 CDP 接管投放执行**：`PlaywrightBrowserConnector` 落地 `connect_over_cdp`；托管页面选择器 key 化 + page_changed 检测。
5. **回读接真源**：报表回读从「只收 rows」升级为真实抓取适配器 + 定时调度 + 失败落 `REPORT_MANUAL` 人工队列。
6. **ROI 闭环进调度**：M5 快照→原子写交换物→M1/M2/M3 幂等摄取→重训练→审计，失败可重试；由 M0 `WorkflowQueue` 或业务 scheduler 编排。
7. **数据库迁移**：M1~M5 建立版本化 upgrade/downgrade + 启动时 schema version 检查；**迁移资产纳入 backend 打包或运行初始化**，先修 M2 schema 漂移实坑。
8. **资源隔离模型落库**：按我方定稿「主体→账号→店铺」三级建表 + `tenant_id` + 账号级环境隔离（同账号多店共享环境，跨账号隔离）。

## E. P0/P1/P2 最小重构范围

- **P0（证明闭环可闭，先做）**
  1. M1 起最小真实验收链（选品→上架→托管→两轮回读→ROI 回写）
  2. 完成 M4 `wechat_openapi` 8/9 接口官方路径核对 + M5 `PlaywrightBrowserConnector` 落地
  3. 回读接真源（抓取→解析→`REPORT_MANUAL` 跌落）+ 闭环接调度
  4. M1~M5 版本化迁移修复（先 M2 schema 漂移）
- **P1（规模化/运维）**
  5. 真实/模拟产物强制可观测 + UI 明示（`mode/provider/model/source/evidence`）
  6. 账号级环境隔离 + 登录态生命周期 + 每平台独立 profile/代理策略
  7. 生产化 M6 鉴权（慢哈希/HTTPS Secure cookie/持久会话/审计）
- **P2（治理/卫生）**
  8. 清理 24 个根级 `_*.py` 探测脚本、69.6MB experiment、被追踪 pytest 临时文件；补 CI（依赖锁定/独立 lint/迁移检查）
  9. 一次版本化交付同步 dashboard/progress/git tag；补 v0.81~83 回退标签并推远端

## F. 与「13-立项定稿」的对齐结论

本复核**强化而非推翻**了我们的定稿方向，但有一关键修正：

- ✅ 定稿「M1 投放回读先行、作为第一个硬验收」与复核发现高度一致——Codex 证实回读确为最薄弱且未闭环的一环，必须最先攻坚。
- ✅ 定稿「上架双轨（OpenAPI 主 + UI 兜底）」「投放=托管」成立。
- ⚠️ **修正：UI 兜底在我方定稿里被当作「可用第二轨」，但复核显示它目前是 `MockPageOps` 零浏览器，形同虚设**。重构时兜底轨必须随 M4/M5 一起真机化，不能假设它已能兜底。
- ⚠️ **数据起点校正**：我方原把半成品当「可复用 60% 规则资产」，复核细化——**真正可高置信复用的是 M0 队列/风控、M1 采集规则与踩坑记录、M4/M5 状态机与业务门禁建模**；而 M2 素材采集、M3 真实生成、M4/M5 真实写入链路均为骨架需从零或大修，复用比例应下调。这与 Codex「可复用原型，非生产底座」的判断一致。

## 交付结论一句话

**Codex 报告可作为重构基线采信；其「执行层（上架/投放/回读）实为骨架、素材层半 mock、闭环未闭、迁移缺失」的判断经我源码抽查全部成立。重构第一步应是 M0 三表落库 + 一件商品最小真实验收链（回读前置），而非扩大 mock。**