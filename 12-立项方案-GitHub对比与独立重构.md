# 12 立项方案：独立新仓库 + GitHub 相似项目对比 + 可用 Skills

> 决定：**独立新仓库，从零/重构**。本文给出 GitHub 相似项目实测对比、可用 skills 盘点、以及新仓库的结构与落地路线。用于讨论定稿后再动工。

---

## 一、GitHub 相似项目实测盘点（基于 GitHub API 实拉 2026-09 数据）

### 按本项目五大功能归类

| 功能 | 相似项目 | 语言/Star | 能力 | 对本项目的借鉴价值 |
|---|---|---|---|---|
| **素材收集（视频号下载）** | `putyy/res-downloader` | Go / 19.6k★ | 视频号、小程序、抖音、快手、小红书、直播流、m3u8 等常见网络资源下载 | 视频号视频抓取的核心范式（签名/嗅探/分流）；可作为素材采集中台的前置参考，Apache-2.0 |
| | `ltaoo/wx_channels_download` | Go / 9k★ | 纯微信视频号下载器，活跃维护（2026-09 仍有 push） | 视频号专用下载，比 multi-platform 更聚焦，可 clone 作视频号下载器底座 |
| | `qiye45/wechatVideoDownload` | 5.7k★ | 视频号视频、直播回放、直播、图片下载 | 同素材链路备选；个人维护、改版即失效 |
| | `Evil0ctal/WeChat-Channels-Video-File-Decryption` | WebAssembly / 361★ | 视频号加密视频（XOR + Isaac64 PRNG/WASM 模块）解密 API | 解决「视频号本地缓存加密文件无法直接读取」的关键技术点，逆向分析可参考 |
| **自动分发/发布（素材优化+上架类比）** | `dreammis/social-auto-upload` | Python / 14.7k★ | 自动上传视频到抖音、小红书、**视频号**、TikTok、YouTube、B站 | 视频号上传的 playwright/接口范式；多平台账号管理；MIT —— 上架兜底通道最值得借鉴 |
| | `kebenxiaoming/matrix` | Python / 956★ | 抖音/快手/**视频号**/小红书短视频矩阵内容分发，基于 playwright | 与半成品同栈（playwright），矩阵分发+选择器维护思路可复用 |
| | `toki-plus/video-mover` | Python / 573★ | 全自动搬运：自动下载→去重→AI 标题+标签→上传，可拓展至视频号 | **与「自动收集素材+素材优化」链路高度吻合**——去重/AI文案/多平台上传一条龙，MIT |
| | `hanliang97/MatrixMedia` | JS/Electron / 738★ | 视频矩阵批量发布（含视频号），Vue+electron+puppeteer | 前端控制台形态参照 |
| **AI 电商 Agent（综合类比）** | `whichmen/dxl-commerce-agent` | Python / 114★ | OpenClaw + 大模型驱动的电商客服自动化：覆盖淘宝/拼多多/抖音/快手/小红书/**视频号**，含浏览器/手机 Worker、订单物流售后工具、记忆、回执、恢复、Eval | 与本项目「AI 决策层+执行层+人工闸门」架构理念最接近；idempotency/playwright/FastAPI 栈一致，MIT —— 值得仔细拆解其一做对比验证（Memory/Eval/Recovery） |
| **微信小店 OpenAPI 封装** | （未搜到可用封装） | — | GitHub 上 `wechat channels shop api`/`微信小店 openapi` 均为 0~低质量结果 | **证实 01 文档结论：无成熟开源封装，需自写薄封装**（签名 SHA256 + 时间戳窗口 + 幂等重试 + 配额队列），约几百行 |

### 关键结论
1. **素材链路有成熟开源可复用**：视频号下载 = `lx_t0aa/wx_channels_download` 或 `res-downloader` 的范式；去重+AI文案+多平台上传 = `video-mover` 的架构。**不要闭门造车，踩在 `video-mover` 的「下载→去重→AI→上传」管线骨架上二开。**
2. **上架双轨制依然成立**：微信小店官方 OpenAPI 无封装需自写；Playwright 兜底参考 `social-auto-upload` 的视频号模块（它已实现视频号上传，可直接借鉴而非从零写 181KB）。
3. **投放（小店托管）GitHub 无任何开源**：仍是 Playwright UI 自动化 + 自研止损/预算引擎，属本项目护城河，无包袱从零建。
4. **被污染的检索坑**：`视频号小店` 关键词会混入图书垃圾仓库（如 `Dujltqzv/Some-Many-Books`），忽略之。
5. **视频号加密解密是独有壁垒**：`Evil0ctal` 的解密思路解决的是「本地有视频号缓存文件但加密读不出」——若走「商机中心/本地缓存」采集路线则必要；若走「分享链接在线解析」则绕开。

---

## 二、可用 Skills 盘点 → 与本系统各模块的匹配

当前会话可加载的 skills 中，与本项目直接相关的：

| Skill | 能力 | 对应本项目模块 | 落地动作 |
|---|---|---|---|
| `playwright` | Playwright 浏览器自动化、stealth、反bot、认证会话、截图 | 上架兜底 / 小店投放(商品托管) / 采集兜底 | 开发兜底与投放脚本书写时先加载，避免重复踩选择器维护坑 |
| `e2e-testing` / `e2e-testing-patterns` | E2E 测试架构、POM、网络 mock、认证 | 半成品已有 1093 测试，新仓库回归基线 | 新仓库搭建测试分层时用，参考半成品测试架构 |
| `sqlite-data` | SQLite 持久化/查询/migration | M0 起步阶段（尚未迁 PG 前） | 但 M4 目标迁 PostgreSQL——仅起步期用 |
| `openapi` | OpenAPI 3.1 规格、代码生成 | **微信小店 OpenAPI 薄封装层** | 用 OpenAPI 规范定义 channels 契约，生成客户端骨架，比手写签名代码更稳 |
| `better-auth` | 自托管鉴权框架 | 管理后台鉴权（半成品无鉴权是真风险） | 补上鉴权，替换当前 CORS-only 开放 API |
| `pino-logging` | 结构化 JSON 日志 | 调度/监控/告警链路 | 错误分类码 + 审计留痕升级为结构化日志 |
| `ci-cd-architecture` | CI/CD、GitHub Actions、OIDC、Docker | 新仓库 CI（测试回归/构建镜像/私有化部署） | 建 Actions：测试+lint+镜像；密钥走 secrets |
| `archify` | 架构/流程图生成 HTML 可视化 | 方案文档可视化（05 架构图等） | 出架构/数据流图方便评审 |
| `modlens` | 图片视觉识别 | 素材审核工作台（图片审核） | 若审核要识别图像内容可接入 |

> 说明：这些 skills 是「任务明确且匹配时加载的指令集」，不是运行时依赖。新仓库落地时会按模块挂载对应 skill 的规范。

---

## 三、独立新仓库立项方案（待讨论定稿）

### 3.1 仓库定位与边界
- **新仓库名建议**：`channels-shop-automation`（如要私有化部署再改）。
- **复用策略**：从现有半成品只「挑选复制」四件套，其余从零建：
  1. `sourcing_scheduler.py` 范式（来源账本/节流/熔断/断点恢复）→ 重写为进程化
  2. `workflow_runner.py` 队列范式（失败隔离/人工接管/错误分类码）→ 重写为独立执行器
  3. `listing_gate.py` / `compliance.py` / `pricing.py` 业务规则 → 直接搬（含测试反推）
  4. `app.db` 快照数据 → 抽出 schema 作为种子
- **丢弃不带走**：181KB 待维护 Playwright 脚本（用 `social-auto-upload` 视频号模块替换）、SQLite 单库、daemon 线程调度器、CORS 全开。

### 3.2 分层与模块边界（微调 03 架构，体现独立重构）
```
apps/
  api/        FastAPI 薄网关 + 鉴权(better-auth) + OpenAPI 契约
  worker/     独立进程调度器 + WorkflowJob 执行器（失败隔离）
  web/        React 控制台（选品/素材/上架/托管/看板）
domains/
  sourcing/   选品采集+打分（复用规则，加投放转化维度）
  media/      素材收集(video-mover骨架) + ffmpeg 优化 + 审核
  listing/    上架引擎：wechat_openapi 主链路 + playwright兜底
  ads/        小店投放·商品托管 + 止损/预算引擎（从零，护城河）
libs/
  adapters/   微信小店 OpenAPI 薄封装（openapi 生成骨架）
  ops/        结构化日志(pino) / 配置 / 幂等 / 重试 / 限额队列
```

### 3.3 技术栈（较 03 微调）
| 层 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.12（API/worker）+ TS(React) | 复用半成品规则/测试基线；生态丰富 |
| 存储 | Postgres + MinIO + Redis | M0 就直接 PG 起步，跳过 SQLite 阶段 |
| API 契约 | OpenAPI 3.1 定义 channels 封装 | `openapi` skill 生成客户端，签名规范 |
| 鉴权 | better-auth | 替换 CORS 全开 |
| 日志/监控 | pino + 告警看板 | 半成品教训：无观测 |
| 视频 | ffmpeg + moviepy（9:16 二创） | 已装 ffmpeg 9.0.1 |
| AI | DeepSeek 文案/复核 + Kimi/Wan 生图 + ffmpeg | 半成品已验证 |
| 上线 | GitHub Actions + Docker Compose | `ci-cd-architecture` skill |

### 3.4 里程碑（以独立仓库落地为序）
- **W1 骨架**：Postgres/Redis/MinIO 起；OpenAPI 契约；鉴权；CI（测试+镜像）跑通
- **W2 素材链路**：video-mover 骨架二开 → 视频号下载+去重+ffmpeg 标准化
- **W3 上架双轨**：wechat_openapi 薄封装（mock→live 就绪即切换）+ 兜底换 social-auto-upload
- **W4 投放托管**：shop_ads 从零（添加托管→设ROI→绑素材→报表回读→止损/预算）
- **W5 数据回流**：成交 ROI 写回选品/素材评分，闭环
- 每个里程碑带验收门禁（沿用 11 的「就绪即启用」mock/live 双模式）

### 3.5 三个待你拍板的点
1. **投入素材采集路线**：走「在线分享链接解析」（绕开解密，简单）还是「本地缓存+解密」（`Evil0ctal` 思路，强但复杂）？影响素材链路设计。
2. **是否保留管理前端控制台**：若单人/少人用，React 控制台可精简为「看板+人工闸门」最小集，省时间。
3. **公开/私有**：建议建仓即 Private（半成品文档里已是待办）。商业方案不宜 public。

---

## 四、下一步
你确认上面 3 个拍板点 + 里程碑范围后，我就按「W1 骨架」开始拆解任务并动工。此文档可作为新仓库的 `docs/立项.md` 入库，GitHub 对比结论入库为 `docs/research/github-comparison.md`。