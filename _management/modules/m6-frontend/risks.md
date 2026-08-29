# M6 前端控制台 · 风险预判清单（risks）

> 版本：v1.0（筹备版）｜ 撰写：M6 总工程师 ｜ 日期：2026-08-29
> 开工前由总工程师撰写；每条含风险描述 / 等级 / 应对方案。已知全局风险见 `_management/logs/pitfall-log.md`（P-001~P-018）。

## 一、后端鉴权与登录态（10 文档第六节「管理后台加登录」）

| # | 风险 | 等级 | 应对方案 |
|---|---|---|---|
| R-API-01 | 后端 API 层补鉴权时破坏既有模块 CLI/repo 调用（API 全开放现状改为登录态） | 高 | API 层为**独立 FastAPI 应用**（`backend/api/`），不修改各模块包；鉴权仅作用于 HTTP 路由层；各模块 CLI/内部调用不受影响；回归以各模块既有 pytest 全绿为准 |
| R-API-02 | 会话/Token 方案选错导致 CSRF/XSS 窃取 | 高 | **总控裁决：会话表挂 M0 foundation（跨模块共享）**，API 层只消费不重复建表（AuthStore 接口 + fixtures 模式过渡）；登录成功后发 httpOnly + SameSite=Lax cookie 会话；禁 localStorage 存 token；CORS 白名单收口（仅前端源，`M6_CORS_ORIGINS`），`allow_credentials=True` 配合明确 origin |
| R-API-03 | 密码/密钥明文泄漏（.env 入 git、日志打印） | 高 | 密码只走环境变量（`M6_ADMIN_PASSWORD_HASH` 等，.env.example 只列名不给值）；后端用 `foundation/security.py` 脱敏；前端 ProviderSettings 只显示 masked 值（沿用旧系统 `*_key_masked` 模式） |
| R-API-04 | 会话过期/登出后前端缓存残留 | 中 | 前端路由守卫统一走 `GET /api/auth/me` 判定；401 全局拦截跳登录；登出调用 API 失效会话并清前端状态 |
| R-API-05 | 一键全停（S8）被无权限调用 | 高 | 全停/预算/配置类写接口仅管理员角色可调；API 层记录操作人/时间审计（对齐 10 文档四层防线语义） |

## 二、API 契约与数据口径（核心风险区）

| # | 风险 | 等级 | 应对方案 |
|---|---|---|---|
| R-DATA-01 | **金额口径混用**：M1 商品池价格是 **float 元**（platform_price/real_cost/suggested_price、SourceItem.price），M4/M5 是 **int 分**（price_cents/cost_cents/spend/gmv/subsidy/balance），M1 的 C-2 契约 sales_amount 又是分——前端极易换算错位 | 高 | **总控裁决（DA-001，2026-08-29）：API 层对外金额一律「元（float）」**——内部存储分不变，API 层 ÷100 换算；M1 元字段直接透传；前端只消费元，零换算。lib/format.ts 仅做元格式化（`formatYuan`），保留 `centsToYuan` 兜底函数供未来契约兼容；契约草案与单测覆盖换算断言 |
| R-DATA-02 | 时间口径：存储/传输 UTC ISO8601（部分契约带 +08:00 显式标注、部分带 Z），展示需 UTC+8 | 中 | API 层统一输出 ISO8601 带时区（推荐 UTC Z）；前端统一 `formatDateTime()` 解析后转 Asia/Shanghai 展示，**不在组件内手动 +8h**；后端字段名 `*_at` 后缀约定保留 |
| R-DATA-03 | 枚举中文映射漂移：error_code 7 码、M4 状态机 9 态、M1 compliance 三态、M2 relevance 四态/evaluation 三态、**M5 status/diagnosis 本身是中文枚举**（待托管/托管中/…、优秀/良好/…）——英文枚举与中文枚举并存，映射易漏 | 高 | context/README.md 建**唯一展示口径表**（见「展示口径」节），前端 lib/enums.ts 集中映射 + 单测锁定；API 层枚举值原样透传（不翻译），翻译只在展示层；M5 中文枚举入库值原样透传展示 |
| R-DATA-04 | 接口契约未会签导致字段名/类型漂移（各模块无现成 HTTP API，契约由 M6 起草） | 高 | 契约草案写入 context/README.md → 派工前提交总控 → 各模块总工会签（data-audit 登记）；API 层单测 fixtures 锁定字段名；变更必须同步契约文档（宪法第 8 节文档同步） |
| R-DATA-05 | 分页/筛选/聚合口径不一致（前端展示与后台数字对不上） | 中 | API 层聚合与各模块 CLI 复用同一 repo 函数（不重写统计逻辑）；看板数字以 API 返回为准；集成验收逐页核对 |
| R-DATA-06 | 无数据/弱样本状态未表达（M1 五维 ad_conversion active=False、M5 无快照） | 中 | API 响应保留 `active`/`note` 字段原样透传；前端展示「无数据」占位而非错误；不凭空补零 |

## 三、前端工程与依赖

| # | 风险 | 等级 | 应对方案 |
|---|---|---|---|
| R-FE-01 | Node/npm 源与代理：本机 Node v24.19.0（已就绪）；npm 安装可能受本机代理（P-009 同网络环境）影响 | 中 | 若 npm 装包失败，先核 npm 代理配置（`npm config get proxy`，参照 P-009 git 代理 127.0.0.1:7897 同款）；锁定版本（package.json 精确版本） |
| R-FE-02 | 端口冲突：8787 已被占用（P-008），前端 3000 / API 8000 可能被占 | 中 | 起服务前探测端口；API 默认 8000、前端默认 3000，可配覆盖；避免 8787/8788 |
| R-FE-03 | Next 15 + React 19 与旧组件兼容性（旧组件为 React 19 编写，兼容；但 Tailwind 配置/postcss 需对齐 3.4.x + postcss 8.5.10 override，P-010 类坑） | 中 | 脚手架以旧系统 package.json 依赖清单为基线（含 `overrides: postcss 8.5.10`）；`npm install` 后立即 `next build` 冒烟 |
| R-FE-04 | 构建产物/缓存污染（旧系统 .next 有 failed 目录） | 低 | 新 frontend/ 全新初始化，不复制 .next/node_modules；.gitignore 排除 node_modules/.next |
| R-FE-05 | 浏览器渲染与展示口径测试缺失 | 中 | 口径转换（分→元/时间/枚举）用 vitest 纯函数单测锁定；组件冒烟用 vitest + testing-library |

## 四、旧系统组件复用（P1-7）

| # | 风险 | 等级 | 应对方案 |
|---|---|---|---|
| R-REUSE-01 | 旧组件强耦合旧 API 契约与旧数据模型（`lib/api.ts` 的 Product 宽表类型、旧端点 `/products`、`/listing/packages` 等 26 个端点），新系统按模块分库、字段/端点全变 | 高 | **策略：搬 UI 结构不搬数据层**——`lib/api.ts` 完全重写对接新 API；组件 props 接口保留（如 ImageReviewPanel 的 onDecision/onApproveBatch），内部取数改走新 api 客户端；旧端点清单仅作功能对照 |
| R-REUSE-02 | 大组件内部逻辑耦合旧流程：ImageReviewPanel 17KB、ListingManagerView 25KB（含 recognize/upload 流程）、DataViews 19KB | 高 | 分步改造：先还原组件到「props 驱动 + 无内部取数」的纯展示，再接入新 API；大组件拆子代理时任务书明确「每完成一文件立即落盘」（P-014） |
| R-REUSE-03 | 旧 workflow.ts 状态机按**中文状态文本匹配**推导阶段（`deriveWorkflowStage` 用 includes("已上架") 等），新系统状态机为枚举（M4 9 态 pending/creating/draft/…） | 中 | 重写 `lib/workflow.ts` 为新枚举→阶段映射（对齐 09 文档四节 9 态），保留旧文件仅作参考；映射表单测锁定 |
| R-REUSE-04 | 旧组件「待上架商品」「上架包确认」语义与新系统 9 态/闸门语义差异（旧 ListingManagerView 按旧 products.status 判断） | 高 | 改造点登记到 context/README.md 组件清单表（每组件：来源/大小/props/改造点）；派工前总工评审改造点，子代理任务书附改造清单 |
| R-REUSE-05 | 旧壳不搬（第二波融合清单「排除」项：旧前端框架整体），避免继承旧路由/旧样式包袱 | 低 | 新工程全新脚手架；只搬 components 目录中选定组件源文件 |

## 五、数据与安全（敏感数据不落前端）

| # | 风险 | 等级 | 应对方案 |
|---|---|---|---|
| R-SEC-01 | API 密钥（DeepSeek/Kimi/Wan/微信/COS）泄漏到前端包 | 高 | 密钥仅后端持有；前端 ProviderSettings 只读 masked 值（`has_*_key` + `*_key_masked`），保存动作 POST 到后端；`NEXT_PUBLIC_*` 只放 API 地址，绝不放密钥 |
| R-SEC-02 | 登录态/token 落 localStorage 被 XSS 窃取 | 高 | httpOnly cookie 会话；前端不存任何凭证；XSS 防护：React 默认转义、禁 `dangerouslySetInnerHTML`（旧组件如使用需审查替换） |
| R-SEC-03 | 日志/审计含敏感字段（打点含 token/cookie/手机号） | 中 | 前端日志不打印响应体敏感字段；后端 API 日志走 `foundation/security.py` 脱敏；操作审计只记操作人/动作/对象 ID |
| R-SEC-04 | CORS 配置过宽（`*` 允许） | 中 | CORS 白名单 = 前端 origin（环境变量配置）；credentials 模式精确匹配 |
| R-SEC-05 | 展示层把内部错误码/堆栈直接抛给用户 | 低 | API 错误统一 `{code, message, detail?}` 结构；前端按 error_code 中文映射展示（VERIFICATION_REQUIRED→「需验证码，已暂停该任务」等），堆栈仅日志 |

## 六、跨模块协作与测试纪律

| # | 风险 | 等级 | 应对方案 |
|---|---|---|---|
| R-COL-01 | 跨模块取数未登记 → 数据口径核对缺失（宪法第 5 节） | 中 | M6 API 层取数申请已登记 data-audit.md（DA-011，见 context/README.md 末节）；契约变更经总控核对 |
| R-COL-02 | 并行开发竞态：API 层子代理在途期间其他模块回归误报失败（P-015/P-018 同型） | 中 | API 层只读消费各模块 repo、零修改各模块代码；验收前确认在途代理已完成（list_agents 无 running）；失败先复跑判定中间状态 |
| R-COL-03 | pytest 共享 basetemp / Windows GBK（P-001/P-011/P-017） | 高 | 后端 API 层测试一律 `python -X utf8 -m pytest --basetemp=".pytest-tmp-m6"`；任务书写明；前端 vitest 独立 |
| R-COL-04 | 子代理长任务中断零产出（P-014） | 中 | 页面建设/闸门工作台等大任务优先 workflow 工具或多轮小步落盘；任务书强制「第一动作写盘、每文件即落盘」 |
| R-COL-05 | 前端与 API 并行开发时的联调阻塞 | 中 | 子代理②允许先用 mock（`NEXT_PUBLIC_USE_MOCK=1` + mock 数据文件）开发 UI，①完成后切真实 API；验收以真实 API 为准 |

## 七、里程碑风险

| # | 风险 | 等级 | 应对方案 |
|---|---|---|---|
| R-MS-01 | v1.0 验收依赖真实登录态/真实数据（11 文档 ⏳ 项：小店素材库登录态、DeepSeek Key 等） | 中 | v1.0 验收标准定义为 **fixtures/mock 模式下控制台可启动 + 各页数据可展示 + 人工闸门可操作**（不依赖真实平台）；真实数据接入为 v1.1 增量，环境就绪即启用 |
| R-MS-02 | 页面数量大（看板/队列/素材/上架/托管/闸门/异常）导致工期膨胀 | 中 | 里程碑按页分组（v0.4 看板+队列、v0.5 上架+托管、v0.6 审核+预审、v0.7 闸门+异常）；每迭代独立可验收，滚动排期 |
