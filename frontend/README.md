# M6 前端控制台（frontend/）

> 版本：v1.0（集成验收通过）｜ 栈：Next.js 15.5 + React 19 + Tailwind 3.4 + TypeScript 5.7 + Vitest 4
> 说明：本目录为「视频号微信小店全自动系统」管理控制台——全系统唯一人机界面。
> 已交付：登录闭环 + **8 个业务页**（总览/商品池/素材库/上架任务/托管看板/审核工作台/人工闸门/异常中心）
> + 展示口径层（金额元/时间 UTC+8/枚举集中翻译）+ 状态机映射 + 人工闸门操作（fixtures 模式端到端验收通过）。
> 详细交付记录见 `REPORT.md`；后端 API 层说明见 `backend/api/REPORT.md`。

---

## 一、快速开始

```bash
cd frontend
npm install          # 依赖安装（网络走代理时先核 npm config get proxy，参照 P-009）
npm run dev          # 开发服务，默认 http://localhost:3000（被占可用 -p 覆盖；避开 8787/8788）
npm test             # vitest run（口径转换/状态机映射/API 客户端/页面工具单测，197 用例）
npm run build        # 生产构建冒烟（exit 0；13 路由静态生成）
npx tsc --noEmit     # 类型检查（0 errors）
```

**登录闭环**（后端 `backend/api/` 需已启动，**默认 `http://localhost:8001`**——P-023：本地联调必须前后端统一 `localhost`（同站点），否则 SameSite=Lax 会话 cookie 在跨站（127.0.0.1 vs localhost）fetch 中不携带导致登录后弹回）：

```bash
# 后端（backend/ 目录）：账号经环境变量注入
$env:M6_ADMIN_USERNAME = "admin"
$env:M6_ADMIN_PASSWORD_HASH = "<sha256(明文密码)>"
$env:M6_CORS_ORIGINS = "http://localhost:3000"
python -X utf8 -m api --host localhost --port 8001

# 前端（frontend/ 目录）：API 指向同站 localhost
$env:NEXT_PUBLIC_API_BASE = "http://localhost:8001"
npm run dev
```

1. 打开 `http://localhost:3000/login`，输入用户名/密码；
2. 后端 `POST /api/auth/login` 校验成功 → 下发 **httpOnly + SameSite=Lax 会话 cookie**（浏览器自动携带，前端不存 token）；
3. 前端进入工作台；工作台布局挂载时 `GET /api/auth/me` 校验会话（路由守卫）；
4. 会话失效/未登录访问受保护页 → **401 全局拦截跳 /login**（`lib/api.ts` 统一处理）。

> 端口注意：8000 常被系统进程占用，默认用 8001；避开 8787/8788（P-008）。

## 二、环境变量

复制 `.env.example` 为 `.env.local` 按需修改。**任何 API Key/密码/token 不写入前端任何文件**（宪法第 4 节）。

| 变量 | 说明 | 默认 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | 后端 API 地址（**仅地址**；兼容带 `/api` 后缀写法，客户端自动归一化；`credentials: "include"` 跨域携带会话 cookie） | `http://127.0.0.1:8000` |
| `NEXT_PUBLIC_USE_MOCK` | mock 开关（保留位；当前取数直连真实 API） | `0` |

**登录账号来源（后端环境变量，前端不接触任何凭证）**：

- `M6_API_AUTH_MODE=fixtures`（开发/联调默认）：账号来自 `M6_ADMIN_USERNAME`（默认 admin）+ `M6_ADMIN_PASSWORD_HASH`（密码 SHA-256 hex，由部署方用 `hashlib.sha256(password.encode()).hexdigest()` 计算后设入进程环境，**不落任何文件**）；未设置 HASH 时后端无内置账号（登录 401）；
- `M6_API_AUTH_MODE=m0`（生产前置，依赖 M0 鉴权表落地，L1）：账号来自 M0 foundation `admin_users`/`auth_sessions` 表。

**后端启动**（backend/ 目录，本机 8000 端口被系统进程占用时可换端口，避开 8787/8788）：

```bash
cd backend
python -X utf8 -m api --port 8123   # fixtures 模式，需先设 M6_ADMIN_USERNAME/M6_ADMIN_PASSWORD_HASH
```

## 三、页面清单（8 个业务页 + 登录）

| 路由 | 页面 | 取数端点（GET） | 人工操作（POST） |
|---|---|---|---|
| `/login` | 登录页 | — | `/api/auth/login`、`/api/auth/logout` |
| `/` | 总览看板 | `/api/overview`、`/api/jobs` | `/api/kill-switch`（一键全停） |
| `/products` | 商品池 | `/api/products`、`/api/products/{id}` | 详情抽屉只读；`?state=manual_review` 直达选品复核 |
| `/assets` | 素材库 | `/api/assets`、`/api/assets/{id}`、`/api/assets/uploads` | `/api/assets/{id}/relevance-confirm`（确认目标款） |
| `/listing` | 上架任务 | `/api/listing/tasks`、`/api/listing/tasks/{id}`、`op-logs`、`/api/listing/ready` | `/api/listing/tasks/{id}/confirm`、`/retry` |
| `/ads` | 托管看板 | `/api/ads/campaigns`、`/api/ads/campaigns/{id}`、`/api/ads/account`、`/api/ads/report` | `pause/resume/end`、`/materials` |
| `/review` | 审核工作台（图片审核 + 素材预审） | `/api/optimization/batches`、`/api/optimization/batches/{id}`、`/api/assets?relevance_status=` | `/api/optimization/assets/{id}/decision`、`/api/optimization/batches/{id}/approve`、`/api/assets/{id}/relevance-confirm` |
| `/workbench` | 人工闸门工作台 | `/api/workbench/gates`、`/api/products?state=manual_review`、`/api/overview` | `/api/sourcing/gate-confirm`、`/api/kill-switch` |
| `/exceptions` | 异常中心 | `/api/workbench/exceptions` | `/api/workbench/retry/{job_id}` |

> 另有 `/settings` 占位页（v1.1 迭代）。全部业务页为客户端组件（交互需要），挂载时经 `lib/api.ts` 直连真实 API（fixtures/m0 后端均可），零假数据。

## 四、展示口径（总控裁决，前端铁律）

| 项 | 口径 | 实现 |
|---|---|---|
| 金额 | **前端只消费元（float）**，零换算（API 层已完成分→元，DA-001） | `formatYuan(12.9)` → `¥12.90`；`centsToYuan` 仅兜底保留，正常链路不调用 |
| 时间 | ISO8601 → UTC+8（Asia/Shanghai）展示，禁止手动 +8h | `formatDateTime`（Intl.DateTimeFormat，h23）→ `YYYY-MM-DD HH:mm`（详情加秒） |
| 枚举 | 集中 `lib/enums.ts` 翻译，组件不硬编码中文 | `enumLabel` / `*_LABELS` / `StatusBadge`（error_code 7 码+D10 2 码、M4 9 态、M1/M2 枚举、M5 英文三表、M3 五表等） |
| 鉴权 | httpOnly 会话 cookie（浏览器自动携带）；前端不存 token | `credentials: "include"`；401 全局拦截跳 /login |
| 密钥 | 任何 API Key/密码不写进前端代码/配置/README | `NEXT_PUBLIC_*` 只放 API 地址 |

## 五、API 客户端要点（lib/api.ts）

- 根地址：`NEXT_PUBLIC_API_BASE`（尾部 `/api` 自动归一化，路径统一 `/api/…` 开头）；
- 方法：`apiGet / apiPost / apiPut / apiDelete`，统一 `credentials: "include"` + `cache: "no-store"`；
- 错误：统一 `{code, message, detail?}` → `ApiError`；**401 → `AuthError` + 全局跳登录**（可 `setUnauthorizedHandler` 覆盖）；
- 网络失败 → `ApiError(NETWORK_ERROR)`；`204`/空体 → `undefined`；
- 类型定义对齐 `backend/api/schemas.py`（Paginated 信封、Overview、ProductSummary、AssetSummary、ListingTask（D2/D3 可空 title/error_code）、AdsCampaign（D4 元金额 / D5 英文枚举）、AdsAccount、AdsReportRow、WorkbenchGates/Exception、OptimizationBatch 等）。

## 六、测试（npm test = vitest run，197 用例 / 13 文件）

| 文件 | 覆盖 |
|---|---|
| `tests/format*.test.ts` | formatYuan（元直通/空值/整数）、centsToYuan 兜底、formatDateTime（UTC→UTC+8、+08:00、h23 午夜边界）、formatDuration/formatBytes/formatPercent |
| `tests/enums*.test.ts` | 全部映射表（error_code 7+D10 2、M4 9 态、M1/M2/M3/M5 枚举、阶段条、未知值透传） |
| `tests/workflow.test.ts` | M4 9 态→阶段 6、M5 5 态→阶段 7、阶段推进、淘汰判定 |
| `tests/api.test.ts` | mock fetch：成功解析、POST body、401→AuthError+跳转、错误码透传、网络错误、204 |
| `tests/dashboard/list/env/listing/ads/review/workbench.test.ts` | 页面工具纯函数（漏斗聚合/查询构建/状态机结构/操作可用性/审核进度/闸门计数等） |

## 七、与后端 API 对接说明

- **唯一取数通道**：前端不直连任何模块库（M0~M5 一律经 `backend/api/` 聚合，宪法第 4/5 节）；
- **fixtures 联调**：`M6_API_AUTH_MODE=fixtures` + 6 个临时 SQLite 库（`M6_*_DB_URL` 覆盖）即可起后端；v1.0 集成验收即以此模式完成 31 项 HTTP 断言 + 9 路由 200（详见 `REPORT.md` v1.0 小节）；
- **差异处理**（context 1.8 D1~D10）：jobs 过滤仅 stage/status/error_code；M4 title/error_code 可空；金额元 float；M5 英文枚举前端翻译；workbench retry 支持 blocked 三类；VALIDATION_ERROR/INVALID_STATE 前端直接展示 message；
- **已知待后端项**（详见 REPORT v1.0「移交总控清单」）：`m2-materials.db` schema 过期（素材库页真实库 500）、图片预览媒体端点、托管看板商品名 join、列表关键词/分页参数等——均未在前端规避性改动，backend/ 只读纪律保持。

## 八、环境事实

- Node v24.19.0 / npm 11.17.0（已实测）；后端 API 默认端口 8000（本机被 svchost 占用，联调用 8123）；前端 dev 3000；避开 8787/8788（P-008）；
- 网络走代理 `127.0.0.1:7897`（P-009）：npm 装包失败先核 `npm config get proxy`；
- 所有文本文件 UTF-8 无 BOM（write/edit 工具）；禁止 PowerShell 重定向写中文（宪法第 11 节）；
- 禁止运行 git（宪法第 7 节，由总控统一提交）。
