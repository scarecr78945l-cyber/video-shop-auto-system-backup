# M6 前端控制台 · 决策记录（decisions）

| 日期 | 决策 | 理由 | 备选方案 | 决策人 |
|---|---|---|---|---|
| 2026-08-29 | **金额对外口径：API 层对外金额一律「元（float）」**；内部存储分不变，API 层 ÷100 换算（M1 本身为元直接透传）；前端只消费元 | 总控裁决（DA-001）；消除 M1 元 vs M4/M5 分混用风险（R-DATA-01），前端零换算 | 对外分 int | 总控 |
| 2026-08-29 | **鉴权会话表归属：挂 M0 foundation**（跨模块共享）；API 层只消费不重复建表；开发期 AuthStore 接口 + fixtures 内存实现过渡（`M6_API_AUTH_MODE=fixtures\|m0`） | 总控裁决；避免多模块重复实现会话 | API 层自有表 | 总控 |
| 2026-08-29 | **v1.0 验收口径 = fixtures/mock 模式**（控制台可启动、各页数据可展示、人工闸门可操作，不依赖真实登录态/平台数据） | 总控裁决；真实数据接入为 v1.1 增量（环境就绪即启用） | 真实数据验收 | 总控 |
| 2026-08-29 | **排期批准**：v0.2 API 层 → v0.3 前端工程 → v0.4~v0.6 页面 → v0.7 闸门 → v1.0 集成；子代理①（后端 API 层）即刻派工 | 总控批准 | — | 总控 |
| 2026-08-29 | DA-011 契约会签：总控转达 M0~M5 总工核对，回传后定稿 | 宪法第 5 节 | — | 总控（待回传） |
| 2026-08-29 | **v0.2 API 层验收通过**：`backend/api/` 交付（41 路径），复跑 75 passed（`.pytest-tmp-m6`）；抽查 app/auth/errors/m5_ads 质量合格；M0~M5 源码零修改；差异 D1~D10 登记 context | 验收复跑全绿 + 代码审查 + 纪律核验通过 | 退回修改（未触发） | M6 总工 |
| 2026-08-29 | **API 层局部错误码备案**：`VALIDATION_ERROR`(422)/`INVALID_STATE`(409) 为 DA-008 之外的非业务码，前端直接展示 message；已通知前端子代理② | 统一错误格式需要；不污染业务码表 | 并入 DA-008（留待总控裁定） | M6 总工 |
| 2026-08-29 | **M5 枚举以代码实测为准**：status/diagnosis/target_type 为英文枚举（pending/active/…、excellent/good/…、roi/net_roi/goods），API 原值透传，前端 lib/enums.ts 翻译（D5）；M5 context 文档表述待 M5 总工同步 | 代码为准（ads/tables.py、report.py 归一化）；避免前端按错误文档翻译 | 等 M5 会签后再开发（会阻塞 v0.3，不采用） | M6 总工 |
| 2026-08-29 | **v0.3 前端工程底座验收通过**：`frontend/` 交付（40 文件，Next 15/React 19/Tailwind 3.4）；复跑 vitest 55 passed + tsc 0 errors；E2E 登录闭环实测；抽查 lib/api.ts 质量合格；全文件 UTF-8 无 BOM | 验收复跑全绿 + 代码审查通过 | 退回修改（未触发） | M6 总工 |
| 2026-08-29 | **前端冒烟端口用 8123**：本机 8000 被系统进程 svchost 占用（非本 API）；`NEXT_PUBLIC_API_BASE` 按实际部署 API 端口配置 | 本机环境事实（子代理②实测） | 杀 svchost（不采用，系统进程） | M6 总工 |
| 2026-08-29 | **next build 跳过 lint**（eslint.ignoreDuringBuilds: true）：lint 非验收项，eslint 9 扁平配置桥接为可运行级别，严格 lint 留 v1.0 前升级 | 避免 build 阻塞；单测/tsc 已覆盖类型与口径 | 升级 eslint 配置（留后） | M6 总工 |
| 2026-08-29 | **v0.4 页面建设批次1验收通过**：总览/商品池/素材库 3 页接真实 API；复跑 vitest 107 passed + tsc 0 errors + build exit 0；API 字段映射冒烟实测吻合；抽查 dashboard.ts（纯函数 + 09 阶段顺序 + 枚举集中翻译）质量合格 | 验收复跑全绿 + 代码审查通过 | 退回修改（未触发） | M6 总工 |
| 2026-08-29 | **M2 库 schema 过期上报**：`backend/data/db/m2-materials.db` 缺 `asset_items.relevance_status` 等新列，真实环境下 GET /api/assets 500——属 M2 后端数据层问题（materials/tables.py 已含新列，库需重建/迁移），转达 M2 总工；前端用临时新 schema 库验证通过，未代改 backend | backend/ 只读纪律；库文件不入 git 由模块总工管理 | 前端规避（不采用） | M6 总工（转 M2） |
| 2026-08-29 | **页面建设遗留项登记（待后端补字段/端点，不阻塞 v0.4 验收）**：①商品池关键词=客户端过滤（API 无参数）②类目/平台下拉=当前页去重（API 无枚举端点，可加 `/api/products/categories`、`/api/assets/platforms`）③商品列表缺 source/updated_at（summary 未含，可后端补） | 页面数据可展示目标已达成；增强项留后端增量 | 阻塞页面开发（不采用） | M6 总工（待总控协调） |
| 2026-08-29 | **v0.5 批次2验收通过**：上架任务页（9 态状态机可视化对齐 state_machine.py）+ 托管看板页（对齐后台列）；复跑 vitest 150 passed + tsc 0 errors + build exit 0；M4/M5 冒烟全端点吻合（confirm/retry/409、already、余额告警 58.0<100.0、报表降序→升序）；抽查 lib/ads.ts 质量合格 | 验收复跑全绿 + 代码审查通过 | 退回修改（未触发） | M6 总工 |
| 2026-08-29 | **v0.6 批次3验收通过**：`/review` 审核工作台（图片审核 Tab1 + 素材相关性预审 Tab2，独立路由不并入 workbench）；复跑 vitest 175 passed + tsc 0 errors + build exit 0；冒烟 19 断言全绿（D6 rule_draft_created、422 VALIDATION_ERROR、already_approved、relevance-confirm changed=false、learning_rule_drafts 闭环落库）；P-019 已登记踩坑日志 | 验收复跑全绿 + 冒烟全绿 | 退回修改（未触发） | M6 总工 |
| 2026-08-29 | **v0.7 人工闸门工作台验收通过**：/workbench（6 类闸门待办卡片 + 选品复核内联 gate-confirm + KillSwitch 复用）+ /exceptions（error_code 分组 + 三类接管 retry）；复跑 vitest 197 passed + tsc 0 errors + build exit 0；冒烟 37 断言全绿（gates/exceptions/retry/gate-confirm 200/409/404 全语义）；差异登记：草案 paused_until 在 API 中不存在，实际为 retry_after（前端列名「可重试时间」） | 验收复跑全绿 + 冒烟全绿 | 退回修改（未触发） | M6 总工 |
| 2026-08-29 | **v1.0 集成验收通过（M6 模块交付完成）**：复跑 vitest 197 passed + API 层 pytest 75 passed（双回归全绿）；e2e 联调 40 断言全绿（登录→8 页路由 200→6 类人工闸门操作闭环→kill-switch 回读→计数联动）；v1.0 四条验收标准逐项核对全过；前端业务代码零缺陷（5 项缺陷均为冒烟脚本自身）；遗留项 31 条 + L1~L9 逐条复核，移交总控清单已汇总（frontend/REPORT.md 第六节）；P-020/P-021 登记踩坑日志 | 双回归全绿 + e2e 全绿 + 验收标准全过 | 退回修改（未触发） | M6 总工 |
| 2026-08-29 | **M6 移交总控事项（v1.0）**：🔴 M2 materials.db schema 过期（真实库 /api/assets 500，联调临时库已证前端正确）｜🔴 M0 auth 表契约（L1/L6，m0 鉴权生产前置）｜🟡 图片预览媒体端点｜🟡 托管商品名 join｜🟡 requirements.txt 补依赖（L2）｜🟡 M5 枚举文档漂移（L3）｜🟡 DA-011 会签回传（L8）｜🔵 列表关键词/分页/聚合端点等 v1.1 迭代项 | 前端零缺陷，遗留均为后端/协调项；申请总控执行 M0~M5 全量回归 + 备份标签 | — | M6 总工（移交总控） |
| 2026-08-29 | **审核/预审差异登记（D-B3 系列）**：①批次列表字段为 image_type/plan/gate/target_count（草案 category_key/mode/generation_round 不存在，按源码实测落地）②review_status 三态（无 excluded）③图片预览为占位（backend/api 无媒体服务端点，file_path 本地路径）——待后端补媒体端点后接真实预览 | 以 backend/api 源码为准（任务书草案落后于实现）；前端按实测落地 | 等后端补端点再开发（不阻塞审核流程，不采用） | M6 总工 |
