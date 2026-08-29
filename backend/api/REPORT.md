# M6 后端 API 层 · 交付报告（子代理①）

> 日期：2026-08-29 ｜ 角色：M6 子代理①（后端 API 层开发） ｜ 父代理：M6 总工程师
> 验收命令（已实测全绿）：`python -X utf8 -m pytest tests/test_api_*.py -q --basetemp=".pytest-tmp-m6"`（backend/ 目录）
> 结果：**75 passed**（7 个测试文件 + 1 个共享测试工具模块）

---

## 一、交付物清单

| 文件 | 说明 |
|---|---|
| `backend/api/__init__.py` | 包说明与版本 |
| `backend/api/app.py` | FastAPI 应用工厂：CORS 白名单、请求日志、**鉴权守卫中间件**、统一错误处理器、41 路径注册 |
| `backend/api/config.py` | `M6_*` pydantic-settings（含各模块库连接覆盖 `M6_*_DB_URL`） |
| `backend/api/errors.py` | 统一错误 `{code,message,detail?}` + 金额分→元 + 时间 ISO8601 UTC + 递归脱敏 |
| `backend/api/auth.py` | `AuthStore` 抽象 + `FixturesAuthStore`（内存会话）/ `M0AuthStore`（读 M0 auth 表）+ 密码哈希/常数时间比较 |
| `backend/api/services.py` | `Services` 聚合容器：M0~M5 六库惰性构造 + kill-switch（S8）+ 操作审计（写 M0 logs，脱敏） |
| `backend/api/deps.py` | 会话依赖 / 管理员守卫 / 分页依赖 |
| `backend/api/schemas.py` | pydantic 请求/响应模型（金额字段一律 float 元） |
| `backend/api/routers/` | auth / system / m1_sourcing / m2_materials / m3_optimization / m4_listing / m5_ads / workbench（8 个） |
| `backend/api/__main__.py` | `python -m api` 启动入口（uvicorn） |
| `backend/api/_pytest_glob.py` + `backend/pytest.ini` | pytest 插件：展开命令行 glob 参数（Windows 无 shell 展开，保证验收命令原样可用） |
| `backend/tests/test_api_auth.py` 等 7 个 + `backend/tests/api_testing.py` | 测试套件（fixtures 模式：6 个 tmp SQLite 库 + 运行时随机账号，零外网零真实库） |
| `backend/api/REPORT.md` | 本报告 |

启动方式（backend/ 目录）：`python -X utf8 -m api` 或 `uvicorn api.app:app --port 8000`（默认 127.0.0.1:8000；端口被占可 `--port` 覆盖，避开 8787/8788，P-008）。

---

## 二、接口清单（实际实现 vs 草案差异）

### 2.1 实现全量（41 路径 = 草案 40+ 端点 + /api/health）

| 域 | 方法/路径 | 状态 |
|---|---|---|
| 鉴权 | POST /api/auth/login、POST /api/auth/logout、GET /api/auth/me | ✅ 按草案 |
| 系统 | GET /api/overview、GET /api/jobs、GET /api/jobs/{id}、POST /api/kill-switch、GET/PUT /api/app-config/{key}、GET /api/logs | ✅ 按草案 |
| M1 | GET /api/products、GET /api/products/{id}、GET /api/sourcing/status、POST /api/sourcing/gate-confirm、GET /api/sourcing/report | ✅ 按草案 |
| M2 | GET /api/assets、GET /api/assets/{id}、POST /api/assets/{id}/relevance-confirm、GET /api/assets/uploads | ✅ 按草案 |
| M3 | GET /api/optimization/batches、GET /api/optimization/batches/{id}、POST /api/optimization/assets/{id}/decision、POST /api/optimization/batches/{id}/approve、GET /api/optimization/copywrites | ✅ 按草案（任务书标题写「M3 4」实列 5 项，按 5 项实现） |
| M4 | GET /api/listing/tasks、GET /api/listing/tasks/{id}、GET /api/listing/tasks/{id}/op-logs、POST /api/listing/tasks/{id}/confirm、POST /api/listing/tasks/{id}/retry、GET /api/listing/ready | ✅ 按草案 |
| M5 | GET /api/ads/campaigns、GET /api/ads/campaigns/{id}、GET /api/ads/account、POST pause/resume/end、POST /api/ads/campaigns/{id}/materials、GET /api/ads/report | ✅ 按草案（8 端点） |
| 工作台 | GET /api/workbench/gates、GET /api/workbench/exceptions、POST /api/workbench/retry/{jobId} | ✅ 按草案 |
| 健康 | GET /api/health | 追加（免登录；仅服务/版本/鉴权模式，无业务数据） |

### 2.2 差异登记（字段名以各模块 repo/数据字典为权威，草案表述不一致处以模块方为准）

| # | 草案表述 | 实际实现 | 说明 |
|---|---|---|---|
| D1 | jobs 过滤含 `request_id` | `workflow_jobs` 无 request_id 列（M4 context 的 task_id=request_id 或 job_id 属 M4 域）；过滤仅 stage/status/error_code + 分页；按 job id 详情查 | 待 M0 会签：若需 request_id 过滤由 M0 加列 |
| D2 | M4 tasks 列表列含 `error_code` | `listing_tasks` 无 error_code 列；实现取该任务**最新一条 op_log 的 error_code**（近似语义，无记录为 null） | 差异入 REPORT，前端按可空处理 |
| D3 | M4 tasks 列表列含 `title` | `listing_tasks` 无 title；实现关联 `listing_spus` 最早创建 SPU 的 title（无 SPU 为 null） | 同上 |
| D4 | M5 campaigns「金额分 int」 | 总控裁决 DA-001 优先：API 对外一律**元 float**（spend/gmv/subsidy/balance ÷100）；M5 context README 2.1 与契约表为「分 int」属旧口径 | 已按裁决实现；草案该列已过时 |
| D5 | M5 status/diagnosis「中文枚举入库」 | **实际 repo 存英文枚举**（status: pending/active/paused/not_eligible/ended；diagnosis: excellent/good/optimize_1/optimize_n；target_type: roi/net_roi/goods——见 ads/tables.py、ads/report.py 归一化函数）。API 按「枚举原样透传」输出英文原值 | M5 context README 与代码漂移，以前端 lib/enums.ts 翻译为终；建议 M5 同步文档 |
| D6 | M3 decision「对接 M3 review gate」 | 已对接：写 opt_review_records（gate_type=manual）+ opt_images.review_status + **P0-2 规则草稿闭环**（m0_queue.create_rule_draft，learning_rule_drafts） | 与草案一致，同事务落库防 SQLite 写锁 |
| D7 | M4 retry「二次门禁后重提」 | v1.0 简化：rejected→retry_candidate→creating 或 retry_candidate→creating（状态机合法迁移组合）；**真实 ListingGate 全量校验未接入**（需构造 ListingCandidate 全字段，属 v1.1 增量） | 遗留项 |
| D8 | workbench retry 仅 waiting_* | 实现允许 waiting_verification/waiting_login/**blocked** 三类人工接管状态重试（语义更完整） | 差异登记 |
| D9 | M1 商品详情 quotes/evidence | repo 层无现成查询，直接 ORM 查询 sku/product_source_evidence 表输出；raw_json 递归脱敏 | 无差异，实现方式说明 |
| D10 | 错误码 | 业务错误复用 DA-008 七码；另加 **2 个 API 层局部码**（非业务码，前端直接展示 message）：`VALIDATION_ERROR`(422)/`INVALID_STATE`(409) | 待会签（前端 enums 需加 2 条映射或直接展示 message） |

---

## 三、鉴权实现方式

1. **AuthStore 抽象**（`backend/api/auth.py`）：`verify_user / create_session / get_session_user / delete_session` 四方法接口。
2. **双模式**（`M6_API_AUTH_MODE`）：
   - `fixtures`（默认）：`FixturesAuthStore` 内存会话 + 测试账号。账号仅来自环境变量 `M6_ADMIN_USERNAME`（默认 admin）/ `M6_ADMIN_PASSWORD_HASH`（SHA-256 hex）；未设置 HASH 时无内置账号（登录返回 401 提示），测试经 `seed_user_plain` 运行时造号——**任何文件不含明文密码**（P-004）。内置 admin 角色。
   - `m0`：`M0AuthStore` 读 M0 foundation auth 表（契约表名 `admin_users` / `auth_sessions`，见遗留项 L1）；**表未落地 → 启动即抛 `AuthStoreConfigError`（明确错误提示，不静默降级）**。
3. **会话**：登录成功发 **httpOnly + SameSite=Lax** cookie（`M6_SESSION_COOKIE_NAME`，默认 m6_session；TTL `M6_SESSION_TTL_HOURS`=12h）；登出失效会话并清 cookie。
4. **守卫**：中间件级兜底 + 路由依赖双保险——除 `POST /api/auth/login` 与 `/api/health`（及 docs/openapi）外**全部端点需登录**（401）；kill-switch / app-config 写接口**仅管理员**（403）；写操作统一 `services.audit` 记操作人（写 M0 logs 表，脱敏）。
5. **CORS**：`M6_CORS_ORIGINS` 逗号分隔白名单，默认空=仅本机；`allow_credentials=True` 精确匹配（R-API-02 / R-SEC-04）。
6. **R-API-01 满足**：鉴权只在 HTTP 路由层；各模块 CLI/repo 内部调用不受影响（零修改模块源码）。

---

## 四、金额换算说明（总控裁决 DA-001）

- **API 对外一律「元（float）」**，内部存储分不变，API 层 ÷100（round 2 位）换算；**禁止把分输出给前端**。
- 换算点：
  - M4：`listing_skus.price_cents/cost_cents` → 候选池 `price_min_yuan/price_max_yuan`（1290 分 → 12.9 元，测试断言）；
  - M5：`spend/gmv/platform_subsidy/balance` → `*_yuan`（1290 分 → 12.9 元；50000 分 → 500.0 元；报表按日聚合 1290+990 分 → 22.8 元，测试断言）；
  - M1：商品池元字段（platform_price/real_cost/suggested_price/profit_margin、quotes.unit_cost）**直接透传**；`ad_conversion.sales_amount`（M5 C-2 契约单位分）→ `sales_amount_yuan`（128000 分 → 1280.0 元，测试断言）。
- 时间：一律 ISO8601 UTC（`...Z`，字段名 `*_at`）；M1 `generated_at` 等带 +08:00 契约值由前端解析器按 ISO 带时区处理（展示口径第 2.2 节）。
- 枚举：原样透传不翻译（error_code/M4 9 态/M1 compliance/state/M2 relevance/evaluation 英文枚举；M5 status/diagnosis 实际为英文枚举原值——见 D5）；翻译只在前端 lib/enums.ts。

---

## 五、测试说明

- 运行命令（**已实测 75 passed**）：`python -X utf8 -m pytest tests/test_api_*.py -q --basetemp=".pytest-tmp-m6"`（backend/ 目录；P-001/P-011 独立 basetemp、P-017 -X utf8）。
- fixtures 模式：6 个 tmp SQLite 库（m0/m1/m2/m3/m4/m5），零外网、零真实登录态、零真实平台调用；**不触碰 backend/data/db/*.db**；账号密码运行时随机生成。
- 覆盖矩阵（75 用例）：
  - 鉴权闭环：登录成功 200+Set-Cookie(HttpOnly/SameSite=Lax)、错误密码 401、未登录业务接口 401、登出失效、422 错误格式、m0 模式表未落地明确报错；
  - 系统：overview 聚合、jobs 过滤/分页/详情脱敏、kill-switch 管理员 403/200、app-config 管理员写、logs 脱敏；
  - M1：商品池 score 排序/过滤、详情 quotes+evidence、ad_conversion 分→元、gate-confirm 成功/409/401/404、周报；
  - M2：素材列表过滤/分页、详情 URL 脱敏、relevance-confirm 幂等/404/非法 decision、上传记录；
  - M3：批次列表/详情、decision approve（含规则草稿落库）/reject/非法值、整批通过幂等、文案列表；
  - M4：任务列表（title/error_code 派生）、详情含 spu/audit、op-logs、confirm（pending→creating + 409）、retry（retry_candidate/rejected 两路 + 409）、ready 分→元（1290→12.9）；
  - M5：看板最新快照金额换算、详情快照序列、账户余额换算、pause/resume/end、素材绑定、报表按日聚合换算；
  - 工作台：闸门计数、异常清单、retry 断点续跑 + 409/404/401。
- 未运行全量回归（由总控执行）；已抽查既有模块单测（test_foundation_security.py + test_ads_repo.py，23 passed）确认 pytest.ini/插件无副作用。

---

## 六、遗留项 / 待会签确认项

| # | 项 | 需谁决策/动作 |
|---|---|---|
| L1 | **M0 auth 表契约**：`M0AuthStore` 期望 `admin_users`(username/password_hash/role/created_at) + `auth_sessions`(token/username/created_at/expires_at)。M0 落地后按实际表名/校验规则对齐（当前假定 SHA-256 hex） | M0 总工落地 + 会签 |
| L2 | **requirements.txt 需补依赖**：`fastapi` / `uvicorn` / `httpx`（已本机安装验证；未改共享 requirements.txt，由总控决定并入） | 总控/M6 总工 |
| L3 | **M5 枚举文档漂移**：M5 context README 称 status/diagnosis 中文入库，实际代码存英文枚举（ads/report.py 归一化）；建议 M5 同步 context 文档 | M5 总工 |
| L4 | **错误码扩展**：`VALIDATION_ERROR`(422) / `INVALID_STATE`(409) 为 API 层局部码（DA-008 之外）；前端 enums 需加映射或直接展示 message | M6 总工（前端子代理②知悉） |
| L5 | **M4 retry 二次门禁**：v1.0 为状态机组合简化（人工确认即重提）；真实 `ListingGate` 全量校验接入留 v1.1 | M6 总工排期 |
| L6 | **M6_API_AUTH_MODE=m0 生产启用前置**：依赖 L1 落地；当前生产/部署用 fixtures 模式 + 环境变量账号 | M6 总工 |
| L7 | **/api/health 免登录例外**：仅返回服务/版本/鉴权模式（无业务数据）；如需严格全封闭可改 | M6 总工（默认保留） |
| L8 | **DA-011 契约会签回传**：草案字段差异（D1~D10）待 M0~M5 会签确认后回填 context/README.md | 总控转达 |
| L9 | `backend/pytest.ini`（pythonpath + glob 插件）为 API 层交付物，属共享 pytest 配置；如需收敛由总控评估 | 总控 |

---

## 七、纪律核验

- ✅ 未运行任何 git 命令（宪法第 7 节）
- ✅ 未修改 M0~M5 任何源码（backend/sourcing、materials、optimization、listing、ads、foundation 一律只读）
- ✅ 无明文密钥/token/cookie 值（密码运行时随机生成；环境变量只列名；日志/证据递归脱敏——foundation/security.py 复用）
- ✅ 全部文件 write/edit 工具 UTF-8 无 BOM（宪法第 11 节）
- ✅ pytest 独立 basetemp `.pytest-tmp-m6`（P-001/P-011）+ `-X utf8`（P-017）；未跑全量回归
- ✅ 小步落盘（P-014）：文件逐文件落盘，测试分文件推进
