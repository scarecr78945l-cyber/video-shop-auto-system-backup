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