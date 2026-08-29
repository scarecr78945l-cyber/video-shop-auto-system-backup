# M6 前端控制台 · 上下文库（context）

> 模块的持久记忆，跨会话不丢失。任何代理（含子代理）开工前先读本目录。
> 版本：v1.0（筹备版）｜ 维护：M6 总工程师 ｜ 铁律：只写字段名/契约/口径，**绝不写明文密钥/Token/Cookie 值**（宪法第 4 节）。
> 本目录文件：`README.md`（本文：API 契约草案 / 展示口径 / 旧组件清单 / 环境事实）、`data-requests.md`（跨模块数据需求登记，沿用宪法第 5 节）。

---

## 一、API 契约草案（backend/api/，FastAPI）

> **状态**：草案 v0.1，由 M6 起草；总控已转达 M0~M5 各模块总工会签（DA-011，2026-08-29 派发，回传后定稿）。
> **架构**：`backend/api/` 独立 FastAPI 应用，聚合 M0~M5 repo/服务能力，**前端唯一取数通道**；不改动各模块包。
> **统一约定（总控裁决 2026-08-29 更新）**：① 全部 JSON 金额输出「元（float）」——内部存储分不变，API 层 ÷100 换算（M1 元字段直接透传）；**前端只消费元，零换算**；② 时间 ISO8601 UTC（`Z`）；③ 错误统一 `{code, message, detail?}`，code 复用 DA-008 码表；④ 鉴权：除 `/api/auth/login` 外全部需登录（会话 cookie httpOnly）；**会话表挂 M0 foundation（跨模块共享），API 层只消费不重复建表**——开发期 AuthStore 接口 + fixtures 内存实现过渡（`M6_API_AUTH_MODE=fixtures|m0`）；CORS 白名单收口（`M6_CORS_ORIGINS`）。

### 1.1 鉴权与系统（M0 域）

| 方法 | 路径 | 用途 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 管理后台登录 | body `{username, password}`；成功设 httpOnly 会话 cookie |
| POST | `/api/auth/logout` | 登出 | 失效会话 |
| GET | `/api/auth/me` | 当前用户/权限 | 前端路由守卫用；返回 `{username, role}` |
| GET | `/api/overview` | 总览看板聚合 | 任务队列统计（stage/status/error_code 分组计数）、错误码分布、今日漏斗、风控状态（余额/预算/kill_switch） |
| GET | `/api/jobs` | 任务队列列表 | 过滤：stage/status/error_code/request_id；分页 |
| GET | `/api/jobs/{id}` | 任务详情 | 含 evidence 脱敏摘要 |
| POST | `/api/kill-switch` | 一键全停（S8） | 管理员；body `{enabled}`；对齐 M0 `M0_KILL_SWITCH`/app_config `risk.kill_switch` |
| GET/PUT | `/api/app-config/{key}` | 配置读写 | 类目白名单/预算上限/权重等；管理员写 |
| GET | `/api/logs` | 操作日志（脱敏） | 只读；敏感字段已脱敏（foundation/security.py） |

### 1.2 选品（M1 域，对应 sourcing repo/CLI）

| 方法 | 路径 | 用途 | 说明 |
|---|---|---|---|
| GET | `/api/products` | 商品池列表 | 按 score 排序；过滤 category/state/score 区间；返回含 score_breakdown 摘要、compliance 三态 |
| GET | `/api/products/{id}` | 商品详情 | 完整打分理由（五维 raw/weight/weighted/reasons）+ quotes + source_evidence |
| GET | `/api/sourcing/status` | 调度状态 | 各源账本（next_run_at/throttle_level/consecutive_failures/status 含 waiting_*）；对齐旧 `/sourcing/status` 语义 |
| POST | `/api/sourcing/gate-confirm` | 选品复核闸门 | body `{product_id}`；manual_review → pool（对齐 CLI `gate-confirm`）；记录操作人 |
| GET | `/api/sourcing/report` | 选品周报 | 来源/错误/漏斗聚合（复用 `sourcing/report.py`，P1-6） |

### 1.3 素材（M2 域，对应 materials repo）

| 方法 | 路径 | 用途 | 说明 |
|---|---|---|---|
| GET | `/api/assets` | 素材库列表 | 过滤 asset_type/source_platform/relevance_status/upload_status/evaluation；分页 |
| GET | `/api/assets/{id}` | 素材详情 | 规格字段（duration/resolution/size）+ 双去重指纹 + 评估标签 |
| POST | `/api/assets/{id}/relevance-confirm` | 素材相关性人工确认 | multi_style → 确认目标款（调 M2 `RelevanceGateService` 语义）；记录操作人 |
| GET | `/api/assets/uploads` | 上传记录 | upload_status 追踪（对齐旧素材库页） |

### 1.4 素材优化/图片审核（M3 域，对应 optimization repo）

| 方法 | 路径 | 用途 | 说明 |
|---|---|---|---|
| GET | `/api/optimization/batches` | 生图批次列表 | 过滤 status（含待审核）；对齐旧 `image-batches` 语义 |
| GET | `/api/optimization/batches/{id}` | 批次详情 | assets（main/detail/status/rejection_reason/audit） |
| POST | `/api/optimization/assets/{id}/decision` | 图片审核人工判定 | body `{decision: approve/reject, reason?}`；对接 M3 review gate + P0-2 规则草稿闭环（learning_rule_drafts） |
| POST | `/api/optimization/batches/{id}/approve` | 整批通过 | 对齐旧 `image-batches/{id}/approve` |
| GET | `/api/optimization/copywrites` | 文案/标题候选 | 只读（title/script/ad/badge） |

### 1.5 上架（M4 域，对应 listing repo/状态机）

| 方法 | 路径 | 用途 | 说明 |
|---|---|---|---|
| GET | `/api/listing/tasks` | 上架任务列表 | 按 9 态 status 过滤；列：product_id/title/status/attempts/error_code/updated_at |
| GET | `/api/listing/tasks/{id}` | 上架任务详情 | 状态机轨迹 + gate_result + platform_spu_id/product_link + 拒审记录（audit_records） |
| GET | `/api/listing/tasks/{id}/op-logs` | 微信操作日志 | 只读（脱敏摘要） |
| POST | `/api/listing/tasks/{id}/confirm` | 上架最终确认闸门 | pending → 入队创建；记录操作人（10 文档第五节闸门） |
| POST | `/api/listing/tasks/{id}/retry` | 拒审修复后重提 | rejected/retry_candidate → 二次门禁后重提 |
| GET | `/api/listing/ready` | 待上架商品 | 对齐旧 `listing-ready-products` 语义 |

### 1.6 投放/托管（M5 域，对应 ads repo）

| 方法 | 路径 | 用途 | 说明 |
|---|---|---|---|
| GET | `/api/ads/campaigns` | 托管看板列表 | **对齐后台列**：商品/目标出价(target_roi+target_type)/诊断/曝光/花费/成交/补贴/操作（09 文档四节）；金额分 int |
| GET | `/api/ads/campaigns/{id}` | 托管详情 | 设置（target_type/target_roi/material_ids）+ 报表快照序列（ad_report_snapshots 按 recorded_at） |
| GET | `/api/ads/account` | 投放账户状态 | 余额（分）/status（active/risk_control/waiting_*/paused）/节流级（对齐 S5 余额告警） |
| POST | `/api/ads/campaigns/{id}/pause` | 暂停托管 | 对齐后台操作；记录操作人 |
| POST | `/api/ads/campaigns/{id}/resume` | 恢复托管 | — |
| POST | `/api/ads/campaigns/{id}/end` | 结束托管 | — |
| POST | `/api/ads/campaigns/{id}/materials` | 添加/换素材 | body `{material_ids}`；优选顺序 高效>潜力>探索期提示 |
| GET | `/api/ads/report` | 报表聚合 | 按日聚合 spend/gmv/subsidy/impressions（分 int） |

### 1.7 人工闸门工作台聚合（跨模块）

| 方法 | 路径 | 用途 | 说明 |
|---|---|---|---|
| GET | `/api/workbench/gates` | 闸门待办聚合 | 各闸门待办计数：选品复核(manual_review 数)/上架确认(pending 数)/图片审核(待审核数)/素材预审(manual_review 素材数)/验证码接管(waiting_verification 数)/登录接管(waiting_login 数) |
| GET | `/api/workbench/exceptions` | 异常中心 | blocked/waiting_* 任务清单（error_code/evidence 摘要/暂停截止）；对齐旧 ExceptionCenter 语义 |
| POST | `/api/workbench/retry/{jobId}` | 人工接管后重试 | waiting_* → 断点续跑；记录操作人 |

---

## 二、展示口径（前端唯一转换层，lib/format.ts + lib/enums.ts）

> **铁律**：金额换算只在 API 层完成（内部存储分 → 对外输出元）；前端 lib 层只做元格式化（`formatYuan`），时间转换/枚举翻译在 lib 层集中函数完成（`formatDateTime` / `enumLabel`），组件内禁止自行乘除/拼接/翻译。

### 2.1 金额（API 对外元 float；内部存储分不变）

> **总控裁决（DA-001，2026-08-29）**：API 层对外金额一律「元（float）」；内部存储分不变，API 层 ÷100 换算；前端只消费元。

| 场景 | 内部存储 | API 输出 | 前端展示 |
|---|---|---|---|
| M4 price_cents/cost_cents、M5 spend/gmv/subsidy/balance、M1 C-2 sales_amount | 分 int | 元 float（÷100，round 2 位） | `¥12.90`（`formatYuan` 格式化，不换算） |
| M1 商品池（platform_price/real_cost/suggested_price） | 元 float（SourceItem 口径） | 元 float（直接透传） | 同上 |

### 2.2 时间（UTC → UTC+8）

| 约定 | 说明 |
|---|---|
| 存储/传输 | ISO8601 UTC（`2026-08-29T08:00:00Z`）；字段名 `*_at` 后缀（DA-001） |
| 展示 | 解析 ISO → Asia/Shanghai（UTC+8），格式 `YYYY-MM-DD HH:mm`（列表）/ `YYYY-MM-DD HH:mm:ss`（详情） |
| 例外 | M1 C-2 契约 generated_at 用 +08:00 显式标注——解析器按 ISO 带时区处理，不假设 Z |

### 2.3 枚举中文映射（唯一权威表）

| 枚举 | 值 → 中文 | 来源 |
|---|---|---|
| error_code | `VERIFICATION_REQUIRED`→验证码/安全验证；`AUTH_REQUIRED`→登录失效；`RATE_LIMIT`→限流；`TIMEOUT`→超时；`NO_MATCH`→无匹配；`PLATFORM_REJECT`→平台驳回；`UNEXPECTED`→未知 | 09 文档/DA-008 |
| M4 上架状态机（9 态） | `pending`→待上架；`creating`→创建中；`draft`→草稿；`platform_auditing`→平台审核中；`listed`→已上架；`rejected`→审核驳回；`retry_candidate`→待重提；`manual`→人工处理；`failed`→失败 | M4 context 第二节 |
| M1 compliance 三态 | `hard_reject`→已淘汰；`candidate`→候选；`manual_review`→待人工复核 | M1 context |
| M1 products.state | `pool`→商品池；`manual_review`→待人工复核；`rejected`→已淘汰 | M1 context |
| M2 relevance_status | `pending`→待判定；`passed`→相关放行；`failed`→不相关淘汰；`manual_review`→待人工确认目标款 | M2 context/DA-010 |
| M2 upload_status | `local`→本地；`uploading`→上传中；`uploaded`→已上传；`failed`→失败；`disabled`→拒审下架 | M2 context |
| evaluation 标签 | `exploring`→探索期；`efficient`→高效；`potential`→潜力 | M2/M3/M5 共口径 |
| **M5 中文枚举（入库即中文，原样透传展示，不做反向翻译）** | status：待托管/托管中/已暂停/不可投放/已结束；diagnosis：优秀/良好/1项待优化/N项待优化；target_type：成交ROI/净成交ROI/商品成交 | M5 context 第一节/第二节 |
| 09 前端状态机（阶段条） | 1 已选品 → 2 淘宝素材 → 3 询价(1688) → 4 生图 → 5 图片审核 → 6 待上架/已上架 → 7 托管投放 | 09 文档四节；映射逻辑见 lib/workflow.ts（重写后） |

---

## 三、旧系统组件清单（P1-7 + 同目录可复用，来源 `E:\视频号上架系统\视频号上架系统\frontend`）

> 第二波融合清单 P1-7 结论：Next.js 同栈，**搬组件不搬壳**；`lib/api.ts` 完全重写（新 API 契约），组件 props 接口保留、内部取数改造。
> 旧系统版本：Next.js 15.5.20 / React 19.0.0 / Tailwind 3.4.17 / TypeScript 5.7.2 / vitest 4.1.10。

### 3.1 P1-7 核心组件（5 个 + 2 个 lib）

| 文件 | 大小 | 导出 / Props | 用途 | 改造点 |
|---|---|---|---|---|
| `components/ImageReviewPanel.tsx` | 17.2KB | `ImageReviewPanel({product, batch, loading, error, onDecision, onApproveBatch, onRefresh, onClose})` | 图片审核面板（M3 闸门） | props 保留；取数/提交改走新 API（`/api/optimization/...`）；审核决策对接 P0-2 规则草稿闭环 |
| `components/ListingManagerView.tsx` | 25.3KB | `ListingManagerView({...})`（含上架包确认/recognize/upload） | 上架包确认（M4 闸门） | 旧 recognize/upload 流程对接新 `listing` 状态机与 confirm/retry API；快照哈希/attempt_id 语义（D1）在新 API 不适用，需评审裁剪 |
| `components/StageQueueView.tsx` | 6.5KB | `StageQueueView({...})` | 阶段队列视图（09 状态机） | 状态推导改新枚举映射（lib/workflow.ts 重写） |
| `components/ExceptionCenter.tsx` | 2.8KB | `ExceptionCenter({jobs, onRetry})` | 异常中心（waiting_*/blocked） | props 保留；对接 `/api/workbench/exceptions` + `/api/workbench/retry` |
| `components/ProviderSettings.tsx` | 3.1KB | `ProviderSettings({config, onSave})` | 提供商设置（masked 密钥显示） | 沿用 masked 模式；保存走后端；密钥永不进前端 |
| `lib/api.ts` | 9.9KB | apiGet/apiPost/apiPut + 类型定义（Product/ImageAsset/ListingPackage 等） | API 客户端 | **完全重写**对接新契约；旧类型作对照 |
| `lib/workflow.ts` | 2.7KB | deriveWorkflowStage/canQuoteProduct/canGenerateProduct | 状态机推导 | **重写**为新枚举映射（旧实现按中文文本 includes 匹配，不适用） |

### 3.2 同目录可复用（非 P1-7 点名，按需搬）

| 文件 | 大小 | 说明 | 建议 |
|---|---|---|---|
| `components/AppShell.tsx` | 3.7KB | 工作台外壳（WorkspaceView 枚举 11 视图） | 参考改造为新路由导航 |
| `components/DataViews.tsx` | 19.6KB | ProductLibraryView/ListingMemoryView/RecycleBinView | 商品库/记忆视图按需拆用 |
| `components/ReadyProductsView.tsx` | 12.4KB | 待上架商品视图 | 对接 `/api/listing/ready` |
| `components/ProductTable.tsx` | 8.8KB | 商品表格 | 对接 `/api/products` |
| `components/ProductQueue.tsx` | 4.0KB | 商品队列 | 对接 `/api/products` |
| `components/ImageReviewList.tsx` | 4.5KB | 审核列表 | 对接 `/api/optimization/batches` |
| `components/AutomaticSourcingStatus.tsx` | 6.4KB | 自动采集状态 | 对接 `/api/sourcing/status` |
| `components/ConnectionBar.tsx` | 3.4KB | 浏览器连接状态条 | 按需 |
| `components/WorkflowSteps.tsx` | 1.5KB | 阶段步骤条 | 直接搬 |

### 3.3 旧系统 API 端点参考（仅功能对照，不直接复用）

`GET`：`/products`、`/products/{id}/image-batch`、`/products/{id}/listing/package`、`/product-library`、`/product-library/stats`、`/image-review-products`、`/listing/packages`、`/listing-ready-products`、`/listing-memory`、`/promotion`、`/sourcing/status`、`/alibaba/status`、`/taobao/status`、`/wechat/status`、`/wechat/stores`、`/workflow/issues`、`/config`
`POST`：`/config`、`/image-assets/{id}/decision`、`/image-batches/{id}/approve`、`/product-batches/eliminate`、`/product-batches/retry-enrichment`、`/products/{id}/eliminate`、`/products/{id}/listing/recognize`、`/products/{id}/listing/upload`、`/products/{id}/retry-enrichment`、`/promotion-automation/{enabled}`、`/sourcing/open-browser/{platform}`
`PUT`：`/products/{id}/listing/package`

---

## 四、环境事实

| 项 | 值/约定 |
|---|---|
| Node | v24.19.0（已就绪，满足 Node 20+；11 文档实测） |
| 前端依赖基线 | next ^15.5.20、react/react-dom 19.0.0、tailwindcss ^3.4.17、typescript ^5.7.2、vitest ^4.1.10、lucide-react ^0.468.0、cva/clsx/tailwind-merge/@radix-ui/react-slot（旧系统 package.json；含 `overrides: postcss 8.5.10`） |
| 前端目录 | `frontend/`（全新初始化，不复制旧 .next/node_modules） |
| API 层 | `backend/api/`（FastAPI，Python 3.12；默认端口 8000） |
| 端口规划 | API 8000（默认，可配）；前端 dev 3000；**8787 已被 captcha-vision-gateway 占用禁用**（P-008）；8788 为 M2 下载中台 |
| npm 源/代理 | 本机网络走代理（P-009 同网络：127.0.0.1:7897）；npm 装包失败先核 npm 代理配置 |
| pytest（后端 API 层） | `python -X utf8 -m pytest tests -q --basetemp=".pytest-tmp-m6"`（P-001/P-011/P-017：独立 basetemp，禁止共用 `.pytest-tmp`；全量回归由总控执行） |
| vitest（前端） | `npm test`（vitest run）；口径转换/状态机映射单测必须覆盖 |
| 编码 | 所有文本文件 UTF-8 无 BOM（write/edit 工具）；禁止 PowerShell 重定向写中文（宪法第 11 节） |
| 数据库 | 前端零直连模块库；API 层只读消费各模块 repo（M0~M5 库 `backend/data/db/<模块>.db`，不入 git） |
| 敏感信息 | 任何 API Key/Token/Cookie/密码只走环境变量；ProviderSettings 只显示 masked；日志脱敏（foundation/security.py） |

### 环境变量注册表（只列名，不列值）

| 变量 | 用途 | 归属 |
|---|---|---|
| `M6_ADMIN_USERNAME` / `M6_ADMIN_PASSWORD_HASH` | 管理后台登录账号/密码哈希 | M6 |
| `M6_API_PORT` / `M6_API_HOST` | API 层监听地址（默认 8000/127.0.0.1） | M6 |
| `M6_API_DB_URL` | API 层审计表（可选，默认 sqlite；**会话表挂 M0 foundation，API 层不建**） | M6 |
| `M6_API_AUTH_MODE` | 鉴权模式：`fixtures`（开发期内存会话）/ `m0`（M0 auth 表就绪后） | M6 |
| `M6_CORS_ORIGINS` | CORS 白名单（逗号分隔前端 origin） | M6 |
| `NEXT_PUBLIC_API_BASE` | 前端 API 地址（仅地址，不含密钥） | M6 |
| `NEXT_PUBLIC_USE_MOCK` | 前端 mock 开关（UI 先行开发用） | M6 |
| 只读消费 | `M0_DB_URL`/`SOURCING_DB_URL`/`MATERIALS_DB_URL`/`M3_DB_URL`/`M4_DB_URL`/`M5_DB_URL` 等各模块库连接 | M0~M5（API 层只读） |

---

## 五、跨模块数据调取登记（宪法第 5 节）

- M6 API 层将只读消费 M0~M5 全部业务数据 + 提供人工闸门写操作，取数申请已登记 `_management/logs/data-audit.md` **DA-011**（申请方：M6 总工；提供方：M0~M5）。
- 契约变更流程：本文件草案 → 总控转达各模块总工会签 → 会签结果回填本节 → API 层子代理按定稿契约开发。
- 前端**不直连任何模块库**，全部经 API 层（防数据污染，宪法第 4 节）。
