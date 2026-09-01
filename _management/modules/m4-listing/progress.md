# M4 自动上架 · 进度看板（progress）

> 由总工程师持续维护。迭代版本号规则：每次重要返工/改版 +0.1（v1.0 → v1.1）。
> 当前迭代：**v1.3（M4 模块级收官）** ｜ 最近更新：2025 体系建立日 ｜ 模块完成度：**100%**

## 一、筹备任务（P0，已完成）

- [x] 阅读设计文档（07/09/10/11/03/01）+ 宪法 + 踩坑日志（P-001~P-007） | 负责:总工 | 进度:100% | 剩余:无
- [x] 撰写任务书 brief.md | 负责:总工 | 进度:100% | 剩余:无
- [x] 风险预判 risks.md（R1–R24，覆盖 OpenAPI 准入/令牌/轮询/UI 选择器/真实链接铁律/错峰防风控） | 负责:总工 | 进度:100% | 剩余:无
- [x] 数据字典 context/README.md（listing_* 表字段/状态机/错误码/跨模块契约/环境事实） | 负责:总工 | 进度:100% | 剩余:无
- [x] Schema 规划 database/README.md（DDL v0 + 表归属决策） | 负责:总工 | 进度:100% | 剩余:无
- [x] 制定开发排期（里程碑 P1–P6） | 负责:总工 | 进度:100% | 剩余:无

## 二、开发任务排期（可拆子代理）

> 标记「可拆子代理」的任务由总工创建子代理分派，任务书自包含（背景/输入/输出/验收/宪法要点）。待总控确认排期后启动。

| 任务 | 负责 | 进度 | 剩余工作 | 迭代 |
|---|---|---|---|---|
| [x] P1 `adapters/wechat_openapi.py` 薄封装（签名/时间戳、统一调用+限额退避+幂等重试、令牌桶、9 接口）+ 官方文档核对（REC-003）**可拆子代理** | 子代理 P1（`6a582604`，四派成功；前三派中断零产出，文档核对由总工落盘 `context/external-contracts.md`） | 100% ✅ | 验收通过：6 passed（`.pytest-tmp-m4`），9 接口齐全、live 模式 TODO 待核对 T1/T2 | v1.0 |
| [x] P2 上架校验硬门禁 `listing_gate.py`（六项门禁+失败分类+配置化阈值）**可拆子代理** | 子代理 P2（`054c76d6`） | 100% ✅ | 验收通过：25 passed（`.pytest-tmp-m4`） | v1.0 |
| [x] P3 状态机与证据（listing_tasks 状态机迁移+证据 JSON+断点续跑+前端任务卡片）**可拆子代理** | 子代理 P3（`b57d2057`） | 100% ✅ | 验收通过：31 passed（`.pytest-tmp-m4`），backend/listing/ 包 8 文件，R22 断言固化 | v1.1 |
| [x] P4 拒审处理 `platform_rejection.py`（原因分类+自动修复候选+二次门禁）**可拆子代理** | 子代理 P4（`11d4d391`） | 100% ✅ | 验收通过：36 passed（`.pytest-tmp-m4`），七分类+修复候选+二次门禁复用 ListingGate | v1.1 |
| [x] P5 Playwright 兜底降级+集成（UI 兜底通道、page_changed、与 M1/M3 数据契约联调、端到端模拟）**可拆子代理** | 子代理 P5（`d0e6e336`） | 100% ✅ | 验收通过：23 passed（`.pytest-tmp-m4`），ui_fallback + pipeline 端到端模拟 | v1.2 |
| [x] P6 M5 衔接+验收（销售中商品候选池只读视图、错峰参数、data-audit 登记） | 子代理 P6（`62253f5d`） | 100% ✅ | 验收通过：10 passed（`.pytest-tmp-m4`），candidate_pool + DA-005 登记 | v1.3 |
| [ ] P5 Playwright 兜底降级+集成（UI 兜底通道、page_changed、与 M1/M3 数据契约联调、端到端模拟）**可拆子代理** | 待派发（依赖 P1–P3） | 0% | 全部 | v1.2 |
| [ ] P6 M5 衔接+验收（销售中商品候选池只读视图、错峰参数、data-audit 登记） | 待派发（依赖 P5 + M5 就绪） | 0% | 全部 | v1.3 |

> 状态：总控已批准 P1~P6 排期（REC-003/REC-004 已裁决）；P1/P2 已派发子代理并行开发，离线/模拟模式先行（铁律：不提交真实商品）。v0.2 里程碑（薄封装骨架+单测可跑）= P1 验收通过。

## 二·五、子代理任务书要点（P1~P5 自包含模板，总控批准后直接派发）

> 任务书自包含要求（宪法第 9 节 3）：背景、目标、输入文件路径、输出文件路径、验收标准、宪法要点（子代理看不到本会话上下文）。
> 通用宪法要点（每个任务书必含）：不运行 git；只读写 `backend/data/db/m4-listing.db`（本回合不建库，子代理仅产出 DDL/代码）；任何文件禁写明文密钥（仅环境变量名）；文件一律 UTF-8 无 BOM（宪法第 11 节）；测试命令 `python -m pytest tests/test_<目标>_*.py -q --basetemp=".pytest-tmp-m4"`（P-001 临时目录坑 + P-011 多代理并行必须用本模块独立 basetemp，禁止共用 `.pytest-tmp`；全量回归由总控统一执行）；错误码复用 WorkflowJob 码表；完成后在 `_management/logs/agent-activity.md` 追加台账。

| 子代理任务 | 背景 | 输入文件 | 输出文件 | 验收标准 |
|---|---|---|---|---|
| **P1 OpenAPI 薄封装** | 07 文档四节；双轨制主链路；不依赖社区库（decisions D2） | `context/README.md`（外部契约/环境变量名）、`database/README.md`（DDL）、`risks.md`（R2/R4/R5/R6/R9）、`decisions.md`（D2/D6/D7/D8/D9） | `backend/adapters/wechat_openapi.py`、`backend/tests/test_wechat_openapi.py` | 签名（SHA256+时间戳窗口）、统一调用+限额退避+幂等重试(3 次)、按接口令牌桶、9 接口方法齐全；mock 全链路单测通过（不发真实请求）；错误码映射正确；无明文密钥 |
| **P2 上架校验硬门禁** | 07 文档三节；六项门禁失败不入队 | `context/README.md`（数据字典/跨模块契约）、`risks.md`（R20/R21/R23）、复用 `backend/sourcing/compliance.py` | `backend/services/listing_gate.py`、门禁用例测试 | 六项门禁全覆盖（标题 15–35/类目资质/主图≥5 张 1:1 不全相同+详情图/逐 SKU 真实成本+差异化售价/购买设置/合规预审）；失败不入队；阈值配置化（app_config）；错误码正确 |
| **P3 状态机与证据** | 07 文档五节；09 文档租约/幂等；前端不静默消失 | `database/README.md`（DDL v0）、`context/README.md`（状态机/错误码）、`risks.md`（R7/R22） | `backend/services/listing_state_machine.py`（或等效）、状态迁移测试、前端任务卡片数据接口说明 | 9 态迁移合法校验；`listed` 唯一判据=真实链接验证（R22 断言固化）；证据 JSON 留痕（listing_op_logs）；断点续跑（租约 45min） |
| **P4 拒审处理** | 07 文档五节；10 文档人工闸门 | `context/README.md`（listing_audit_records）、`risks.md`（R8）、`decisions.md`（D10） | `backend/services/platform_rejection.py`、拒审流程测试 | 驳回原因分类（title/category/qualification/image/price/content_compliance/other）；自动修复候选产出；重提需二次门禁；不可修复转 manual |
| **P5 Playwright 兜底+集成** | 07 文档一/二节；现有 181KB 脚本降级兜底；P-003 | 现有 181KB Playwright 脚本（降级源）、P1–P3 产出、`risks.md`（R10/R11/R19） | 兜底通道模块（选择器/URL 配置化、page_changed 检测）、端到端模拟脚本 | 仅处理 API 未覆盖操作；page_changed 检测+截图留证据+人工接管；失败不阻塞队列；端到端模拟（**不提交真实商品**）；真实链接才标已上架；错峰参数生效 |

## 三、里程碑进度

- **本模块当前完成度：100%（P1~P6 全部验收通过，M4 模块级收官）** ｜ 迭代 v1.3
- 已完成：
  - P0 筹备（任务书/风险/数据字典/Schema/排期）
  - P1 OpenAPI 薄封装 `backend/adapters/wechat_openapi.py`（6 测试，mock 模式零网络，live 待核对 T1/T2）
  - P2 上架校验硬门禁 `backend/services/listing_gate.py`（25 测试，六项门禁失败不入队）
  - P3 状态机与证据 `backend/listing/`（31 测试，7 表 ORM + 9 态迁移 + **R22 铁律断言固化** + 租约断点续跑）
  - P4 拒审处理 `backend/listing/platform_rejection.py`（36 测试，七分类 + 修复候选 + 二次门禁）
  - P5 兜底降级+集成 `backend/listing/ui_fallback.py` + `pipeline.py`（23 测试，端到端模拟）
  - P6 M5 衔接 `backend/listing/candidate_pool.py`（10 测试，候选池只读视图 + 错峰 + DA-005 登记）
  - P1 文档核对 `context/external-contracts.md`（待核对项 T1~T7 标注来源）
- 模块级验收门：
  - [x] 端到端模拟流程跑通（不提交真实商品）；真实链接才标「已上架」（R22 铁律，代码断言固化）
  - [x] 模块单测独立 basetemp 全绿：`--basetemp=".pytest-tmp-m4"`（**132 passed**：6+25+31+36+23+11；全量回归由总控统一执行）
  - [x] 无明文密钥；错误码复用 WorkflowJob 码表；幂等/断点续跑验证
  - [x] 数据审计登记完成（data-audit.md DA-005）；与 M1/M3/M5 口径核对一致（金额分/时间 UTC/状态枚举）
- 修复记录：
  - [x] **DA-009（M0 A7 集成冒烟缺口）**：pipeline 创建 SPU/SKU 后落库 `listing_spus`/`listing_skus`（幂等 upsert + audit_id 回填），repo 新增 upsert_spu/upsert_skus/get_spu/get_skus；候选池 title/category/价格不再恒 None；新增端到端回归用例（test_listing_candidate_pool +1）；目标测试 22 passed、M4 全量 **132 passed** 无回退（decisions D13）
- 待外部条件（不阻塞 mock 模式）：官方 channels OpenAPI 文档核对（T1~T7 需 web 额度恢复后销项，live 模式实现依赖 T1/T2）；企业主体/类目资质开通状态（REC-004，用户确认后切 live）

## P-041 上架推进：商品池 → pending 上架任务（2026-09-01 ｜ 用户批准推进上架）

- **新增 CLI `listing intake`**：读 M1 商品池（state=pool + real_cost）→ 清洗标题（15-35 字符）→ 构造 ListingCandidate（模拟主图/详情图、占位资质/购买设置）→ 六项门禁 → 建 pending 上架任务（幂等，generation_version 去重）。
- **结果**：50 个真实商品门禁全过 → **50 个 pending 任务**（API `/api/listing/tasks?status=pending` 可见；`/api/listing/ready`=0 正确——pending 未确认不进 M5 销售候选池）；M4 回归 **136 passed**。
- **真实 live 前置**（REC-004 待用户）：① M3 真实素材（当前占位图）；② 类目资质/运费模板（店铺后台）；③ 契约 T2/T4/T7。前置齐备 → 前端 confirm → pipeline.submit(live)。
- **登记**：pitfall-log P-041。

## P-042 真实素材生成 + intake 升级（2026-09-01 ｜ 用户重登有米云）

- **素材**：重采有米云（新签名图）→ 匹配 pool 商品 → 下载本地 → PIL 生成 5 张 1:1 主图 + 详情图（**56/65**，目录 `backend/data/images/listing/<pid>/`）；#1 微信图单独补；9 个有米云商品本次榜单未命中（登记待补）。
- **intake 升级**：优先真实素材（`data/images/listing/<pid>/`），缺失回退占位；清理旧占位 pending → 重建 **65 个 pending 上架任务**（API 可见）。
- **验证**：M4 回归 **115 passed**；65 pending 任务素材真实优先。
- **登记**：pitfall-log P-042。

## 四、验收门（模块级）

- [ ] 端到端模拟流程跑通（不提交真实商品）；真实链接才标「已上架」（R22 铁律）
- [ ] 模块单测在独立 basetemp 下全绿：`python -m pytest tests/test_<模块>_*.py -q --basetemp=".pytest-tmp-m4"`（P-001/P-011；全量回归由总控统一执行）
- [ ] 无明文密钥；错误码复用 WorkflowJob 码表；幂等/断点续跑验证
- [ ] 数据审计登记完成（data-audit.md）；与 M1/M3/M5 口径核对一致
