# M6 前端控制台 · 工程底座交付报告（子代理②：前端工程底座）

> 日期：2026-08-29 ｜ 角色：M6 子代理②（前端工程底座） ｜ 父代理：M6 总工程师
> 交付目录：`frontend/`（全新初始化，未复制旧系统 .next/node_modules/package-lock.json）

---

## 一、验收结果（全部实测）

| 验收项 | 命令 | 结果 |
|---|---|---|
| 依赖安装 | `npm install`（frontend/ 目录） | ✅ 396 packages，6m，exit 0（无需改代理，默认 registry 可达） |
| 单测 | `npm test`（vitest run） | ✅ **4 files / 55 passed / 0 failed**（18.37s） |
| 类型检查 | `npx tsc --noEmit` | ✅ 0 errors |
| 生产构建 | `npm run build`（next build） | ✅ 编译通过，12 路由静态生成，exit 0 |
| 开发服务 | `npm run dev`（端口 3000） | ✅ 启动成功；`/login` 200 且含「管理控制台登录」表单；`/` 200（客户端守卫在浏览器内跳转） |
| 登录闭环（真实后端） | 后端 fixtures 模式临时起 8123 端口 | ✅ login 200 + Set-Cookie（HttpOnly/SameSite=Lax）→ /me 200(username/role=admin) → 无 cookie 访问 /api/overview 401 → 错误密码 401 → logout 200 → logout 后 /me 401 |

> 说明：本机 **8000 端口被系统进程 svchost 占用**（非本 API），冒烟用 `--port 8123` 覆盖；
> 前端默认 `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000`，部署时按实际 API 端口配置即可。

## 二、工程结构（40 文件）

```
frontend/
├─ package.json           依赖基线照旧系统（next ^15.5.20 / react 19.0.0 / tailwind ^3.4.17 /
│                         typescript ^5.7.2 / vitest ^4.1.10 / lucide-react ^0.468.0 / cva / clsx /
│                         tailwind-merge / @radix-ui/react-slot；dev：autoprefixer/postcss 8.5.10/
│                         eslint ^9.17.0/eslint-config-next 15.1.3；保留 overrides: postcss 8.5.10）
├─ next.config.ts / tailwind.config.ts / postcss.config.js / tsconfig.json
├─ vitest.config.mts / eslint.config.mjs / .env.example / .gitignore / next-env.d.ts
├─ app/
│  ├─ layout.tsx / globals.css
│  ├─ login/page.tsx                 登录页（LoginForm，type=password）
│  └─ (dashboard)/
│     ├─ layout.tsx                  工作台布局：路由守卫（/api/auth/me）+ AppShell
│     ├─ page.tsx                    总览占位（任务队列/漏斗/错误码/风控 4 卡片）
│     └─ products|assets|listing|ads|workbench|exceptions|settings/page.tsx  占位页（v0.4+ 建设中）
├─ components/  AppShell / LoginForm / StatusBadge / YuanText / PagePlaceholder
├─ lib/  api.ts / auth.ts / format.ts / enums.ts / workflow.ts / cn.ts
├─ tests/  format / enums / workflow / api（vitest，node 环境）
└─ README.md / REPORT.md
```

## 三、API 客户端要点（lib/api.ts，完全重写）

- 根地址 `NEXT_PUBLIC_API_BASE`（默认 `http://127.0.0.1:8000`；尾部 `/api` 自动归一化，路径统一 `/api/…`）；
- `apiGet/apiPost/apiPut/apiDelete`：统一 `credentials: "include"`（httpOnly 会话 cookie 跨域携带）+ `cache: "no-store"`；
- 错误统一 `{code, message, detail?}` → `ApiError(code, message, status, detail)`；
- **401 → `AuthError` + 全局跳登录**：默认 `window.location.assign("/login")`（登录页自身不跳转，防刷新循环）；可 `setUnauthorizedHandler` 覆盖（供路由守卫/测试）；
- 网络失败 → `ApiError(NETWORK_ERROR)`；204/空体 → `undefined`；非 JSON 错误体兜底 UNEXPECTED；
- 类型定义对齐 `backend/api/schemas.py` + 各 router 实测：`Paginated<T>`、`CurrentUser`、`OverviewResponse`、`JobSummary`、`ProductSummary`、`AssetSummary`、`OptimizationBatchSummary`、`ListingTask`（title/error_code 可空 D2/D3）、`ListingReadyItem`（price_*_yuan）、`AdsCampaign/AdsSnapshot/AdsAccount/AdsReportRow`（金额 *_yuan、M5 英文枚举 D5）、`WorkbenchGates/WorkbenchException`（D8）。

## 四、展示口径层（lib/format.ts + lib/enums.ts，总控裁决落实）

- **金额**：`formatYuan` 只格式化元（`¥12.90` / 空值 `—`），**零换算**（DA-001）；`centsToYuan` 兜底保留（注释注明仅供未来契约兼容，正常链路不调用）；
- **时间**：`formatDateTime(iso, withSeconds?)` 用 `Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai', hourCycle:'h23'})`，UTC→UTC+8 `YYYY-MM-DD HH:mm`（详情加秒），**禁止手动 +8h**；支持带 +08:00 的 M1 generated_at 契约值；
- **枚举**：enums.ts 集中映射——error_code 7 码（DA-008）+ **D10 局部 2 码**（VALIDATION_ERROR/INVALID_STATE）、M4 9 态、M1 compliance/products.state、M2 relevance/upload/evaluation、**M5 英文枚举三表（D5）**、09 阶段条；组件经 `enumLabel`/`StatusBadge` 翻译，无硬编码中文。

## 五、状态机映射（lib/workflow.ts，重写）

- 旧实现按**中文文本 includes 匹配**已弃用；新实现输入 = 新 API 字段（products.state/compliance.state/hasQuotes/relevance_status/upload_status/生图与图片审核/listing_tasks.status/ads.campaigns.status）；
- `deriveWorkflowStage`：取最远阶段——M5 5 态 → 7 托管投放；**M4 9 态 → 6 待上架/已上架**；图片审核通过 → 6、待审/拒审 → 5、已生图 → 4、已询价 → 3、素材放行/上传 → 2、入池 → 1；
- 辅助：`isEliminated`（hard_reject/rejected/failed/disabled）、`canStartQuote`、`canStartGeneration`（对齐旧函数名，语义按新枚举）。

## 六、鉴权闭环（lib/auth.ts + app/(dashboard)/layout.tsx）

- `login`（POST /api/auth/login）/ `logout`（失效会话清 cookie）/ `getCurrentUser`（GET /api/auth/me，AuthError → null，守卫用）；
- 工作台布局挂载时 `getCurrentUser()` 守卫：未登录 → 401 全局拦截跳 /login（兜底 `router.replace`）；已登录 → 渲染 AppShell；登出后回 /login；
- 前端**不存 token/密码**；登录页密码 `type=password`；`NEXT_PUBLIC_*` 仅 API 地址（R-API-02/R-API-04/R-SEC-02）。

## 七、测试覆盖（55 passed）

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| tests/format.test.ts | 15 | formatYuan（元直通/空值/整数）、**centsToYuan(1290)=12.9 兜底 + 端到端 formatYuan(centsToYuan(1290))=¥12.90**、formatDateTime（UTC→UTC+8、+08:00、非法值、h23 午夜边界 16:00Z→次日 00:00） |
| tests/enums.test.ts | 16 | 全部映射表：error_code 7+D10 2、M4 9 态、M1/M2 枚举、M5 三表、enumLabel 通用翻译、阶段条 |
| tests/workflow.test.ts | 14 | M4 9 态→6、M5 5 态→7、阶段推进、淘汰判定、canStart* |
| tests/api.test.ts | 10 | mock fetch：成功解析（credentials/include 断言）、POST body、**401→AuthError+handler 调用**、{code,message,detail?}（409/422/500）、网络错误、204 |

> 说明：任务书测试要求「formatYuan（1290→¥12.90）」按**硬性口径 1（前端零换算，总控裁决优先）**落地为
> `centsToYuan(1290)=12.9`（兜底函数）+ `formatYuan(12.9)=¥12.90`（格式化函数）组合断言，
> formatYuan 本身对 1290 直出 `¥1290.00`（视为元，不换算）。已在 tests/format.test.ts 注释与 REPORT 中说明。

## 八、差异处理（context 1.8 D1~D10 前端相关项）

| # | 落地 |
|---|---|
| D1 | jobs 过滤仅 stage/status/error_code + 分页（类型 Paginated<JobSummary>，无 request_id） |
| D2/D3 | ListingTask.title/error_code 类型 `string \| null`；展示空值 `—`（formatYuan/StatusBadge 空值口径） |
| D4 | 金额元 float：类型 `*_yuan`/透传字段，前端零换算 |
| D5 | M5 status/diagnosis/target_type 英文原值 → lib/enums.ts 三表翻译（单测锁定） |
| D8 | 异常中心 retry 支持 blocked/waiting_verification/waiting_login 三类（类型 WorkbenchException.status 注释） |
| D10 | enums.ts 增加 VALIDATION_ERROR/INVALID_STATE 2 码映射 + ApiError 透传 message |

## 九、遗留项 / 说明

1. **登录账号**：由后端环境变量决定（fixtures 模式 `M6_ADMIN_USERNAME`/`M6_ADMIN_PASSWORD_HASH`；m0 模式 M0 鉴权表）。本会话冒烟用运行时随机账号验证闭环，**任何文件不含明文密钥**。
2. **浏览器级 401 跳转**（window.location → /login）无法在无浏览器环境实测；代码路径已由 api.test.ts 的 handler 断言覆盖，父代理浏览器冒烟时可验证。
3. **`next build` 跳过 lint**（eslint.ignoreDuringBuilds: true）：lint 非验收项，且 eslint-config-next 15.1.3 与 eslint 9 的扁平配置桥接仅为「可运行」级别；如需严格 lint 再行升级配置。
4. **`NEXT_PUBLIC_USE_MOCK` 保留位**：本版本取数直连真实 API，mock 层留 v0.4+ 页面建设（R-COL-05）。
5. **未运行任何 git 命令**；全部文件 write 工具 UTF-8 无 BOM（宪法第 7/11 节）；backend/ 未做任何修改（只读）。

---

# M6 前端控制台 · v0.4 批次1 交付报告（子代理③：页面建设 · 总览看板 + 商品队列 + 素材库）

> 日期：2026-08-29 ｜ 角色：M6 子代理③（页面建设·批次1） ｜ 父代理：M6 总工程师
> 范围：3 个占位页 → 真实业务页（总览 `/`、商品池 `/products`、素材库 `/assets`），全部接真实 API（backend/api/），零假数据。

## 一、验收结果（全部实测）

| 验收项 | 命令 | 结果 |
|---|---|---|
| 单测 | `npm test`（vitest run） | ✅ **9 files / 107 passed / 0 failed**（原 55 + 新增 52） |
| 类型检查 | `npx tsc --noEmit` | ✅ 0 errors |
| 生产构建 | `npm run build`（next build） | ✅ 12 路由编译，`/`(4.49kB) `/products`(4.98kB) `/assets`(4.35kB)，exit 0 |
| API 字段映射实测 | 后端 fixtures 模式临时起 8123 + 临时种子库 | ✅ overview/jobs/products/products{id}/assets/assets{id}/assets/uploads/kill-switch 全部 200 且字段与实现逐一吻合（见第五节） |

## 二、三个页面实现说明

### 1. 总览看板 `app/(dashboard)/page.tsx`（客户端组件）
- 取数：`GET /api/overview`（Promise.all 并行 `GET /api/jobs?page=1&page_size=10`）；
- 顶部 4 统计卡：任务总数 / 今日新增任务（today_funnel 求和）/ 执行中（running）/ 异常任务（blocked+failed+waiting_* 聚合）；
- 任务队列统计：按阶段（funnelEntries 阶段顺序 chip）+ 按状态（JOB_STATUS_LABELS 徽章×计数）；
- 今日漏斗：阶段顺序横条（宽度=count/max，合计=sumRecord）；
- 错误码分布：countEntries 降序 + ERROR_CODE_LABELS 徽章（空态「无错误任务」）；
- 风控状态：KillSwitch 一键全停（POST `/api/kill-switch`，二次确认，失败展示后端 message）+ 余额（YuanText，≤0 红）+ 账户状态（ADS_ACCOUNT_STATUS_LABELS）+ 节流级别；
- 最新任务表：stage/status 徽章 + error_code 红徽章 + retry_count + 更新时间（formatDateTime）。

### 2. 商品池 `app/(dashboard)/products/page.tsx`（客户端组件）
- 取数：`GET /api/products`（score 降序，limit/offset 分页，buildProductQuery 组装 category/compliance/min_score/max_score）；
- 筛选：类目下拉（当前页去重 distinctCategories）/ 合规三态下拉（COMPLIANCE_LABELS）/ 得分区间（可空）/ 关键词（客户端过滤 filterProductsByKeyword，页面注明命中数与 API 无关键词参数的差异）；
- 表格列：标题(截断 tooltip)/类目/平台价/建议价（YuanText）/得分(≥70 绿 ≥50 琥珀)/合规三态徽章/销量·排名/入库时间；
- 行点击 → `GET /api/products/{id}` → ProductDetailPanel 抽屉：五维打分（SCORE_DIM_ORDER 顺序，raw/weight/weighted/reasons 可解释列表，active=false 置灰）/ 询价明细 quotes 表 / 来源证据 source_evidence（脱敏直展）/ 概览（含 formatPercent 毛利率）。

### 3. 素材库 `app/(dashboard)/assets/page.tsx`（客户端组件）
- 取数：`GET /api/assets`（page/page_size 分页，buildAssetQuery 组装 asset_type/source_platform/relevance_status/upload_status/evaluation）；
- 筛选：类型（ASSET_TYPE_LABELS）/来源平台（当前页去重 distinctSourcePlatforms）/相关性门/上传状态/评估标签 五维下拉；
- 表格列：ID/类型徽章(video=blue)/来源平台/规格（formatDuration+resolution+formatBytes）/相关性门/上传状态/评估标签/热度/入库时间；
- 行点击 → `GET /api/assets/{id}` + `GET /api/assets/uploads?asset_id=` → AssetDetailPanel 抽屉：完整规格表（含 compliance_status/平台素材ID/tags_json）+ 双去重指纹（md5/phash/file_path 中段截断 hover 全显）+ 二创义务标记 derivation_note + 上传记录表（attempt/status/error_code/更新时间）。

## 三、API 字段映射（源码 backend/api/routers/*.py + schemas.py 为准，冒烟实测）

| 端点 | 页面消费字段 | 备注 |
|---|---|---|
| GET /api/overview | total_jobs / jobs_by_stage / jobs_by_status / jobs_by_error_code / today_funnel / risk{kill_switch_enabled, ad_balance_yuan, ad_account_status, ad_throttle_level} / generated_at | risk 精确类型 OverviewRisk；generated_at 已入类型 |
| GET /api/jobs | id / product_id / stage / status / error_code / retry_count / updated_at | 过滤仅 stage/status/error_code + 分页（D1） |
| POST /api/kill-switch | body {enabled} → {ok, key, enabled} | 管理员端点；操作人由后端 audit 记录 |
| GET /api/products | limit/offset 分页信封 {total, limit, offset, items}；item: id/title/category/platform_price/suggested_price/score/compliance{state,reasons}/state/sales/rank_best/board_count/supplier_count/profit_margin/created_at | **注意：分页是 limit/offset，非 page/page_size**（buildProductQuery 已按此实现） |
| GET /api/products/{id} | 追加 score_breakdown{total,dimensions{trend/profit/after_sale/supply/ad_conversion:{label,raw,weight,weighted,active,reasons}},note} / quotes{supplier_name,sku_name,unit_cost,min_order,freight,quoted_at} / source_evidence{source,board,title,price,sales,rank,collected_at} | D9 脱敏直展 |
| GET /api/assets | page/page_size 信封；item: asset_type/source_platform/source_url/source_author/md5/phash/file_path/duration/resolution/size/tags_json/heat_score/evaluation/upload_status/platform_material_id/compliance_status/relevance_status/derivation_note/created_at/updated_at | tags_json API 已解析为 dict（json_safe） |
| GET /api/assets/uploads | {total, page, page_size, items{id,asset_id,attempt,status,platform_material_id,error_code,evidence,created_at,updated_at}} | 详情抽屉可选加载 |

## 四、新增组件 / lib 工具（在既有底座上扩展，未推倒重来）

| 文件 | 说明 |
|---|---|
| `lib/dashboard.ts`（新） | sumRecord / countEntries / funnelEntries（09 阶段顺序+未知兜底）/ abnormalJobCount —— 纯函数，tests/dashboard.test.ts（12 用例） |
| `lib/products.ts`（新） | ProductFilters / buildProductQuery（limit/offset）/ filterProductsByKeyword / distinctCategories —— tests/list.test.ts 商品段 |
| `lib/assets.ts`（新） | AssetFilters / buildAssetQuery（page/page_size）/ distinctSourcePlatforms —— tests/list.test.ts 素材段 |
| `lib/env.ts`（新） | isMockMode（NEXT_PUBLIC_USE_MOCK 保留位：当前不注入 mock 数据，仅页面提示条）—— tests/env.test.ts |
| `lib/useAsyncData.ts`（新） | 轻量取数 Hook（loading/error/data/reload，加载期保留旧数据防闪烁） |
| `lib/enums.ts`（追加） | JOB_STAGE_LABELS(7) / JOB_STATUS_LABELS(8) / ADS_ACCOUNT_STATUS_LABELS / ASSET_TYPE_LABELS / ASSET_COMPLIANCE_LABELS / **UPLOAD_RECORD_STATUS_LABELS（上传台账四态，与 upload_status 不同枚举）** / SCORE_DIM_LABELS + SCORE_DIM_ORDER —— tests/enums-extra.test.ts（9 用例） |
| `lib/format.ts`（追加） | formatDuration（秒→X分Y秒）/ formatBytes（B/KB/MB/GB）/ formatPercent（比率→%） —— tests/format-extra.test.ts（12 用例） |
| `lib/api.ts`（类型细化，**函数语义零改动**） | OverviewResponse.risk → OverviewRisk（精确类型）；新增 generated_at；ProductSummary.compliance → ProductCompliance；补充 supplier_count/return_rate/ad_conversion 可选字段；AssetSummary 补充 derivation_note/file_path/tags_json 可选字段；新增 OverviewRisk/ProductCompliance/ScoreDimension/ScoreBreakdown/QuoteItem/SourceEvidenceItem/ProductDetail/AssetUploadRecord 类型 |
| `components/KillSwitch.tsx`（新） | 一键全停开关（POST /api/kill-switch，二次确认，busy/error 反馈） |
| `components/Pagination.tsx`（新） | 分页条（共N条·第p/N页 + 每页 20/50/100 + 上下页），商品池与素材库共用 |
| `components/ProductDetailPanel.tsx`（新） | 商品详情抽屉（五维/报价/证据） |
| `components/AssetDetailPanel.tsx`（新） | 素材详情抽屉（规格/指纹/二创/上传记录） |
| `components/AppShell.tsx`（微调） | 顶栏版本文案 → v0.4 |

## 五、API 冒烟实测（临时后端，不落库不落密钥）

- 起服务：`backend/` 下 `python -X utf8 -m api --port 8123`，`M6_API_AUTH_MODE=fixtures` + 运行时随机账号（SHA-256 运行时生成，**任何文件不含明文**）；
- 登录/me 200 → overview/jobs/products 字段与映射一致；products 返回 `{total,limit,offset,items}` 信封确认（limit/offset 分页）；
- 素材端点对**既有 `backend/data/db/m2-materials.db` 报 `no such column: asset_items.relevance_status`**（该库 schema 早于 relevance_status 列创建，属 M2 后端数据层问题，非前端）；改用临时库（create_all 新建 schema + 种子 1 条 AssetItem）验证 `/api/assets`、`/api/assets/1`、`/api/assets/uploads` 全部 200，字段与类型逐一吻合；
- 临时选品库种子 1 条 Product+Sku+Evidence 验证 `/api/products/1`：score_breakdown 五维（trend/profit/after_sale/supply/ad_conversion 顺序与 SCORE_DIM_ORDER 一致）、quotes、source_evidence、compliance{state}、profit_margin(0.609 比率) 全部吻合；
- POST /api/kill-switch 开启→overview.risk.kill_switch_enabled=true 回读确认，冒烟结束后已重置 false；
- 冒烟临时 DB/脚本已清理；服务器已停。

## 六、测试覆盖（107 passed = 既有 55 + 新增 52）

| 文件 | 用例 | 覆盖 |
|---|---|---|
| tests/dashboard.test.ts（新） | 12 | sumRecord / countEntries 降序 / funnelEntries 阶段顺序+未知兜底+翻译 / abnormalJobCount |
| tests/list.test.ts（新） | 17 | filterProductsByKeyword / buildProductQuery（limit/offset、分数区间、非有限值）/ distinctCategories / buildAssetQuery / distinctSourcePlatforms |
| tests/format-extra.test.ts（新） | 12 | formatDuration（秒/分/小时/非法）/ formatBytes（B/KB/MB/GB/≥100 省略小数）/ formatPercent |
| tests/enums-extra.test.ts（新） | 9 | 全部新映射表（JOB_STAGE 7/JOB_STATUS 8/账户/素材/上传台账/五维）+ 未知值透传 |
| tests/env.test.ts（新） | 2 | isMockMode（未设置/0/1/true） |
| tests/format/enums/workflow/api（既有） | 55 | 未修改，全绿 |

## 七、遗留项 / 需父代理决策

1. **`m2-materials.db` schema 过期（后端数据层问题，前端未规避）**：既有库缺 `asset_items.relevance_status` 等新列，`GET /api/assets` 对其直接 500。属 M2 模块迁移/重建库范畴（backend/ 只读纪律，前端未代改）；请 M6 总工转达 M2 总工处理（重建或迁移该库），否则素材库页在真实环境下 500。
2. **商品池「关键词」为客户端过滤**：`GET /api/products` 无关键词参数（类 D1 差异），当前按「当前页条目过滤 + 页面标注命中数」实现；如需要服务端关键词，需后端加参数（记入遗留，未动 backend）。
3. **类目/来源平台下拉为「当前页去重」**：API 无独立类目/平台枚举端点；翻页后下拉选项会随当前页变化。后续可加 `/api/products/categories`、`/api/assets/platforms` 聚合端点（后端决策）。
4. **商品列表无「来源」列**：`_product_summary` 无 source 字段（来源平台只在详情 source_evidence 中），表格以「销量/排名」替代，详情抽屉展示完整来源证据；如列表需来源列需后端在 summary 补字段。
5. **商品列表无 updated_at**：`_product_summary` 仅 created_at，表格列名为「入库时间」；如严格需要更新时间列需后端补字段。
6. **页面为客户端组件**（交互需要），已移除原占位页的 `export const metadata`（客户端组件不支持 metadata，Next 构建约束）；标题走根布局 template。
7. **非管理员操作一键全停**：前端开关始终可点，非管理员会收到后端 403 message 反馈（前端无 role 上下文注入；如需按角色禁用开关，可由父代理在布局注入 user.role）。
8. **冒烟用临时账号/密码为运行时生成，未落任何文件**；宪法第 7 节：全程未运行 git；第 11 节：全部 write/edit 工具 UTF-8 无 BOM。

---

# M6 前端控制台 · v0.5 批次2 交付报告（子代理③：页面建设 · 上架任务页 + 托管看板页）

> 日期：2026-08-29 ｜ 角色：M6 子代理③（页面建设·批次2） ｜ 父代理：M6 总工程师
> 范围：2 个占位页 → 真实业务页（上架任务 `/listing`、托管看板 `/ads`），全部接真实 API（backend/api/），零假数据。
> 冒烟验证：fixtures 模式临时后端（8123）+ 临时种子库，M4/M5 全部端点字段逐一吻合（见第五节）；冒烟环境已清理。

## 一、验收结果（全部实测）

| 验收项 | 命令 | 结果 |
|---|---|---|
| 单测 | `npm test`（vitest run） | ✅ **11 files / 150 passed / 0 failed**（原 107 + 新增 43） |
| 类型检查 | `npx tsc --noEmit` | ✅ 0 errors |
| 生产构建 | `npm run build`（next build） | ✅ 12 路由编译，`/listing`(8.31kB) `/ads`(7.66kB)，exit 0 |
| API 字段映射实测 | fixtures 模式临时起 8123 + 临时种子库 | ✅ listing/tasks|{id}|op-logs|ready、ads/campaigns|{id}|account|report、confirm/retry/pause/resume/end/materials 全部 200/409 语义与实现逐一吻合（见第五节） |

## 二、两个页面实现说明

### 1. 上架任务 `app/(dashboard)/listing/page.tsx`（客户端组件）
- 取数：`GET /api/listing/tasks`（9 态 status 过滤 + page/page_size 分页）+ 详情 `GET /api/listing/tasks/{id}` + `GET /api/listing/tasks/{id}/op-logs?limit=100` + 可选 `GET /api/listing/ready?limit=20`（「待上架快捷视图」折叠卡片，含价格区间/链接验证时间）；
- **9 态状态机可视化**：`components/ListingStateMachine.tsx`，主链 pending→creating→draft→platform_auditing→listed + 分支 rejected→retry_candidate→creating（重提回主链）/manual + failed 终态（迁移语义对齐 `backend/listing/state_machine.py` ALLOWED_TRANSITIONS）；每个状态 chip 显示当前页计数、点击即筛选；枚举中文全部走 `LISTING_STATUS_LABELS`（lib/enums.ts）；
- 列表：任务ID（title 可空 D3 兜底）/商品ID/9 态徽章/尝试次数/error_code 红徽章（可空 D2 兜底）/更新时间/操作列（详情 + 条件确认/重提按钮）；
- **人工确认入口**：POST `/api/listing/tasks/{id}/confirm`（仅 pending 显示，二次确认弹窗 + 可选备注 note，成功刷新列表与详情；409 INVALID_STATE 等后端 message 展示在弹窗内）；POST `/api/listing/tasks/{id}/retry`（仅 rejected/retry_candidate 显示，二次确认；D7 v1.0 简化语义，二次门禁由前端确认弹窗承担）；
- 详情抽屉 `components/ListingTaskDetailPanel.tsx`：概览（gate_result 脱敏 JSON / platform_spu_id / product_link 外链 / 拒审原因码 / 租约）+ **状态机轨迹**（从 op-logs `direction=transition` 的 evidence{from,to} 提取，`extractListingTrajectory`）+ SPU 映射 + 拒审记录（audit_records：reject_category/reject_reason/fix_candidate）+ 操作日志表（direction 徽章 request/response/transition + api + status_code + error_code 中文）。

### 2. 托管看板 `app/(dashboard)/ads/page.tsx`（客户端组件）
- 取数：`GET /api/ads/campaigns`（status 过滤 + 分页）+ 详情 `GET /api/ads/campaigns/{id}`（设置 + 报表快照序列）+ `GET /api/ads/account` + `GET /api/ads/report?days=7|30`；
- **表格列对齐后台**：商品（product_id + 计划 id；API 未返回商品名，见遗留 1）/目标出价（`formatTargetBid` →「成交ROI 2.40」，D5 类型翻译 + ROI 两位）/诊断徽章（M5_DIAGNOSIS_LABELS）/曝光（latest_snapshot.impressions，无快照 —）/花费/成交/补贴（latest_snapshot `*_yuan`，YuanText 零换算）/状态徽章（M5_STATUS_LABELS）/操作；
- 状态筛选（全部 + M5 5 态）+ 分页；**操作列**：详情 / 暂停（active）/ 恢复（paused）/ 结束（非 ended）/ 素材，均二次确认（`already:true` 视为成功，409/404 展示后端 message，成功刷新列表与详情）；
- **账户状态卡**：余额（YuanText）+ **低于 min_balance_yuan 红色告警**（S5，smoke 实测 58.0<100.0 触发）+ status 徽章（ADS_ACCOUNT_STATUS_LABELS）+ 节流级别 + paused_until + pause_reason；
- **报表**：近 7/30 天切换，汇总卡 4 张（总曝光/总花费/总成交/总补贴，`sumReportMetrics`）+ **轻量 div 柱状图**（`components/ReportBars.tsx`：单序列曝光图 + 花费/成交/补贴分组图，缩放基准 `barMax`，**零重型图表库**）+ 按日表格（`reportRowsAscending` 将 API 降序转升序展示）；
- **素材绑定（最小可用版）**：`components/AdsMaterialsDialog.tsx` 输入 material_ids（`parseMaterialIds` 逗号/空白分隔去重）→ POST materials → 展示后端 preferred_order 与 note（高效>潜力>探索期），成功刷新详情。

## 三、API 字段映射（源码 backend/api/routers/*.py + schemas.py 为准，冒烟实测）

| 端点 | 页面消费字段 | 备注 |
|---|---|---|
| GET /api/listing/tasks | {total,page,page_size,items}：task_id/product_id/generation_version/stage/status/title(可空 D3)/gate_result/platform_spu_id/product_link/link_verified_at/reject_reason_code/attempts/error_code(派生可空 D2)/lease_*/created_at/updated_at | status 过滤 + page/page_size |
| GET /api/listing/tasks/{id} | 列表字段 + spu{spu_id,title,category_id,status,audit_id} + audit_records[{audit_record_id,audit_id,submit_at,last_query_at,audit_status,reject_reason,reject_category,fix_candidate(脱敏),resubmit_required,evidence}] | 详情 error_code 恒 null（接口未派生）；轨迹由 op-logs 提取 |
| GET /api/listing/tasks/{id}/op-logs | {task_id,total,items{log_id,request_id,api,direction,payload_digest,status_code,error_code,platform_code,evidence(脱敏),created_at}} | direction=request/response/transition（state_machine 写 transition） |
| POST /api/listing/tasks/{id}/confirm | body {note?} → {ok,task_id,status,operator}；非 pending → 409 INVALID_STATE | 操作人后端记录 |
| POST /api/listing/tasks/{id}/retry | → {ok,task_id,status,operator}；rejected 先→retry_candidate 再→creating；非 rejected/retry_candidate → 409 | D7 v1.0 简化 |
| GET /api/listing/ready | {total,evidence,items{product_id,task_id,title,category_id,product_link,link_verified_at,price_min_yuan,price_max_yuan}} | 仅 status=listed 且链接已验证；价格已分→元 |
| GET /api/ads/campaigns | {total,page,page_size,items}：id/product_id/ad_mode/target_type(D5)/target_roi/material_ids/status(D5)/diagnosis(D5)/batch_id/created_at/updated_at/latest_snapshot(null 或 {id,recorded_at,impressions,spend_yuan,gmv_yuan,subsidy_yuan,diagnosis,status}) | **API 未返回商品名**（遗留 1） |
| GET /api/ads/campaigns/{id} | 设置字段 + snapshots（recorded_at 升序，金额元）+ snapshot_count；latest_snapshot 恒 null | 快照表含 status |
| GET /api/ads/account | {balance_yuan,status,throttle_level,paused_until,pause_reason,min_balance_yuan,updated_at} | 无状态时 status=unknown |
| POST /api/ads/campaigns/{id}/pause|resume|end | → {ok,campaign_id,status,operator}；已是目标状态 → already:true；resume ended → 409 | 操作人后端记录 |
| POST /api/ads/campaigns/{id}/materials | body {material_ids} → {ok,campaign_id,material_ids,preferred_order,note,operator} | 最小可用版 |
| GET /api/ads/report | {days,total,items{date,impressions,spend_yuan,gmv_yuan,subsidy_yuan,campaign_count}} | 日期**降序**，展示前升序 |

## 四、新增组件 / lib 工具（在既有底座上扩展，未推倒重来）

| 文件 | 说明 |
|---|---|
| `lib/listing.ts`（新） | LISTING_STATUSES_ORDERED / LISTING_MAIN_FLOW / LISTING_BRANCH_FLOW / LISTING_TERMINAL_STATUSES（9 态迁移结构，对齐 state_machine.py）/ listingStatusCounts / canConfirmTask / canRetryTask / buildListingQuery / filterTasksByKeyword / extractListingTrajectory —— tests/listing.test.ts（18 用例） |
| `lib/ads.ts`（新） | canPauseCampaign / canResumeCampaign / canEndCampaign / buildAdsQuery / buildAdsReportQuery（夹取 1..90，非法回落 7）/ formatTargetBid / sumReportMetrics / barMax / reportRowsAscending / parseMaterialIds —— tests/ads.test.ts（24 用例） |
| `lib/api.ts`（类型追加，**函数语义零改动**） | ListingSpu / ListingAuditRecord / ListingTaskDetail / ListingOpLog / ListingOpLogsResponse / ListingReadyResponse / ListingActionResult / AdsCampaignDetail / CampaignActionResult / AdsMaterialsResult / AdsReportResponse |
| `lib/enums.ts`（追加 1 表，未改既有键） | LISTING_OP_LOG_DIRECTION_LABELS（request/response/transition）—— tests/enums-extra.test.ts +1 用例 |
| `components/ConfirmDialog.tsx`（新） | 通用二次确认弹窗（标题/说明/可选输入/危险态/tone/busy/error），上架确认·重提·托管暂停/恢复/结束共用 |
| `components/ListingStateMachine.tsx`（新） | 9 态状态机可视化（主链 + 分支 + 终态，点击筛选） |
| `components/ListingTaskDetailPanel.tsx`（新） | 上架任务详情抽屉（概览/轨迹/SPU/拒审/操作日志/人工操作按钮） |
| `components/AdsCampaignDetailPanel.tsx`（新） | 托管详情抽屉（设置 + 快照序列表） |
| `components/AdsMaterialsDialog.tsx`（新） | 素材绑定弹窗（最小可用版，成功展示优选顺序） |
| `components/ReportBars.tsx`（新） | SimpleBarChart / GroupedBarChart（纯 div 柱状图，零图表库） |
| `components/AppShell.tsx`（微调） | 顶栏版本文案 → v0.5（批次2） |

## 五、API 冒烟实测（临时后端，不落库不落密钥）

- 起服务：`backend/` 下 `python -X utf8 -m api --port 8123`，`M6_API_AUTH_MODE=fixtures` + 临时账号（SHA-256 哈希运行时经 python 计算，**任何文件不含明文**）；临时库 `M6_M4_DB_URL`/`M6_M5_DB_URL`/`M6_M0_DB_URL` 指向 `%TEMP%\dsh-m6-smoke`（种子 9 条 ListingTask 覆盖 9 态 + 1 SPU + 1 拒审记录 + 3 op-logs；3 条 AdCampaign + 4 快照 + 1 账户 + 3 AdMaterial）；
- listing/tasks 9 条字段与类型逐一吻合（title 仅带 SPU 的任务非空 D3；task-07 error_code=PLATFORM_REJECT 派生 D2）；task-01 详情 spu.title/gate_result 吻合；task-06 拒审记录 reject_category/reject_reason/fix_candidate 吻合；op-logs transition/request 方向吻合；ready 返回 listed 任务（无 SPU/SKU 时 title/价格 null，前端按 — 展示）；
- **confirm**：pending→creating 返回 {ok,status,operator}；再 confirm → 409 INVALID_STATE「仅 pending 可确认入队」；**retry**：rejected→creating（经 retry_candidate）；错误状态 → 409；
- ads/campaigns 3 条：target_type/target_roi/status/diagnosis/latest_snapshot（金额元 34.5/89.0/5.0）吻合；详情 snapshots 升序 3 条、snapshot_count=3；account balance=58.0 < min_balance=100.0（告警触发）；report days=7 返回 3 日降序聚合（金额元）；
- **pause**→paused / 再 pause→already:true / resume→active / resume ended→409「已结束的托管计划不能恢复」；materials 返回 preferred_order 与 note；
- 冒烟临时 DB/脚本已清理，服务器已停（8123 端口已释放）。

## 六、测试覆盖（150 passed = 既有 107 + 新增 43）

| 文件 | 用例 | 覆盖 |
|---|---|---|
| tests/listing.test.ts（新） | 18 | 9 态结构（主链/分支/终态）/ listingStatusCounts / canConfirmTask·canRetryTask / buildListingQuery / filterTasksByKeyword（task_id/product_id/title）/ extractListingTrajectory（方向过滤 + evidence 解析 + 非法跳过） |
| tests/ads.test.ts（新） | 24 | 操作可用性三函数 / buildAdsQuery / buildAdsReportQuery（夹取与非法回落）/ formatTargetBid（类型翻译/ROI 空/未知透传）/ sumReportMetrics / barMax（空/负数/非有限）/ reportRowsAscending（升序 + 不改原数组）/ parseMaterialIds |
| tests/enums-extra.test.ts（追加） | +1 | LISTING_OP_LOG_DIRECTION_LABELS 三向翻译 + 空值兜底 |
| 既有 format/enums/workflow/api/dashboard/list/env | 107 | 未修改，全绿 |

## 七、遗留项 / 需父代理决策

1. **托管看板「商品」列无商品名**：`GET /api/ads/campaigns` 仅返回 product_id（backend m5_ads.py `_campaign_dict` 未 join 商品池），当前展示 `#product_id`；如需关联商品名需后端在列表补字段（backend/ 只读纪律，未代改）。
2. **上架任务关键词为客户端过滤**：`GET /api/listing/tasks` 无关键词参数（类 D1），当前按当前页条目过滤 + 页面标注命中数；如需服务端关键词需后端加参数。
3. **状态机条计数为当前页数据**：列表接口分页返回，计数随翻页变化；页面已标注说明（如需全量计数需后端聚合端点）。
4. **audit_status / spu.status 为平台原样状态**（listing/tables.py 注释），无固定枚举，前端直展原值（未加映射表）。
5. **素材绑定为最小可用版**：单行输入 material_ids + 展示 preferred_order/note；如需素材库选择器需前端调 `/api/assets` 做选择 UI（后续迭代）。
6. **已结束计划恢复**：前端操作列对 ended 不显示恢复按钮（与后端 409 语义一致），无需前端规避。
7. **`formatTargetBid` 对 target_roi 空值返回「—」**：smoke 中 id=3（target_type=goods, target_roi 落库默认 2.0）展示「商品成交 2.00」；如后端对 goods 类型不返回 ROI，前端按「—」处理已兼容。
8. **冒烟账号/密码为运行时临时值，未落任何文件**；宪法第 7 节：全程未运行 git；第 11 节：全部 write/edit 工具 UTF-8 无 BOM；backend/ 未做任何修改（只读）。

---

# M6 前端控制台 · v0.6 批次3 交付报告（子代理③：页面建设 · 图片审核工作台 + 素材预审）

> 日期：2026-08-29 ｜ 角色：M6 子代理③（页面建设·批次3） ｜ 父代理：M6 总工程师
> 范围：2 个业务页 → 真实可用的审核工作台（图片审核 + 素材相关性预审），全部接真实 API（backend/api/），零假数据。
> 冒烟验证：fixtures 模式临时后端（8123）+ 临时种子库，M3/M2 全部端点字段与写操作逐一吻合（19 项断言全绿，见第五节）；冒烟环境已清理。

## 一、验收结果（全部实测）

| 验收项 | 命令 | 结果 |
|---|---|---|
| 单测 | `npm test`（vitest run） | ✅ **12 files / 175 passed / 0 failed**（原 150 + 新增 25） |
| 类型检查 | `npx tsc --noEmit` | ✅ 0 errors |
| 生产构建 | `npm run build`（next build） | ✅ 13 路由编译，`/review`(7.82kB)，exit 0 |
| API 字段映射实测 | fixtures 模式临时起 8123 + 临时种子库 | ✅ optimization/batches|{id}|assets/{id}/decision|batches/{id}/approve、assets?relevance_status|assets/{id}|relevance-confirm 全部 200/400/409/422 语义与实现逐一吻合（见第五节） |

## 二、路由决策

- **新增独立路由 `app/(dashboard)/review/page.tsx`（审核工作台）**，未并入 workbench：workbench 为跨模块闸门聚合（v0.7 子代理④范围，含 `/api/workbench/gates` 待办计数 + 异常中心），图片审核/素材预审为**两大业务页级工作台**，独立路由更清晰、导航直达（AppShell 已加「审核工作台」项，v0.5→v0.6 版本文案）；workbench 占位页保持现状待 v0.7。
- 页内双 tab：**图片审核**（M3 生图批次）｜ **素材相关性预审**（M2 multi_style 目标款确认）。

## 三、两个页面实现说明

### 1. 图片审核工作台（`app/(dashboard)/review/page.tsx` Tab1 + `components/ImageReviewPanel.tsx`）
- 批次列表：`GET /api/optimization/batches`（status 筛选：全部/生成中/待审核/已审核/已通过 + page/page_size 分页）；行 = batch_id/product_id/image_type 徽章/status 徽章/image_count/创建时间；点击即载入右侧审核面板（xl 双栏，小屏纵向堆叠）；
- 批次详情：`GET /api/optimization/batches/{id}` → **主图/详情图 tab**（filterAssetsByType）+ 逐图卡片；
- **逐图审核**：`POST /api/optimization/assets/{id}/decision`——通过（approve）/驳回（reject）；**驳回必填理由**：下拉预置 6 项（旧系统 5 项语义 + 「构图/清晰度不合格」，REJECTION_REASONS）+「自定义…」自由输入，无理由时驳回按钮禁用（双保险）；成功 `detail.reload()` 刷新；
- **D6 规则草稿闭环**：decision 响应 `rule_draft_created=true` → 面板顶部 teal 提示条「本次判定已沉淀审核规则草稿（P0-2 规则草稿闭环：learning_rule_drafts）」；
- **整批通过**：`POST /api/optimization/batches/{id}/approve`（二次确认弹窗）；**幂等**——后端 `already_approved:true` 直接视为成功；成功后该批全部 approved（冒烟验证 non_approved=0）；
- 进度条：`reviewProgress`（已审 approved/rejected ÷ 总数 %）+ 头部计数（已审 X/Y、驳回 N、待审 M）；
- 错误展示：409/422 等后端 message 由面板统一展示（D10 VALIDATION_ERROR/INVALID_STATE 经 lib 透传）；
- 审核流水：每张图展示 `audit` 记录（gate_type 徽章：规则预审/素材评估/人工复核/相关性门 + result 徽章 + reviewer + 时间）；
- 图片预览：**API 仅返回本地 file_path（backend/api 无媒体服务端点）→ 占位预览**（ImageOff 图标 + 规格 宽×高 + 质检徽章 quality_ok + file_path），真实预览端点见遗留项 1。

### 2. 素材相关性预审（`components/MaterialPreReview.tsx`，双入口）
- 入口①：`/review` Tab2「素材相关性预审」——`GET /api/assets?relevance_status=manual_review`（buildPreReviewAssetQuery）列出待确认素材 + 分页；视图切换「待确认目标款 / 已放行」（passed 可选查看，buildPassedAssetQuery）；
- 入口②：`/assets` 素材库详情抽屉——`AssetDetailPanel` 新增「确认目标款」按钮（**仅 relevance_status=manual_review 显示**，isManualReviewAsset），点击弹二次确认；
- 确认操作：`POST /api/assets/{id}/relevance-confirm` `{decision:"pass"}`（body 按 router 源码：仅 decision 字段，pass/reject/manual_review 三选一）→ passed 放行；**二次确认弹窗**明确文案「确认该素材为目标款，放行进入询价/上架链；多款式素材必须人工确认目标款，禁止自动创建衍生商品（REC-迁移-03 C3）」；成功后刷新列表/详情（素材离开 manual_review 列表）；
- 幂等语义：后端 `changed:false`（同值重复回写）按成功处理；400/404 后端 message 展示；
- 素材信息展示：类型/来源平台 + file_path、规格（formatDuration/resolution/formatBytes）、评估标签、二创义务 derivation_note（truncate + hover 全显）、入库时间——全部走 lib 层格式化，组件零硬编码口径。

## 四、API 字段映射（源码 backend/api/routers/*.py + schemas.py 为准，冒烟实测）

| 端点 | 页面消费字段 | 备注 |
|---|---|---|
| GET /api/optimization/batches | {total,page,page_size,items}：batch_id/**product_id（String(64)，可能为字符串 "101"）**/image_type/plan(plan_json)/target_count/gate(gate_json)/status/image_count/created_at/updated_at | **任务书草案字段 category_key/mode/generation_round 在 API 中不存在**，实际为 image_type/plan/gate/target_count（差异 D-B3-1 见遗留项）；status 实测 generating（create_batch）/pending/reviewed/approved |
| GET /api/optimization/batches/{id} | 批次字段 + assets：image_id/image_type/variant_no/file_path/phash/width/height/quality(quality_json)/quality_ok/**review_status（仅 pending/approved/rejected，无 excluded）**/reject_reason/category_memory_key/audit[{review_id,gate_type,result,reasons,reviewer,created_at}]/created_at/updated_at | 排序 image_type,variant_no（detail 排在 main 前，前端按类型过滤展示）；audit 为空数组时正常 |
| POST /api/optimization/assets/{id}/decision | body {decision:"approve"\|"reject", reason?} → {ok,image_id,review_status,review_id,**rule_draft_created**,operator} | 非法 decision → 422 VALIDATION_ERROR（D10 冒烟实测）；D6 规则草稿闭环已对接 |
| POST /api/optimization/batches/{id}/approve | → {ok,batch_id,status,images_approved,operator}；已通过时 {ok,batch_id,status,**already_approved:true**} | 幂等，冒烟实测二次调用 already=true |
| GET /api/assets?relevance_status=manual_review | 复用既有 AssetSummary 字段（含 derivation_note/file_path/duration/resolution/size/evaluation） | 分页 page/page_size |
| POST /api/assets/{id}/relevance-confirm | **body 仅 {decision:"pass"\|"reject"\|"manual_review"}（无 reason 字段）** → {ok,asset_id,**relevance_status**,**changed**,reason?} | 非法 decision → 400（PLATFORM_REJECT 语义）；幂等 changed=false；pass→passed 放行（REC-迁移-03 C3 唯一口径） |

## 五、API 冒烟实测（临时后端，不落库不落密钥）

- 起服务：`backend/` 下 `python -X utf8 -m api --port 8123`，`M6_API_AUTH_MODE=fixtures` + 运行时随机账号（**密码仅在脚本进程内存，任何文件不含明文**）；临时库 `M6_M3_DB_URL`/`M6_MATERIALS_DB_URL`/`M6_M0_DB_URL` 指向 `frontend/.smoke-b3/`（种子：2 生图批次〔batch-001 pending：main×2+detail×1；batch-002 approved〕+ 3 素材〔manual_review/passed/pending〕）；
- 冒烟脚本为 **Python 单脚本**（`seed.py` + `smoke.py`，urllib 单条持久连接——P-019 防复发）：**19 项断言全绿**——
  - batches 列表字段与 batch 映射（status=pending/image_count=3/target_count=3/plan.strategy）；detail assets 类型感知断言（main×2+detail×1、quality_ok、宽高、reject_reason 空、audit 数组）；
  - **decision approve** → review_status=approved + **rule_draft_created=true**（D6）；**decision reject（reason 卖点不清晰）** → rejected；非法 decision → **422 VALIDATION_ERROR**；
  - **整批通过** → status=approved/images_approved=3；二次调用 → **already_approved=true**；回读全部 approved（non_approved=0）；
  - 素材预审列表（manual_review 1 条 + derivation_note/duration/resolution 吻合）→ **relevance-confirm pass → passed 放行**；回读 assets/1 relevance=passed；**幂等 changed=false**；非法 decision → 400；确认后离开 manual_review 列表（total=0）；
  - **learning_rule_drafts 闭环落库**：`[('image_generation','image_review_approve',1), ('image_generation','image_review_reject',1)]`（P0-2 幂等累计 sample_count 语义吻合）；
- 冒烟临时目录（`.smoke-b3/`）已删除、服务器已停、8123 已释放（netstat 验证）。

## 六、新增组件 / lib 工具（在既有底座上扩展，未推倒重来）

| 文件 | 说明 |
|---|---|
| `lib/review.ts`（新） | REJECTION_REASONS（6 项预置）/ buildBatchQuery / countReviewStatus / reviewProgress / canApproveBatch / filterAssetsByType / formatImageSpec / buildPreReviewAssetQuery / buildPassedAssetQuery / isManualReviewAsset / RELEVANCE_CONFIRM_DECISION_LABELS + relevanceConfirmLabel —— tests/review.test.ts（19 用例） |
| `lib/api.ts`（类型，**函数语义零改动**） | **OptimizationBatchSummary 重写**（原草案类型字段 category_key/generation_round/batch_id:number 与 API 不符且未被任何页面引用——按源码实测重定义为 batch_id:string/product_id:string\|number/image_type/plan/target_count/gate/status/image_count）；新增 OptimizationImage/OptReviewRecord/OptimizationBatchDetail/ImageDecisionResult/BatchApproveResult/RelevanceConfirmResult/CopywriteItem |
| `lib/enums.ts`（追加 5+1 表，**未改既有键**） | OPT_IMAGE_TYPE_LABELS（main/detail）/ OPT_BATCH_STATUS_LABELS（generating/pending/reviewed/approved）/ OPT_IMAGE_REVIEW_STATUS_LABELS（pending/approved/rejected）/ OPT_REVIEW_GATE_LABELS（rule/evaluate/manual/relevance）/ OPT_REVIEW_RESULT_LABELS（pass/reject/manual_review）/ OPT_QUALITY_LABELS（quality_ok 布尔 String() 翻译）—— tests/enums-extra.test.ts +6 用例 |
| `components/ImageReviewPanel.tsx`（新） | 图片审核面板（批次头/进度条/主图·详情 tab/逐图审核卡片/整批通过 ConfirmDialog/规则草稿提示/审核流水） |
| `components/MaterialPreReview.tsx`（新） | 素材相关性预审组件（待确认/已放行视图切换 + 确认目标款 ConfirmDialog） |
| `components/AssetDetailPanel.tsx`（扩展） | 新增 onConfirmRelevance/confirming props——manual_review 素材显示「确认目标款」入口条 |
| `app/(dashboard)/assets/page.tsx`（扩展） | 确认目标款流程：ConfirmDialog + POST relevance-confirm → 刷新详情+列表 |
| `app/(dashboard)/review/page.tsx`（新） | 审核工作台（双 tab + 批次列表/筛选/分页 + 面板装配） |
| `components/AppShell.tsx`（微调） | 导航加「审核工作台」+ 顶栏版本 → v0.6 |

## 七、测试覆盖（175 passed = 既有 150 + 新增 25）

| 文件 | 用例 | 覆盖 |
|---|---|---|
| tests/review.test.ts（新） | 19 | buildBatchQuery（空筛选/status/分页夹取）/ countReviewStatus（三态/未知归 pending/空）/ reviewProgress（50%/空批）/ canApproveBatch（null/待审可/已通过不可/空批）/ filterAssetsByType / formatImageSpec / 预审查询（manual_review/passed）/ isManualReviewAsset / relevanceConfirmLabel（三向+未知透传）/ REJECTION_REASONS（6 项去重非空） |
| tests/enums-extra.test.ts（追加） | +6 | M3 五表 + OPT_QUALITY_LABELS（含未知值透传与空值兜底） |
| 既有 format/enums/workflow/api/dashboard/list/env/listing/ads | 150 | 未修改，全绿 |

## 八、遗留项 / 需父代理决策

1. **图片预览为占位**：`backend/api` 无静态媒体服务端点，`OptImage.file_path` 为本地路径（M3 生图输出），前端以占位（ImageOff + 规格/质检/路径）展示；如需真实预览，需后端提供媒体服务端点（如 `GET /api/optimization/media?path=` 白名单映射）——backend/ 只读纪律，未代改（任务书提到 image_url/resolveMediaUrl，但新 API 无此字段，已按 file_path 落地）。
2. **任务书草案字段与 API 实际不一致（D-B3-1）**：批次列表草案期望 category_key/mode(manual|auto)/generation_round/待审·已审数——API 实际为 image_type/plan/gate/target_count，无 mode/category_key/generation_round；「待审/已审」由前端按详情 assets 的 review_status 计算（列表 image_count 为总数）。前端已按 API 实现，若需草案字段需后端补充（未动 backend）。
3. **M3 图片无 excluded 状态**：任务书提到 status 含 excluded，API review_status 仅 pending/approved/rejected（移出/排除语义在旧系统存在，新 M3 状态机未实现）——前端按 API 三态实现。
4. **批次状态无「待审核」专属枚举值**：batch.status 由 create_batch 写 generating、人工 approve 写 approved（另有 pending/reviewed 由业务链路写）；前端 OPT_BATCH_STATUS_LABELS 四态已覆盖并透传未知值；若需严格「待审核」口径需后端状态机统一。
5. **批次列表计数为当前页数据**：分页返回（与批次2 listing 页同口径），状态筛选/进度以详情为准。
6. **next build 多 lockfile 警告**（`E:\新建文件夹 (6)\package-lock.json` 存在导致 tracing root 推断告警，exit 0 不受影响，底座既有现象）：如需消除可在 next.config.ts 设 `outputFileTracingRoot`（未改，不在本批次范围）。
7. **已放行列表为可选实现**：素材预审「已放行」视图按 relevance_status=passed 分页展示（后端已支持），与待确认视图同组件。
8. **冒烟账号/密码为运行时临时值，未落任何文件**；P-019（Windows 回环 10048）已登记踩坑日志并落实防复发（冒烟脚本用单条持久连接）；宪法第 7 节：全程未运行 git；第 11 节：全部 write/edit 工具 UTF-8 无 BOM；backend/ 未做任何修改（只读）。

---

# M6 前端控制台 · v0.7 批次4 交付报告（子代理④：人工闸门工作台 + 异常中心）

> 日期：2026-08-29 ｜ 角色：M6 子代理④（人工闸门工作台 + 异常中心） ｜ 父代理：M6 总工程师
> 范围：2 个占位页 → 真实业务页（闸门工作台 `/workbench`、异常中心 `/exceptions`），全部接真实 API（backend/api/），零假数据。
> 冒烟验证：fixtures 模式临时后端（8123）+ 临时种子库，gates/exceptions/retry/gate-confirm 全部 200/409/404 语义与实现逐一吻合（37 断言全绿，见第五节）；冒烟环境已清理。

## 一、验收结果（全部实测）

| 验收项 | 命令 | 结果 |
|---|---|---|
| 单测 | `npm test`（vitest run） | ✅ **13 files / 197 passed / 0 failed**（原 175 + 新增 22） |
| 类型检查 | `npx tsc --noEmit` | ✅ 0 errors |
| 生产构建 | `npm run build`（next build） | ✅ 13 路由编译，`/workbench`(5.7kB) `/exceptions`(4.44kB)，exit 0 |
| API 字段映射实测 | fixtures 模式临时起 8123 + 临时种子库 | ✅ gates/exceptions/retry/gate-confirm/products?state=manual_review 全部 200/409/404 语义与实现逐一吻合（37 断言，见第五节） |

## 二、路由决策：选品复核「内联 + 跳转双通道」

- **选品复核在 workbench 页内联**（`components/SourcingReviewPanel.tsx`，闸门核心操作直达），同时闸门卡片「选品复核」也保留跳转 `/products?state=manual_review`（商品池页完整筛选/详情体验）——两种入口并存：
  - 内联：`GET /api/products?state=manual_review`（limit/offset 分页）→ 行内「确认入池」POST `/api/sourcing/gate-confirm`（二次确认，409/404 message 弹窗展示）→ 成功刷新列表 + 回调刷新闸门计数；「详情」按钮/行点击 → 复用 `ProductDetailPanel` 抽屉（五维/报价/证据）；
  - 跳转：products 页挂载时读取 `?state=` query 参数做初始合规筛选（仅客户端运行时，不影响静态生成）。
- **闸门卡片跳转直达**：为让 6 张卡片的目标链接真正落到对应筛选，在 **products（`?state=manual_review`）/ review（`?tab=image|material`）/ listing（`?status=pending`）/ exceptions（`?status=waiting_*`）** 四页各加一个挂载时 `useEffect` 读取 query 参数做初始筛选（`window.location.search` 仅客户端，静态生成不受影响——不引入 useSearchParams 以避免 Next 15 Suspense 约束）。

## 三、两个页面实现说明

### 1. 人工闸门工作台 `app/(dashboard)/workbench/page.tsx`（客户端组件）
- 取数：`GET /api/workbench/gates`（6 类待办计数 + generated_at）+ `GET /api/overview`（KillSwitch 状态）；
- **6 类闸门待办卡片**（`GATE_DEFS` 顺序 + `GateTodoCard`）：选品复核（manual_review 商品数）/上架确认（pending 任务数）/图片审核（待审图片数）/素材预审（manual_review 素材数）/验证码接管（waiting_verification 数）/登录接管（waiting_login 数）；每卡 = 计数 + 状态图标 + 统计口径 hint + 跳转链接；**count=0 置灰 +「无待办」**；
- **一键全停快捷卡**：复用 `components/KillSwitch`（总览页同款，无重复实现），状态取 overview.risk.kill_switch_enabled，卡片内展示当前开关；页头展示待办合计 + 聚合时间；
- **选品复核内联面板**（见路由决策）；确认入池成功 → `gates.reload()` 计数即时刷新。

### 2. 异常中心 `app/(dashboard)/exceptions/page.tsx`（客户端组件）
- 取数：`GET /api/workbench/exceptions`（status 筛选 chips：全部/阻塞/等待验证码/等待登录 + limit=100，buildExceptionsQuery）；
- **顶部统计**：待接管总数 + 按 error_code 分组计数卡片（`exceptionGroups`：VERIFICATION_REQUIRED→验证码/安全验证 等中文标签；error_code 为空按 status 标签兜底——blocked→阻塞；再兜底「未分类」；降序）；
- **任务清单**：任务ID/商品/阶段徽章（JOB_STAGE_LABELS）/状态徽章（JOB_STATUS_LABELS）/error_code 中文红徽章（errorCodeLabel，hover 展示 error_message）/evidence 摘要（`evidenceSummary` 脱敏截断）/可重试时间（retry_after，即暂停截止语义）/更新时间/操作；
- **人工接管**：POST `/api/workbench/retry/{id}`——「已处理，恢复执行」按钮 + 二次确认（`retryConfirmText` 按任务类型区分文案：验证码「确认验证码已通过，恢复执行」/登录「确认已重新登录，从断点续跑」/blocked「确认问题已解决，重试」）；成功刷新；409 INVALID_STATE/404 message 展示在弹窗内（D8 三类状态均支持重试）；
- 空态：「暂无异常任务，队列运行正常」。

## 四、API 字段映射（源码 backend/api/routers/*.py + schemas.py 为准，冒烟实测）

| 端点 | 页面消费字段 | 备注 |
|---|---|---|
| GET /api/workbench/gates | total / counts{sourcing_review,listing_confirm,image_review,material_pre_review,verification_takeover,login_takeover} / generated_at | 单模块库不可用不影响其余计数（后端 try/except） |
| GET /api/workbench/exceptions | {total, items{id,product_id,stage,status,error_code,error_message(≤200),retry_count,retry_after,lease_owner,lease_expires_at,evidence(脱敏 dict),created_at,updated_at}} | **任务书草案「paused_until」在 API 中不存在**——暂停截止语义由 retry_after（下次可重试时间）承担，前端列名「可重试时间」（差异见遗留项 1）；排序 updated_at 降序 |
| POST /api/workbench/retry/{job_id} | → {ok,id,status(pending),stage,error_code,operator}；非异常状态 → 409 INVALID_STATE「仅 blocked/waiting_verification/waiting_login 可人工重试」；不存在 → 404 | D8：三类状态均支持；断点续跑（retry_after 置为当前时间立即可 claim，清租约） |
| GET /api/products?state=manual_review | {total,limit,offset,items}：item 含 title/category/platform_price/score/state/compliance{state,reasons}/created_at（limit/offset 分页） | 与商品池页同构复用；确认后 total 递减 |
| POST /api/sourcing/gate-confirm | body {product_id} → {ok,product_id,title,state(pool),operator}；已在池 → 409 INVALID_STATE「已在池中」；不存在 → 404 | 对齐 CLI gate-confirm；操作人后端 audit 记录 |

## 五、API 冒烟实测（临时后端，不落库不落密钥）

- 起服务：`backend/` 下 `python -X utf8 -m api --port 8123`，`M6_API_AUTH_MODE=fixtures` + 运行时随机账号（**密码仅脚本进程内存，任何文件不含明文**）；临时库 `M6_M0_DB_URL`/`M6_SOURCING_DB_URL`/`M6_MATERIALS_DB_URL`/`M6_M3_DB_URL`/`M6_M4_DB_URL`/`M6_M5_DB_URL` 全部指向 `frontend/.smoke-b4/`（种子：M0 4 任务〔waiting_verification/waiting_login/blocked/success〕+ M1 3 商品〔manual_review×2/pool×1〕）；
- 冒烟脚本为 **Python 单脚本 + 单条 http.client 持久连接**（P-019 防复发）：**37 断言全绿**——
  - gates.counts 与种子逐一吻合（sourcing_review=2 / verification_takeover=1 / login_takeover=1 / 其余 0）、total=4、generated_at 存在；
  - products?state=manual_review 2 条、字段齐全（title/category/score/platform_price/state/compliance.reasons）、compliance.state=manual_review；
  - **gate-confirm**：manual_review→pool 成功 → 重复 409 INVALID_STATE → 不存在 404 → 已在池商品 409「已在池中」→ 确认后 manual_review 剩 1 条；
  - exceptions total=3（**success 任务正确排除**）、条目 11 字段齐全、evidence 为 dict（脱敏）、error_message ≤200；status=waiting_login 过滤命中 1 条（error_code=AUTH_REQUIRED）；
  - **retry**：waiting_verification→pending（operator=当前用户）→ 异常清单剩 2 → 重试已恢复任务 409 → 重试 success（非异常）任务 409 → 重试不存在 404 → waiting_login→pending → 异常清单剩 1（blocked）；
- 冒烟临时目录（`.smoke-b4/`）已删除、服务器已停、8123 已释放（netstat 验证）。

## 六、新增组件 / lib 工具（在既有底座上扩展，未推倒重来）

| 文件 | 说明 |
|---|---|
| `lib/workbench.ts`（新） | GATE_DEFS（6 卡定义：key/label/hint/href，顺序即展示顺序）/ gateCount / totalGateCount / exceptionGroups（error_code 分组计数，中文标签+status 兜底）/ retryConfirmText（三类文案+兜底）/ evidenceSummary（脱敏截断）/ complianceReasonsSummary（合规摘要）/ buildReviewProductsQuery（state=manual_review + limit/offset）/ buildExceptionsQuery —— tests/workbench.test.ts（22 用例） |
| `lib/api.ts`（类型，**函数语义零改动**） | WorkbenchException 按 router 实测补全（product_id:number / error_message / retry_count / retry_after / lease_owner / lease_expires_at / evidence / created_at / updated_at）；新增 WorkbenchRetryResult / GateConfirmResult |
| `components/GateTodoCard.tsx`（新） | 闸门待办卡片（计数 + 图标 + hint + 跳转；count=0 置灰「无待办」） |
| `components/SourcingReviewPanel.tsx`（新） | 选品复核内联面板（manual_review 列表 + 确认入池 ConfirmDialog + ProductDetailPanel 详情抽屉 + 分页 + onConfirmed 回调） |
| `components/ExceptionCenter.tsx`（新） | 异常清单（顶部统计分组卡 + 表格 + 人工接管 ConfirmDialog + 空态） |
| `app/(dashboard)/workbench/page.tsx`（改造） | 占位页 → 闸门聚合 + KillSwitch 快捷 + 选品复核内联 |
| `app/(dashboard)/exceptions/page.tsx`（改造） | 占位页 → 统计 + 清单 + 重试 + status 筛选 chips + `?status=` 初始筛选 |
| `products/review/listing/page.tsx`（微改） | 各加一个挂载时 useEffect 读取 query 参数做初始筛选（`?state=manual_review` / `?tab=material` / `?status=pending`），使闸门卡片跳转直达 |
| `components/AppShell.tsx`（微调） | 顶栏版本 → v0.7（批次4：闸门工作台 / 异常中心） |

## 七、测试覆盖（197 passed = 既有 175 + 新增 22）

| 文件 | 用例 | 覆盖 |
|---|---|---|
| tests/workbench.test.ts（新） | 22 | GATE_DEFS（6 类齐全/唯一/跳转目标）/ gateCount（正常/null 安全/缺失 counts）/ totalGateCount（求和/空）/ exceptionGroups（分组+中文+降序/status 兜底/未分类/空数组）/ retryConfirmText（三类+error_code 兜底+通用）/ evidenceSummary（截断/空）/ complianceReasonsSummary（合并/过滤/截断）/ buildReviewProductsQuery（分页夹取）/ buildExceptionsQuery（status+limit 夹取） |
| 既有 format/enums/workflow/api/dashboard/list/env/listing/ads/review/enums-extra | 175 | 未修改，全绿 |

## 八、遗留项 / 需父代理决策

1. **任务书草案「paused_until」字段在 /api/workbench/exceptions 中不存在**（差异登记）：实际为 `retry_after`（下次可重试时间，blocked 退避/等待场景的暂停截止语义），前端列名「可重试时间」；如严格需要 paused_until 字段需后端补充（backend/ 只读纪律，未代改）。
2. **闸门卡片跳转依赖「挂载时读取 query 参数」**：采用客户端 useEffect 读 `window.location.search`（不引入 useSearchParams，避免 Next 15 静态生成 Suspense 约束）；刷新页面后 query 参数仍生效，但页内切换筛选不会回写 URL。
3. **exceptions 列表 limit=100**（API Query 默认 100，上限 500）：异常量超 100 时仅展示最新 100 条（页脚已标注）；如需分页需后端加分页参数（未动 backend）。
4. **异常中心暂无「批量接管」**：当前逐条人工接管（对齐任务书「逐个操作」）；批量重试可后续迭代（后端 retry 为单 job 端点）。
5. **KillSwitch 状态仅展示 + 操作**：workbench 页不重复实现，复用 components/KillSwitch（总览页同款）；非管理员调用返回 403 message（与总览页同口径）。
6. **冒烟账号/密码为运行时临时值，未落任何文件**；P-019（Windows 回环 10048）已落实防复发（冒烟脚本单条 http.client 持久连接）；宪法第 7 节：全程未运行 git；第 11 节：全部 write/edit 工具 UTF-8 无 BOM；backend/ 未做任何修改（只读）。

---

# M6 前端控制台 · v1.0 集成验收报告（子代理⑤：集成验收）

> 日期：2026-08-29 ｜ 角色：M6 子代理⑤（集成验收 v0.8~v1.0） ｜ 父代理：M6 总工程师
> 范围：全量回归（本模块范围）+ fixtures 模式端到端联调 + v1.0 验收标准逐项核对 + 遗留项复核 + 文档同步。
> 纪律：禁 git / 禁明文密钥 / backend/ 只读 / 独立 basetemp `.pytest-tmp-m6` / -X utf8 / 小步落盘 / P-019 单条持久连接。

## 一、全量回归（步骤 1）✅ 双绿

| 套件 | 命令（backend/ 或 frontend/ 目录） | 结果 | 时间 |
|---|---|---|---|
| 前端 vitest 全量 | `npm test` | ✅ **13 files / 197 passed / 0 failed**（exit 0） | 1.56s |
| API 层 pytest 子集 | `python -X utf8 -m pytest tests/test_api_*.py -q --basetemp=".pytest-tmp-m6"` | ✅ **75 passed**（exit 0，1 warning 为 starlette 弃用提示，非失败） | 21.19s |

- **未运行 M0~M5 全量 pytest**（宪法：由总控统一执行）。
- vitest 13 个文件逐一列出：format 15 / enums-extra 16 / api 10 / enums 16 / list 17 / workbench 22 / review 19 / format-extra 12 / ads 24 / listing 18 / env 2 / workflow 14 / dashboard 12 = **197**。
- pytest 75 用例覆盖：auth / system / m1_sourcing / m2_materials / m3_optimization / m4_listing / m5_ads / workbench 8 个测试文件（与 v0.2 基线一致，零回归）。

## 二、端到端联调（步骤 2）✅ 40 项断言全绿

- **方式**：Python 冒烟脚本走 HTTP 层（fixtures 模式后端 + 前端 `next dev`），**单条 http.client 持久连接**（P-019 防 WinError 10048）；后端 `python -X utf8 -m api --port 8123`（本机 8000 被 svchost 占用，P-008 同型）；前端 `next dev -p 3000`（NEXT_PUBLIC_API_BASE=http://127.0.0.1:8123）。
- **临时环境**：`frontend/.smoke-v10/dbs/` 6 个 SQLite 种子库（复用 `backend/tests/api_testing.py` 造数工具 + 增量种子，零外网零真实库）；账号密码**运行时随机生成**（SHA-256 hex 仅进程环境变量，任何文件不含明文，P-004）。
- **种子口径**：M1 manual_review×2 + pool×2（gate-confirm 目标）；M2 素材×3（manual_review/passed/pending）；M3 生图批次 batch-001（main×2 待审图 + 文案×2）；M4 上架任务×4（pending/listed/rejected/retry_candidate）；M5 托管×2（active/paused + 快照×2 + 账户 balance=500.0 + 素材 mat-001）；M0 任务×4（waiting_verification/waiting_login/blocked/success）。
- **API 层冒烟（31 断言全绿，exit 0）**——关键链路逐条：

| # | 断言 | 结果 |
|---|---|---|
| 01-03 | 登录 200 + Set-Cookie(m6_session) + /api/auth/me 200(username/role=admin) | ✅ |
| 04-05 | 未登录访问业务端点/写操作 → 401（鉴权闭环回归） | ✅ |
| 06 | /api/workbench/gates 计数与种子逐一吻合（sourcing_review=2/listing_confirm=1/image_review=2/material_pre_review=1/verification=1/login=1，total=8） | ✅ |
| 07-10 | 选品复核：manual_review total=2 → gate-confirm 200 state=pool → total 减为 1 → 重复 409 INVALID_STATE「已在池中」 | ✅ |
| 11-14 | 上架确认：pending ≥1 → confirm 200 status=creating → 重复 409 INVALID_STATE → pending 减为 0 | ✅ |
| 15-18 | 图片审核：批次含待审图 → decision approve 200 review_status=approved + rule_draft_created=true（D6 规则草稿闭环）→ 回读 approved | ✅ |
| 19-21 | 素材预审：manual_review ≥1 → relevance-confirm pass 200 relevance_status=passed → 减为 0 | ✅ |
| 22-25 | 异常接管：waiting_verification ≥1 → retry 200 status=pending（operator=admin）→ 减为 0 → 重复 retry 409 | ✅ |
| 26-30 | 一键全停：overview 初始 false → kill-switch true 200 → overview 回读 true → 重置 false → 回读 false | ✅ |
| 31 | 操作后 gates 计数联动（sourcing=1/listing=0/image=1/material=0/verification=0/login=1） | ✅ |

- **前端路由冒烟（9/9 通过）**：`next dev` 起服务后 HTTP GET——`/`、`/products`、`/assets`、`/listing`、`/ads`、`/review`、`/workbench`、`/exceptions` 全部 **200 + 工作台壳渲染**（含路由守卫「正在验证登录状态」标记，无 500/白屏/真 404）；`/login` 200 + 登录表单（含「管理控制台」）；未知路由基线返回真 404（证明标记方法有效）。数据渲染由既有 197 单测 + build + 上述 API 字段断言保障。
- **联调观察**：① 首轮冒烟曾出现 1 次「retry 后 exceptions 回读」连接超时（http.client 10s 超时），复跑及后续多轮未复现（服务端日志显示该链路单请求 2-12ms，pytest 75 用例同链路全绿）——判定为瞬态环境抖动（SQLite/连接时序），**非代码缺陷**，已在缺陷修复节登记；② next dev 与 next build 共用 `.next` 目录：build 后直接 dev 会命中陈旧 manifest（全路由返 200 壳但内容为 not-found 页）——**dev 前需删 `.next`**（已在 README 快速开始备注）。
- **清理**：冒烟临时目录 `.smoke-v10/`（种子库/脚本/日志）已删除；后端/前端服务已停；8123/8125/3000 端口 netstat 验证已释放（P-019 防复发：脚本全程单条持久连接）。

## 三、v1.0 验收标准逐项核对

| # | 验收标准 | 结果 | 证据 |
|---|---|---|---|
| 1 | **控制台可启动**：`npm run dev` 可启动；`npm run build` exit 0 | ✅ | dev 实测 9 路由 200；`npm run build` **exit 0**（13 路由静态生成，2.8s compile）；`npx tsc --noEmit` 0 errors |
| 2 | **各页面数据可展示**：8 个业务页全部接真实 API（fixtures 模式后端），无白屏/无 500/无字段错位 | ✅ | 8 页全部 200 + 壳渲染；页面消费的全部 API 端点（overview/jobs/products/assets/uploads/listing/ready/ads/account/report/optimization/workbench）在 31 断言中逐一 200 且字段与类型吻合（v0.4~v0.7 各批次冒烟亦逐一验证） |
| 3 | **人工闸门可操作**：选品复核/上架确认/图片审核/素材预审/异常接管/一键全停 6 类闭环 + 状态回读 | ✅ | 见上表 07-31：每类操作成功 → 列表计数递减/状态机推进/overview 回读正确（409 幂等语义同时验证） |
| 4 | **回归全绿**：`npm test` 全绿 + pytest 子集全绿 | ✅ | vitest **197 passed**（13 文件）；`python -X utf8 -m pytest tests/test_api_*.py -q --basetemp=".pytest-tmp-m6"` **75 passed**（exit 0） |

## 四、缺陷修复列表

联调发现的缺陷（均为前端冒烟脚本自身问题，前端业务代码零缺陷——6 类闸门操作首轮即按契约通过）：

| # | 缺陷 | 定位 | 修复 |
|---|---|---|---|
| F1 | 冒烟脚本 `seed_extra_m0` 误用 `enqueue()` 返回值当 job id（实为 WorkflowJob 对象）→ SQL 绑定类型错误 | 冒烟脚本（非业务代码） | 改 `session.get(WorkflowJob, job.id)`；重跑全绿 |
| F2 | 冒烟脚本重复 confirm 未带请求体 → 后端 422 VALIDATION_ERROR（**API 契约：confirm 请求体必填**，前端页面实现已正确传 `{}`+note） | 冒烟脚本（非业务代码） | 补 `{}` 请求体；重跑 409 INVALID_STATE 符合预期 |
| F3 | 冒烟脚本逐请求新建 socket → WinError 10048（P-019 自身坑） | 冒烟脚本 | 改单条 http.client 持久连接 |
| F4 | 路由冒烟「not-found」字符串误判：Next.js App Router 每个页面 RSC flight payload 均内嵌客户端 404 兜底组件定义（HTTPAccessErrorFallback），非渲染 404 | 冒烟脚本标记逻辑 | 改以「200 + 工作台壳标记（正在验证登录状态）/登录表单标记 + 未知路由 404 基线」判定 |
| F5 | next build 后直接 next dev → 陈旧 .next manifest 致全路由返回 not-found 页 | 运行方式（非代码） | dev 前删除 `.next`（README 已备注）；本机验证有效 |

> 业务代码缺陷：**0**（未发现需改前端组件的 bug）。API 层观察项 1 条（瞬态超时未复现）见第五节移交清单。

## 五、遗留项复核（各批次 REPORT 遗留逐条标注）

### frontend/REPORT.md 既有遗留项

| 来源 | 遗留项 | v1.0 状态 |
|---|---|---|
| v0.3-1 | 登录账号由后端环境变量决定 | ✅ 已解决（README 二节已说明 fixtures/m0 两模式；联调实测） |
| v0.3-2 | 浏览器级 401 跳转无浏览器环境实测 | 🔵 待浏览器冒烟（代码路径单测覆盖；Playwright 非强制，v1.1 可补） |
| v0.3-3 | next build 跳过 lint | 🔵 保持（非验收项，决策已记录） |
| v0.3-4 | NEXT_PUBLIC_USE_MOCK 保留位 | 🔵 保持（本版本零 mock，直连真实 API） |
| v0.4-1 | **m2-materials.db schema 过期**（缺 relevance_status 等新列 → /api/assets 真实库 500） | 🔴 **待 M2 处理**（已上报；联调用临时库验证通过，真实库仍受影响——移交总控） |
| v0.4-2 | 商品池关键词为客户端过滤（API 无关键词参数） | 🔵 待后端加参数（低优先级） |
| v0.4-3 | 类目/来源平台下拉为当前页去重（无聚合端点） | 🔵 待后端加 `/api/products/categories`、`/api/assets/platforms`（低优先级） |
| v0.4-4 | 商品列表无「来源」列（summary 无 source 字段） | 🔵 待后端补字段（低优先级） |
| v0.4-5 | 商品列表无 updated_at | 🔵 待后端补字段（低优先级） |
| v0.4-6 | 页面为客户端组件（无 metadata） | ✅ 已解决（设计决策） |
| v0.4-7 | 非管理员一键全停：前端无 role 上下文 | 🔵 保持（非管理员收到后端 403 message；可后续注入 user.role） |
| v0.5-1 | 托管看板商品列无商品名（API 未 join 商品池） | 🔴 **待后端**（v1.0 联调确认仍为 #product_id——移交总控） |
| v0.5-2 | 上架任务关键词为客户端过滤 | 🔵 待后端加参数（低优先级，同 v0.4-2） |
| v0.5-3 | 状态机条计数为当前页数据 | 🔵 保持（页面已标注） |
| v0.5-4 | audit_status/spu.status 平台原样状态 | 🔵 保持（前端直展原值） |
| v0.5-5 | 素材绑定为最小可用版（单行 material_ids 输入） | 🔵 保持（后续可做素材库选择器） |
| v0.5-6 | 已结束计划恢复 | ✅ 已解决（前端不显示恢复按钮，与后端 409 语义一致） |
| v0.5-7 | formatTargetBid 空 target_roi → — | ✅ 已解决（已兼容） |
| v0.6-1 | **图片预览为占位**（backend/api 无媒体服务端点） | 🔴 **待后端**（file_path 本地路径，需媒体服务端点白名单映射——移交总控） |
| v0.6-2 | 批次列表草案字段（category_key/mode/generation_round）与 API 不一致 | ✅ 已解决（前端按 API 实现） |
| v0.6-3 | M3 图片无 excluded 状态 | ✅ 已解决（前端按 pending/approved/rejected 三态） |
| v0.6-4 | 批次状态无「待审核」专属枚举 | ✅ 已解决（前端四态覆盖 + 未知透传） |
| v0.6-5 | 批次列表计数为当前页数据 | 🔵 保持（分页口径，同 v0.5-3） |
| v0.6-6 | next build 多 lockfile 警告 | 🔵 保持（exit 0 不受影响；v1.0 build 复现该警告确认无害；可设 outputFileTracingRoot 消除） |
| v0.6-7 | 已放行列表可选实现 | ✅ 已实现 |
| v0.7-1 | 草案 paused_until 字段不存在（实际 retry_after） | ✅ 已解决（前端按 API 实现，列名「可重试时间」） |
| v0.7-2 | 闸门卡片跳转依赖挂载时读 query 参数 | 🔵 保持（设计决策） |
| v0.7-3 | exceptions 列表 limit=100（无分页） | 🔵 待后端加分页参数（低优先级） |
| v0.7-4 | 异常中心暂无批量接管 | 🔵 待后端批量端点（后续迭代） |
| v0.7-5 | KillSwitch 仅展示+操作 | 🔵 保持 |

### backend/api/REPORT.md 遗留项（L1~L9，前端侧立场）

| # | 项 | v1.0 状态 |
|---|---|---|
| L1 | M0 auth 表契约（admin_users/auth_sessions） | 🔴 待 M0 落地会签（m0 鉴权模式生产前置） |
| L2 | requirements.txt 补依赖（fastapi/uvicorn/httpx） | 🔴 待总控并入 |
| L3 | M5 枚举文档漂移（context 称中文入库，实际英文） | 🔴 待 M5 同步文档（前端已按英文枚举翻译） |
| L4 | 错误码扩展 VALIDATION_ERROR/INVALID_STATE | ✅ 前端侧已解决（enums.ts 映射 + message 直展） |
| L5 | M4 retry 二次门禁（ListingGate 全量校验） | 🔵 v1.1 增量（当前人工确认即重提） |
| L6 | m0 模式生产启用 | 🔴 依赖 L1 |
| L7 | /api/health 免登录 | 🔵 保持（无业务数据） |
| L8 | DA-011 契约会签回传 | 🔴 待总控转达 M0~M5 回传 |
| L9 | pytest.ini 共享配置 | 🔵 待总控评估 |

## 六、移交总控清单

| 优先级 | 项 | 责任方 | 说明 |
|---|---|---|---|
| 🔴 高 | **M2 materials.db schema 过期**（asset_items 缺 relevance_status 等新列） | M2 总工 | 素材库页/素材预审在真实库下 500；联调已用临时库证明前端链路正确 |
| 🔴 高 | M0 auth 表契约落地 + m0 鉴权模式验证（L1/L6） | M0 总工 | 生产鉴权前置 |
| 🟡 中 | 图片预览媒体服务端点（v0.6-1） | 后端 API 层 | 审核工作台真实预览；当前占位 |
| 🟡 中 | 托管看板商品名 join（v0.5-1） | M5/API 层 | 列表商品列展示 #product_id |
| 🟡 中 | requirements.txt 补依赖（L2） | 总控 | fastapi/uvicorn/httpx |
| 🟡 中 | M5 枚举文档漂移同步（L3） | M5 总工 | context README 与代码对齐 |
| 🟡 中 | DA-011 契约会签回传（L8） | 总控转达 | D1~D10 各模块回填 |
| 🔵 低 | 列表关键词/分页/聚合端点/updated_at/source 字段（v0.4-2~5、v0.5-2、v0.7-3） | 后端 API 层 | 前端已客户端过滤兜底，非阻塞 |
| 🔵 低 | 异常中心批量接管（v0.7-4）、素材库选择器（v0.5-5）、浏览器级 401 跳转实测（v0.3-2） | M6 v1.1 | 后续迭代 |
| ℹ️ 观察 | 联调 1 次瞬态连接超时（retry 后 exceptions 回读） | — | 未复现，pytest 同链路 75 全绿；若再现按 P-001/P-011 流程排查环境 |

## 七、文档同步说明（步骤 4）

- `frontend/README.md` **已重写为 v1.0 版**：版本头 v1.0；快速开始（dev/test/build/tsc）；环境变量表（NEXT_PUBLIC_API_BASE / NEXT_PUBLIC_USE_MOCK）与**登录账号来源**（fixtures 的 M6_ADMIN_USERNAME/M6_ADMIN_PASSWORD_HASH 计算方式、m0 模式说明，明文不落文件）；**9 路由页面清单表**（取数端点 + 人工操作端点）；展示口径/API 客户端/测试覆盖/与后端对接说明；环境事实（本机 8000 被占联调用 8123、**next build 后需删 .next 再 dev**、P-008/P-009/P-017）。
- `frontend/REPORT.md` **追加本 v1.0 小节**（步骤 1~7 全量记录）。
- `_management/logs/agent-activity.md` 追加子代理⑤台账。

## 八、纪律核验

- ✅ 未运行任何 git 命令（宪法第 7 节）；backend/ 零修改（只读，仅经 HTTP 调用；联调发现的 API 层观察项已登记移交，未代改）；
- ✅ 无明文密钥（联调账号密码运行时随机生成，SHA-256 hex 仅进程环境变量；任何 md/脚本/日志无明文）；
- ✅ 全部文件 write/edit 工具 UTF-8 无 BOM（宪法第 11 节）；pytest 独立 basetemp `.pytest-tmp-m6` + `-X utf8`（P-001/P-011/P-017）；
- ✅ 未跑 M0~M5 全量 pytest（由总控执行）；冒烟临时环境（库/脚本/日志/服务/端口）已全部清理。
