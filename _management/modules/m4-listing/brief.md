# M4 自动上架 · 模块任务书（brief）

> 本模块总工程师撰写（对照宪法第 2 节）。必读设计文档：07-自动上架模块设计.md、09、10、11、03、01（上架部分）。
> 版本：v1.3（实现完成）｜ 日期：2025 体系建立日 ｜ 模块 ID：m4-listing

## 一、模块目标

一句话：以**官方微信小店 OpenAPI（channels）为主链路、Playwright UI 为兜底**的双轨制，将 M1 已完成选品/询价/定价、M3 已完成主图/详情图的商品，自动完成「上架前校验硬门禁 → 创建 SPU/SKU → 上传图片（COS 直传）→ 提交审核 → 轮询审核状态 → 真实链接验证 → 已上架」，并把**销售中商品**送入 M5 托管投放候选池，全过程幂等、可断点续跑、证据留痕、防风控。

## 二、范围与边界

### 负责（In Scope）
1. `adapters/wechat_openapi.py` 薄封装：SHA256 签名 + 时间戳窗口、统一调用 + 限额退避、幂等重试（3 次）、按接口令牌桶配额管理；接口覆盖 create_spu / update_spu / create_skus / update_stock / update_price / upload_image（COS 直传）/ submit_audit / query_audit_status / get_product_link。
2. 上架前校验硬门禁清单（标题 15–35 字符非虚构 / 类目+资质完整 / 主图 ≥5 张 1:1 不全相同+详情图完整 / 逐 SKU 真实成本+差异化售价 / 必填购买设置（限购/物流/售后）/ 合规预审），**失败不入队**。
3. 上架状态机：待上架 → 创建中 → 草稿 → 提交审核 → 平台审核中 → 已上架（仅真实可访问链接）/ 审核驳回 → 平台拒审处理。
4. 状态与证据：`listing_tasks` 状态机 + 每次操作证据 JSON（`listing_op_logs`），前端「可上架品」点击必须返回任务 ID/阶段/错误，不静默消失。
5. 拒审处理 `platform_rejection.py`：记录驳回原因 + 自动修复候选 + 二次门禁。
6. Playwright 兜底链路：仅处理官方接口未覆盖操作（展示类目联动、部分参数、限购设置等），选择器/URL 全配置化，`page_changed` 检测留证据，失败不阻塞队列。
7. 与 M5 衔接：上架成功（已上架+真实链接）商品进入「托管添加候选池」，上架节奏与托管节奏错峰。
8. 配额管理与失败分类：复用 WorkflowJob 错误码表（VERIFICATION_REQUIRED / AUTH_REQUIRED / RATE_LIMIT / TIMEOUT / NO_MATCH / PLATFORM_REJECT / UNEXPECTED）。

### 不负责（Out of Scope）
- 选品打分、1688 询价、定价策略（M1）；素材采集（M2）；生图/素材优化（M3）；托管投放执行与报表（M5）。
- 基座库（`backend/data/db/app.db` 等）的建表与迁移（M0）；共享表 `upload_history` / `wechat_upload_logs` / `workflow_jobs` / `app_config` 的归属与写通道（见 database/README.md 归属决策）。
- git 提交/推送（总控唯一执行）；浏览器登录态维护（总控协调共享 Chrome）。

### 依赖其他模块（输入）
| 输入 | 来源 | 关键字段 |
|---|---|---|
| 商品池（上架就绪） | M1 | products 标题/类目/资质、sku 逐 SKU 成本、pricing 差异化售价、限购设置 |
| 主图/详情图（审核通过） | M3 | image_assets 5 张 1:1 主图 + 详情图，审核状态=通过 |
| 任务队列/配置/错误码 | M0 | workflow_jobs（stage=listing_upload）、app_config（类目白名单/阈值/限额）、共享表只读 |

### 对外提供（输出）
| 输出 | 去向 | 内容 |
|---|---|---|
| 销售中商品候选池 | M5 | 已上架+真实链接可访问的商品（listing_spus 只读视图），仅销售中商品 |
| 上架任务状态 | 前端/总控 | 任务 ID、阶段、错误码、证据 JSON（不静默消失） |
| 类目上架记忆 | M0/自身 | category_listing_memory 通过/拒审经验回流（经总控协调写入） |

## 三、交付物清单

| 交付物 | 验收标准 |
|---|---|
| `brief.md`（本文件） | 目标/范围/交付物/里程碑齐全，与 07/09/10/11 一致 |
| `risks.md` | 覆盖 OpenAPI 准入、令牌密钥、状态轮询、UI 选择器脆弱、真实链接铁律、错峰防风控等 |
| `progress.md` | 任务可勾选、完成度%、剩余、迭代版本号 |
| `decisions.md` | 关键技术决策与备选方案留痕 |
| `context/README.md` | 数据字典（SPU/SKU/上传历史/操作日志字段）、状态机、错误码、外部契约、跨模块契约、环境事实 |
| `database/README.md` | listing_* Schema DDL、表归属说明、迁移记录 |
| `adapters/wechat_openapi.py` | 签名/统一调用/限额退避/幂等重试单测通过；mock 全链路（不请求真实商品） |
| `listing_gate.py`（上架前校验） | 六项硬门禁全覆盖，失败不入队，错误码正确 |
| 状态机模块（listing_tasks + 迁移逻辑） | 状态迁移合法校验 + 证据 JSON 留痕 + 断点续跑 |
| `platform_rejection.py`（拒审处理） | 驳回原因分类 + 自动修复候选 + 二次门禁 |
| Playwright 兜底降级通道 | 仅 API 未覆盖操作；page_changed 检测；失败不阻塞队列 |
| 前端「可上架品」联动 | 点击返回任务 ID/阶段/错误 |
| M5 衔接 | 销售中商品入托管候选池（只读视图），错峰参数可配 |

## 四、里程碑拆解

| 阶段 | 任务 | 迭代版本 | 完成标准 |
|---|---|---|---|
| P0 筹备（本回合） | 通读文档；任务书；风险预判；开发排期 | v0.1 | 本回合全部文件落地 |
| P1 OpenAPI 薄封装（可拆子代理） | wechat_openapi.py：签名/时间戳、统一调用、令牌桶、限额退避、幂等重试、9 个接口 | v1.0 | 单测通过（mock 签名/退避/重试）；环境变量接入 |
| P2 上架校验硬门禁（可拆子代理） | listing_gate.py 六项门禁 + 失败分类 + 配置化阈值 | v1.0 | 门禁用例全覆盖；失败不入队 |
| P3 状态机与证据（可拆子代理） | listing_tasks 状态机 + 证据 JSON + 断点续跑 + 前端任务卡片 | v1.1 | 状态迁移测试通过；证据可回查 |
| P4 拒审处理（可拆子代理） | platform_rejection.py：原因分类 + 自动修复候选 + 二次门禁 | v1.1 | 拒审流程测试通过 |
| P5 兜底降级 + 集成（可拆子代理） | Playwright 兜底通道、page_changed、与 M1/M3 数据契约联调 | v1.2 | 端到端模拟流程（不提交真实商品）；真实链接才标已上架 |
| P6 M5 衔接 + 验收 | 销售中商品入托管候选池、错峰参数、数据审计登记 | v1.3 | 候选池只读视图可用；错峰验证通过 |

## 五、验收总纲（模块级）

1. 端到端模拟流程（选品 → 询价 → 生图 → 上架）跑通，**不提交真实商品**；仅当 `get_product_link` 返回且链接 HTTP 可达才标记「已上架」。
2. 全部写入幂等、可重试、可断点续跑；错误分类复用 WorkflowJob 码表。
3. 任何文件/日志无明文密钥；AppID/Secret 仅环境变量。
4. 测试运行统一 `python -m pytest tests/test_<模块>_*.py -q --basetemp=".pytest-tmp-m4"`（P-001 临时目录坑 + P-011 多代理并行必须用本模块独立 basetemp，禁止共用 `.pytest-tmp`；全量回归由总控统一执行）。

## 六、实现快照（v1.3 收官，2025 体系建立日）

| P | 交付物（backend/） | 测试 | 状态 |
|---|---|---|---|
| P1 | `adapters/wechat_openapi.py`（薄封装，mock 零网络，live 待核对 T1/T2） | test_wechat_openapi.py 6 例 | ✅ 验收通过 |
| P2 | `services/listing_gate.py`（六项硬门禁，失败不入队） | test_listing_gate.py 25 例 | ✅ 验收通过 |
| P3 | `listing/` 包（config/models/tables/db/repo/state_machine/__main__，7 表 + 9 态状态机 + R22 断言 + 租约断点续跑） | test_listing_tables.py 14 + test_listing_state_machine.py 17 | ✅ 验收通过 |
| P4 | `listing/platform_rejection.py`（七分类 + 修复候选 + 二次门禁） | test_listing_rejection.py 36 例 | ✅ 验收通过 |
| P5 | `listing/ui_fallback.py`（UI 兜底 + page_changed）+ `listing/pipeline.py`（端到端编排） | test_listing_fallback.py 12 + test_listing_pipeline.py 11 | ✅ 验收通过 |
| P6 | `listing/candidate_pool.py`（M5 候选池只读视图 + 错峰） | test_listing_candidate_pool.py 10 例 | ✅ 验收通过 |

- **模块单测合计 131 passed**（`--basetemp=".pytest-tmp-m4"`），全量回归由总控统一执行。
- 铁律落地：R22（真实链接验证才标已上架，代码断言固化）；REC-004（全程 mock，不提交真实商品）；数据审计 DA-005（M4→M5 候选池）已登记。
- 待外部条件：官方 OpenAPI 契约核对（external-contracts.md T1~T7，web 额度恢复后销项，live 模式依赖 T1/T2）；企业主体/类目资质开通（用户确认后切 live）。
