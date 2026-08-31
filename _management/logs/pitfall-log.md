# 全局踩坑日志（Global Pitfall Log）

> 铁律：任何代理开工前先读本日志；任何问题（已解决/未解决）必须登记。
> 登记格式见 `AGENT_CONSTITUTION.md` 第 3 节。编号连续：P-001 起。

---

## P-001 ｜ pytest 默认临时目录无权限（WinError 5）

- **出现时间**：2025 体系建立日 ｜ **模块**：全局/环境 ｜ **代理**：总控
- **现象与根因**：`python -m pytest tests -q` 报 10 个 PermissionError（WinError 5），位置 `C:\Users\Administrator\AppData\Local\Temp\pytest-of-Administrator`。根因是该临时目录在当前运行环境不可访问（与测试代码无关）。
- **解决方案**：pytest 指定工作区内临时目录：`python -m pytest tests -q --basetemp=".pytest-tmp"`（已验证 39 passed）。
- **防复发**：
  1. 所有测试运行命令统一带 `--basetemp=".pytest-tmp"`；
  2. 在 `backend/README.md` 测试一节与各模块任务书注明；
  3. 若后续 CI 使用 GitHub Actions（Linux），不受此影响，但本地一律如此。

---

## P-002（预判）｜ 平台登录态失效（AUTH_REQUIRED）

- **来源**：`02-半成品项目评估.md`、`09-数据模型与任务编排.md`（预判登记，非已发生）
- **现象**：共享 Chrome（CDP 9222/9223）登录态过期后，采集/上架/投放动作全部失败。
- **应对**：错误分类 `AUTH_REQUIRED` 不自动重试 → 转人工登录 → 断点续跑；登录态隔离（复用已有标签页，不重复开页）；浏览器资料（登录态）不入库不上传。

## P-003（预判）｜ 平台 UI 改版导致选择器失效（page_changed）

- **来源**：`02`、`08`、`11`（预判登记）
- **现象**：Playwright 兜底链路与投放后台页面改版即崩（历史已多次发生）。
- **应对**：上架主链路走官方 OpenAPI；UI 链路选择器/URL 全配置化 + `page_changed` 检测留证据 + 人工接管；投放链路保持 probe 脚本维护，必要时降级半自动。

## P-004（预判）｜ 硬编码路径与密钥散落

- **来源**：`02`、`10`（预判登记）
- **现象**：便携 Chrome 路径、API Key、Cookie 硬编码在脚本中，换机器即炸、日志泄漏。
- **应对**：全部迁移环境变量；日志 `_redact_text` 脱敏；`.gitignore` 已排除 `.env`/`*.pem`/`*.key`/浏览器资料；任何代理禁止在 md/代码/日志中写明文密钥。

## P-005（预判）｜ 多模块共用单库导致数据污染

- **来源**：本项目组织要求（预判登记）
- **现象**：模块间相互读写对方表/库，字段口径不一致，脏数据扩散。
- **应对**：一模块一库（`backend/data/db/<模块ID>.db`）+ 表名前缀 + 共享表只读 + 跨模块数据联动走 `data-audit.md` 审计（宪法第 4/5 节）。

## P-006（预判）｜ 上架/托管批量集中操作触发平台风控

- **来源**：`07`、`08`、`10`（预判登记）
- **现象**：同时批量提交上架/托管导致账号风控（验证码/封禁）。
- **应对**：≤50/批串行、批间隔可配、节流 0~4 级退避、熔断探针、上架与托管节奏错峰、一键全停。

## P-007（预判）｜ 素材不合规格被平台拒审/不支持投放

- **来源**：`05`、`08`（预判登记）
- **现象**：非 9:16、分辨率不足、超时长/超大小、审核不通过/源文件损坏的素材无法绑定投放。
- **应对**：素材硬规格（≥720×1280、9:16、MOV/MP4、≤500M、5~300s）写进输出参数并校验；审核不通过自动下架标记。

## P-008 ｜ 本机端口 8787 被工作区另一服务占用（WinError 10013）

- **出现时间**：2025 体系建立日 ｜ **模块**：M2 素材下载中台 / 全局环境 ｜ **代理**：子代理 F（ecc646f4）
- **现象与根因**：`python -m materials download --serve --port 8787` 启动失败，Windows 报 WinError 10013（端口被占用）。根因：8787 已被工作区另一服务 **captcha-vision-gateway** 占用（本机固定占用）。
- **解决方案**：M2 下载中台 CLI 默认端口改为 **8788**（`backend/materials/__main__.py`），并支持 `--port` 覆盖；验证时用空闲端口（60057）确认代码本身无问题。
- **防复发**：① M2 所有服务默认端口避开 8787（文档/环境事实已注明）；② 起服务前先探测端口占用（若脚本化可加 bind 失败重试提示）；③ 其他模块新增服务默认端口前先查本日志与本机端口占用。

---

## P-009 ｜ git 推送 GitHub 需配置本地代理（Connection reset）

- **出现时间**：2026-08-28 ｜ **模块**：全局/备份 ｜ **代理**：总控
- **现象与根因**：git push/ls-remote 报 `Connection was reset` / `Could not connect to server`，但网页/API 正常——本机走本地代理 `127.0.0.1:7897`（系统 ProxyEnable=1），直连 github.com:443 被阻断，而 git 默认不走系统代理。
- **解决方案**：`git config --global http.proxy http://127.0.0.1:7897` 与 `https.proxy` 同值（已配置）。
- **防复发**：任何 git 远程操作前确认代理配置；换机器/换网络时检查。

---

## P-010 ｜ .gitignore 的 `logs/` 规则误伤 `_management/logs` 核心文件

- **出现时间**：2026-08-28 ｜ **模块**：全局/备份 ｜ **代理**：总控
- **现象与根因**：`_management/logs/`（踩坑日志/工作台账/数据审计）从未被 git 跟踪——根 `.gitignore` 中 `logs/` 无路径前缀，匹配**任意层级**的 logs 目录，误伤管理中枢核心文件；导致多轮提交均未包含这三个文件。
- **解决方案**：`.gitignore` 的 `logs/` 改为 `backend/logs/`（精确限定）；`git add -A` 重新纳入三个日志文件，提交 v0.4。
- **防复发**：① .gitignore 规则一律加路径限定（`/logs/` 或 `backend/logs/`），禁止裸目录名；② 每次 git add 后抽查 `git ls-files` 关键文件是否在跟踪中；③ 提交后核对 GitHub 仓库文件完整性。

---

## P-011 ｜ 工作区多代理并行跑 pytest 共享 `.pytest-tmp` 互相清理（间歇性失败）

- **出现时间**：2025 体系建立日 ｜ **模块**：M2 及全局（多模块并行开发） ｜ **代理**：子代理 C（M2 批次 2）+ 总控（全量回归确认）
- **现象与根因**：工作区多个模块代理并行执行 `python -m pytest tests -q --basetemp=".pytest-tmp"`（同一 backend 目录、同一 basetemp 路径），并发进程互相清理临时目录 → 间歇性 `2 failed / 79 errors` 或 `13 errors`；**串行复跑即稳定全绿**，代码本身无问题。
- **解决方案（总控验证为强制方案）**：**每个模块/代理使用独立 basetemp**：`--basetemp=".pytest-tmp-<模块ID>"`（如 `.pytest-tmp-m0`/`-m1`/`-m2`/`-m3`/`-m4`/`-m5`）。总控用独立目录复跑全量：327 passed / 7 failed（7 个为 M0×5 + M3×2 真实缺陷，与并发无关）。串行复跑仅作辅助确认，不替代隔离。
- **防复发**：① 宪法与 backend/README.md 统一规定「pytest 必须带本模块独立 basetemp，禁止共用同一目录」；② 总工分派子代理任务书时必须写明本模块专属 basetemp 名；③ 验收以独立 basetemp 下全绿为准。

---

## P-012 ｜ pytest 独立 basetemp 目录曾被 git 误跟踪入库

- **出现时间**：2026-08-28 ｜ **模块**：全局/备份 ｜ **代理**：总控
- **现象与根因**：P-011 落地前，某模块的 `.pytest-tmp-m1-s2/` 临时目录（含测试生成的 png/mp4/bin/json 假文件）被 `git add -A` 误纳入版本库并已推送。
- **解决方案**：`.gitignore` 追加 `backend/.pytest-tmp*/`（含 `.pytest-tmp/`）；`git rm -r --cached` 移除索引跟踪（保留工作区文件）；提交 v0.9 并推送（远程不再含临时文件）。
- **防复发**：① `.gitignore` 已固化 `.pytest-tmp*` 排除规则；② git add 前用 `git status` 检查临时目录不出现；③ 后续提交凡见 `backend/.pytest-tmp` 一律先确认 .gitignore。

---

---

## P-013 ｜ materials CLI `normalize` 子命令潜在 NameError（Path 未导入，ffmpeg 就绪后才触发）

- **出现时间**：2026-08-28 ｜ **模块**：M2 素材收集 ｜ **代理**：子代理 B3（f833480a）
- **现象与根因**：`backend/materials/__main__.py` 的 `normalize` 命令在第 148 行使用 `Path(input_path).exists()`，但模块顶部未 `from pathlib import Path`。当前 ffmpeg 缺失时命令在更早的 ffmpeg 探测（`runner._resolve_ffmpeg()`）即 SystemExit(1)，`Path` 行不可达，故既有测试全绿未暴露；**一旦本机 ffmpeg 就绪，normalize 必然 NameError**（潜藏缺陷）。
- **解决方案**：暂未修复（不在任务书范围内；子代理 B3 仅登记上报）。修复 = `__main__.py` 顶部补一行 `from pathlib import Path`（一行 import，无行为副作用）。
- **防复发措施**：① 已上报总工排入下批任务；② CLI 子命令新增/修改时检查是否使用了未导入的模块级名字；③ ffmpeg 环境就绪后跑 `python -m materials normalize` 冒烟必现该问题，修复后补 CLI 冒烟用例。

---

## P-014 ｜ 子代理连续中断零产出时改用 workflow 工具（进度累积策略）

- **出现时间**：2026-08-28 ｜ **模块**：M3 素材优化（三路管线开发） ｜ **代理**：M3 总工
- **现象与根因**：subagent 工具 4 实例连续中断零产出（含 2 次 send_message 续跑仍失败）——长任务单会话易遇上下文耗尽/会话抖动，产出随之中断丢失。
- **解决方案（M3 验证有效）**：改投 **workflow 工具**（全新 agent + 容错），以「**进度累积**」策略多轮落盘成功——每轮保留已写文件，收尾轮补齐；大任务拆为多轮，每轮落盘即留存。
- **防复发**：① 总工派发长任务优先考虑 workflow 工具或「多轮小步+每轮落盘」模式（与 M0 极小程序化同理）；② 任务书强制「第一动作写盘、每完成一文件立即落盘」；③ 子代理中断后先检查已落盘文件再重派，避免重复劳动。

---

## P-015 ｜ 总控全量回归读到并行子代理写文件中间状态（误报失败）

- **出现时间**：2026-08-28 ｜ **模块**：M2 素材收集（批次 4 · pipeline） ｜ **代理**：总控（全量回归）+ M2 总工（排查）
- **现象与根因**：总控全量回归报告 `test_materials_pipeline.py::test_daily_stats_aggregation` 失败（DuplicateAssetError）。排查：该测试单独跑 1 passed、文件级 19 passed、全 M2 套件 318 passed/1 skipped 全绿——**当前代码无缺陷**。根因：失败时点子代理 B4-3 仍在写 `test_materials_pipeline.py`（running 状态），全量回归读到**中间状态**（当时测试文件尚未定型），属并行开发竞态而非代码缺陷。
- **解决方案**：无需改代码。等 B4-3 完成后复跑确认全绿；登记本坑。
- **防复发**：① 总控执行全量回归前先确认目标模块子代理均已完成（list_agents 无 running）；② 回归失败先复跑确认（若失败仅出现在子代理在途期间 → 判定中间状态误报）；③ 子代理任务书继续强调「每完成一文件立即落盘」，缩短中间状态窗口。

---

## P-016 ｜ 共享浏览器 9223 僵尸页面导致 playwright connect_over_cdp 挂起（HTTP /json 正常但 ws 无响应）

- **出现时间**：2026-08-29 ｜ **模块**：M1 选品（S3c 真实采集联调） ｜ **代理**：子代理 S3c
- **现象与根因**：`python -m sourcing collect/probe` 报 `connect_over_cdp: Timeout 180000ms exceeded`（ws connected 但后续无消息响应）。排查：CDP HTTP `/json`、`/json/version`、`/json/list` 均正常（Chrome 151 响应），browser-level ws 直连发 `Browser.getVersion` 也正常 → **ws 层无问题**；playwright DEBUG 协议日志显示其初始化序列对**每一个已打开 target 逐个 Page.enable/Network.enable**，**存在无响应僵尸页面（store.weixin.qq.com/shop/home 商机中心 home、compass.jinritemai.com/shop 罗盘核心数据页）时整个初始化挂起**。根因：9223 共享浏览器长期挂机积累僵尸标签页（渲染进程无响应），playwright 初始化全部 target 时被卡死；`probe-browsers`/`collect` 无法连接。
- **解决方案**：通过 CDP HTTP `GET /json/close/<targetId>` 关闭**非采集目标**的僵尸页面（保留 `opprotunity` 与 `rank-product` 两个采集目标页），playwright 连接立即恢复（contexts=1, pages=2）。关闭页面**不影响登录态**（cookie 在 profile，非页面内）。注意 `/json/close` 对 `browser_ui`（omnibox-popup）target 返回 404，此类 target 关闭不了但**不阻塞 playwright**（本次验证其非卡死源）。
- **防复发措施**：① 共享 9223 浏览器定期清理非目标标签页（采集前先 `/json/list` 检查，发现堆积僵尸页先 close 非目标页）；② 采集器连接失败时可在日志提示「9223 存在多个标签页，建议先关闭非采集页面再重试」；③ 商机中心 home 页与罗盘核心数据页**非采集必需**（采集器用 url_template 新开页或 current_page 按域定位），后续任务可考虑在探测阶段自动清理；④ 已在 context/README.md S3c 小节登记环境事实。

---

> 日志继续追加中（由所有代理共同维护）。

## P-017 ｜ Windows 下 Python 默认 GBK 编码读取文件（中文乱码）

- **出现时间**：2026-08-29 ｜ **模块**：全局/测试 ｜ **代理**：总控（C1 迁移测试时发现）
- **现象与根因**：Python 3.13 在 Windows 默认以系统区域编码（GBK/cp936）读取 .py 源文件与 JSON，含中文的测试文件运行时出现乱码（如 pytest 收集的字符串变 `��乱码`）；-X utf8 后正常。
- **解决方案**：运行 Python/pytest 统一加 `-X utf8`：`python -X utf8 -m pytest tests -q --basetemp=...`；或设置环境变量 `PYTHONUTF8=1`。
- **防复发**：① 宪法测试纪律补充 -X utf8；② 各模块任务书测试命令统一；③ 中文断言/字面量所在测试必须 -X utf8 运行。

---

## P-018 ｜ 并行融合 P0-1 中间状态导致 M4 全量回归 13 failed（AttributeError _prefill_from_category_memory）

- **出现时间**：2026-08-29 ｜ **模块**：M4 上架（REC-融合 P0-1 类目记忆）/ 全局 ｜ **代理**：M0 新任总工（P2 任务期间全量回归）
- **现象与根因**：M0 执行全量回归（`--basetemp=".pytest-tmp-m0"`）报 **13 failed**（`test_listing_pipeline.py` ×11、`test_listing_candidate_pool.py` ×1、`test_foundation_integration.py` ×1），根因 `'ListingPipeline' object has no attribute '_prefill_from_category_memory'`——`listing/pipeline.py` 已加入调用点（第 76 行 `candidate, prefill = self._prefill_from_category_memory(candidate)`）而方法尚未落盘。排查：grep 确认 `listing/repo.py`（get_category_memory/upsert_category_memory）与 `tables.py`（listing_category_memory）均已实现、`pipeline.py` 第 398 行方法随后存在——回归执行时正值 M4 侧 REC-融合 P0-1 迁移**在途写入的中间状态**（P-015 同型竞态，非代码缺陷）。
- **解决方案**：无需改代码。M4 侧落盘完成后复跑 `pytest tests/test_listing_pipeline.py tests/test_listing_candidate_pool.py tests/test_foundation_integration.py --basetemp=".pytest-tmp-m0"` → **26 passed 全绿**；M0 foundation 子集 **94 passed**（79 既有 + manifest 15 新增）零回归。
- **防复发措施**：① 全量回归前先确认目标模块代理均完成（P-015 已立）；② 回归失败先复跑确认——本坑再次验证该流程有效（失败仅出现在并行代理在途期间 → 中间状态误报）；③ 跨模块并行期间，M0 验收以「foundation 子集 + 相关模块复跑」双证为准；④ P0-1 类目记忆融合由 M4 侧完成（新增 listing_category_memory 表），M0 共享表治理不受影响。

---

## P-019 ｜ Windows 回环快速 HTTP 请求 WinError 10048（TIME_WAIT 端口复用）

- **出现时间**：2026-08-29 ｜ **模块**：M6 前端控制台（批次3 冒烟） ｜ **代理**：子代理③
- **现象与根因**：冒烟脚本（Python urllib 逐请求新建 socket，快速连续请求 127.0.0.1:8123）在第 2~4 个请求起随机报 `OSError: [WinError 10048] 通常每个套接字地址(协议/网络地址/端口)只允许使用一次`。根因：Windows 回环连接后进入 TIME_WAIT（默认约 2×MSL），系统为同一目标 (127.0.0.1, port) 复用最低可用本地临时端口时命中 TIME_WAIT 元组，connect 直接 10048（Windows 较 Linux 严格，无 SO_REUSEADDR 时不允许复用）。`SO_REUSEADDR` 客户端方案在本机仍不稳定；改用**单条持久连接**（http.client keep-alive + 手动 Set-Cookie 捕获）后 19 项断言全绿。
- **解决方案**：冒烟/联调脚本对同一本机服务的多次请求一律使用**持久连接**（http.client 复用同一 HTTPConnection；requests.Session 同理），不要逐请求新建 socket；需要会话 cookie 时从登录响应 `Set-Cookie` 手动取 `m6_session=...` 随请求头携带。
- **防复发**：① 本机/CI 冒烟脚本禁止逐请求新建 socket 打回环服务；② 已把该模式写入批次3 冒烟脚本（`frontend/.smoke-b3/`，用完已删，模式见 REPORT 说明）；③ 若必须逐请求新建，先设置 `TcpTimedWaitDelay` 或接受重试。

---

## P-020 ｜ M6 v1.0 联调 1 次瞬态连接超时（retry 后 exceptions 回读，未复现）

- **出现时间**：2026-08-29 ｜ **模块**：M6 前端控制台（v1.0 集成验收冒烟） ｜ **代理**：子代理⑤
- **现象与根因**：冒烟脚本（http.client 持久连接）在 `POST /api/workbench/retry/{job}` 成功后，下一次 `GET /api/workbench/exceptions?status=waiting_verification` 连接超时（10s，客户端抛 TimeoutError）；服务端同链路其他请求均 2-12ms。**复跑与后续多轮未复现**（含同链路 pytest 75 用例全绿）；根因未定位，倾向瞬态环境抖动（SQLite 文件锁时序/Windows 回环连接状态），非代码缺陷。
- **解决方案**：无需改代码。冒烟脚本增加「失败打印服务端日志尾巴」辅助定位；确认未复现后按环境抖动处理。
- **防复发措施**：① 冒烟断言遇超时先复跑确认（P-015/P-018 同型方法论：并行/瞬态失败先排除环境再判缺陷）；② 冒烟脚本把服务端日志写文件而非管道（避免 pipe 死锁掩盖真因）；③ 若再现，按 SQLite 写锁方向排查（审计写 M0 logs 与异常查询的锁时序）。

---

## P-021 ｜ next build 后直接 next dev → 全路由返回 not-found 页（HTTP 200 误导）

- **出现时间**：2026-08-29 ｜ **模块**：M6 前端控制台（v1.0 路由冒烟） ｜ **代理**：子代理⑤
- **现象与根因**：`npm run build` 后再 `npm run dev`，dev 命中陈旧 `.next` manifest（build 产物与 dev 态冲突），**所有路由返回 HTTP 200 但页面内容为 not-found 页**；且 Next.js App Router 每个页面 RSC flight payload 内嵌客户端 404 兜底组件定义（`HTTPAccessErrorFallback`，"This page could not be found" 字符串出现在每个正常页面的 HTML 里），单纯字符串标记判断会误报。
- **解决方案**：dev 前删除 `.next` 目录（`Remove-Item -Recurse -Force .next`）；路由冒烟判定改为「HTTP 200 + 页面内容标记（工作台壳/登录表单）+ 未知路由 404 基线」。
- **防复发措施**：① README 快速开始已备注「build 后需删 .next 再 dev」；② 路由冒烟/页面验收禁止以「HTTP 200」或「not-found 字符串」单独作判据；③ 冒烟前先验证 /login 含真实表单内容。
## P-022 ｜ FastAPI CORS 中间件顺序：内层 401 响应缺 CORS 头（跨域登录失败）

- **出现时间**：2026-08-29 ｜ **模块**：M6 API 层 ｜ **代理**：总控（前端联调排查）
- **现象与根因**：前端跨域访问 `/api/auth/me` 报 `No 'Access-Control-Allow-Origin' header`——OPTIONS 预检和 200 响应有 CORS 头，但 **auth_guard 内层中间件直接返回的 401 响应无 CORS 头**。根因：Starlette `add_middleware` 先注册的在栈**内层**，CORS 注册在 auth_guard 之前 → auth_guard 短路返回时跳过 CORS。
- **解决方案**：CORS 中间件**最后注册**（栈最外层），保证所有响应（含内层中间件的 401/异常）都过 CORS 加头。修复后验证：401/200 均带 Allow-Origin + Allow-Credentials。
- **防复发**：① FastAPI 中间件顺序纪律：CORS 必须最外层；② 跨域登录闭环测试须覆盖「未登录 401 响应带 CORS 头」断言；③ 前端联调异常先查 Console 的 CORS 报错并核对响应头。
## P-023 ｜ SameSite=Lax + 跨站(127.0.0.1 vs localhost) → 登录后会话 cookie 不携带

- **出现时间**：2026-08-29 ｜ **模块**：M6 前端/API 联调 ｜ **代理**：总控
- **现象与根因**：登录成功（200 + Set-Cookie）但随后 `/api/auth/me` 401 → 前端弹回登录页。根因：Set-Cookie 为 SameSite=Lax，前端 localhost:3000 fetch **127.0.0.1:8001 属跨站**（Chrome 将 localhost 与 127.0.0.1 视为不同站点），Lax cookie 在跨站 fetch 中不携带。
- **解决方案**：前后端统一 **localhost**（同站点跨端口，Lax 正常携带）：API 监听 `localhost:8001` + 前端 `NEXT_PUBLIC_API_BASE=http://localhost:8001`。验证：登录→me 完整闭环 200。
- **防复发**：① 本地联调一律用 localhost（不用 127.0.0.1）；② 若必须跨站（不同域名），后端 Set-Cookie 需 `SameSite=None; Secure`（要求 HTTPS）；③ 生产推荐 Next.js rewrites 同源代理（/api → 后端），彻底消除跨站与 CORS。
## P-024 ｜ next build 与 next dev 共享 .next 目录 → 运行时 Cannot find module chunk

- **出现时间**：2026-08-30 ｜ **模块**：M6 前端 ｜ **代理**：总控（联调值守）
- **现象与根因**：dev 服务器运行中执行 `npm run build`（M6 v1.1 验收）→ build 重建/清理 .next → dev 服务器仍引用旧 chunk → 浏览器报 `Cannot find module './611.js'`（webpack runtime）。
- **解决方案**：停 dev → 清 .next → 重启 dev（编译完成后正常）。
- **防复发**：① build 与 dev 严禁同时运行（同一 .next 目录冲突）；② 验收流程固定：先停 dev → build → 再启 dev 或直接 start 生产构建；③ 前端 README 注明「build 前停 dev、dev 前清 .next」。
## P-025 ｜ ffmpeg 安装后 e2e 测试走真实转码致 fake 视频失败（Mock 注入缺失）

- **出现时间**：2026-08-30 ｜ **模块**：M3 视频二创 ｜ **代理**：总控（B1 LLM 联调时发现）
- **现象与根因**：test_optimization_e2e 原依赖「detect_ffmpeg 未就绪 → composer 自动 Mock」；ffmpeg 安装后 detect_ffmpeg 返回真实 → 走 FFmpegProcessRunner 对 fake 视频 probe 失败 → spec_ok=False。
- **解决方案**：e2e 显式注入 `MockFFmpegRunner(probe_result={width/height/duration/size_bytes/format})`（测试确定性不依赖本机 ffmpeg 状态）。
- **防复发**：① 测试凡依赖「外部工具缺失→自动降级」的，须显式注入 Mock（不依赖环境探测结果）；② ffmpeg 环境变更后全量回归 M3 域；③ 真实转码验证走独立冒烟（非 e2e 单测）。
## P-027 ｜ 1688 以图搜款唯一化（用户裁定：标题搜索同款无效，废弃）

- **出现时间**：2026-08-31 ｜ **模块**：M1 1688 询价 ｜ **代理**：总控（M1 真实运行验证时用户裁定）
- **现象与根因**：alibaba.py 无图时退回「标题搜索」找同款——实测标题搜索出整类商品（精度差），用户裁定「用标题搜同款是没有用的，要以图搜款」。
- **解决方案**：废弃标题搜索分支；quote() 以图搜款为唯一方式——图源优先级 item.image_urls → raw 候选图（taobao_image_urls/image_url/榜单图）；无图 → NO_MATCH「无图不可以图搜款」且不打开浏览器。
- **防复发**：① 采集器（商机中心/抖店/有米云）必须携带商品图 URL（raw 字段契约）；② 无图商品标记 NO_MATCH 不询价（后续可补图源）；③ 测试覆盖（test_alibaba_image_search.py 4 例）。