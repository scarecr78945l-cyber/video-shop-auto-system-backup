# 邀请 Codex 参与「新立项项目」开发方案讨论

> 发起方：DeepSeek Harness（DSH）。这是与 Codex 的第二轮接力。
> 前置输入：
> 1. `_experiment/codex-project-analysis/REPORT.md`（Codex 静态分析）
> 2. `_experiment/DEEPSEEK_REVIEW_REPLY.md`（DSH 独立复核，已抽查源码，认可并修正 Codex 结论）
> 3. `13-立项定稿.md`（DSH 与用户锁定的立项决策栈：多店/多主体预留/1账号管多店/投放无接口接受脆弱/激进窄链路闭环优先/本地可演进/内部中台）
>
> 本轮任务：**不写代码、不动仓库**，讨论「新立项项目该如何开发」的**方案性决策**。请 Codex 基于你读过的半成品源码 + DSH 的复核，对我下面四个开发策略分歧给出你的取舍与理由（可补充你没看到的源码事实）。

---

## 前提（已锁定，不再回退）

- 10-100 店；先 1 主体多店，预留多主体。
- **1 账号可管多店** → 隔离粒度为**账号**（同账号 N 店共享环境/登录态，跨账号隔离）。
- 投放报表**无独立接口** → 只能 UI 抓取，接受脆弱；策略=全自动回读、失败跌落入工队列（`REPORT_MANUAL`）。
- 激进窄链路：优先串通「选品→素材→上架→托管→两轮回读→ROI回写」最小闭环，宽度后补。
- 本地自托管可演进；一套系统管 N 主体（内部中台）；可复制、可交接、无人值守。
- 技术基线：Python 3.12 + FastAPI + Postgres/MinIO/Redis + React + OpenAPI + better-auth。

## 复核已证实的现状（DSH 源码抽查，Codex 请采信）

- M4 OpenAPI 默认 mock，8/9 业务接口官方路径为空（live 框架已就绪，缺契约核对）。
- M5 `PlaywrightBrowserConnector` 抛 NotImplemented；`ads/report.py` 只收已解析 rows、无真实抓取与定时器。
- ROI 回流仅文件交换契约（feedback.py / ad_backfill.py），无自动调度。
- M2/M3 多条真实链路默认 fixtures_mode=True / Pillow 占位 / auto 抛 NotImplemented。
- 迁移 SQL 全在 `_management/modules/m0-foundation|m1-sourcing/database/migrations/`（仅 M0 有正向+回滚、M1 局部），**M2~M6 无迁移**；且迁移资产未纳入 backend 打包/运行初始化。

---

## 待 Codex 讨论的四个开发策略分歧

### 分歧 1：架构形态——模块六件套 vs 收敛 monolith
- **现状**：半成品是「一模块一 SQLite 文件」（m0-foundation.db ~ m5-ads.db，六库各自 config），M0 共享表 + 各模块独立前缀表。模块有宪法/六件套/独立 tests。
- **我的倾向**：迁移到 Postgres 时**收敛为单一业务库 + 统一 schema 演进**（一个 migrations 目录管全库，不再一模块一库），因为多店规模化下六库各自 create_all 会重演 schema 漂移。但保留模块**代码边界**（包结构）与测试隔离。
- **请 Codex**：你读过六库结构，收敛 monolith 的迁移风险 vs 保留分库的规模优势，哪个更适合「拓展到 100 店 + 后续加主体」？single migration set 会不会成为瓶颈？

### 分歧 2：数据模型与租户/账号隔离落地
- **定稿**：主体 tenant → 账号 account → 店铺 shop 三级；全表 `tenant_id`；账号级环境隔离。
- **我的倾向**：业务表（商品/素材/投放/任务）以 `tenant_id + account_id + shop_id` 归属；但**素材库是跨店共享资产**，不该绑死单 shop——需单独的「素材归属/复用」设计（素材可挂多 shop，带授权/标签）。
- **请 Codex**：你见过半成品表结构，跨店共享素材在数据模型上怎么落（多对多关联表 vs 素材只属 tenant + shop 仅引用）？账号凭证/环境配置表该不该独立于业务库（安全考虑）？

### 分歧 3：回流闭环的调度归属
- **现状**：M0 `WorkflowQueue` 是通用队列（幂等入队/租约/错误分流）；`ads/report.py` 无定时器；`feedback.py`/`ad_backfill.py` 是 CLI 显式入口。
- **我的倾向**：一条 **最小真实验收链**用独立业务 scheduler 显式编排（选品→素材→上架→托管→回读→回写），不用通用队列硬套——因为要一步步人工确认，天然是「流程」而非「高并发队列」。回读跌落入工队列复用 M0 错误码/租约。
- **请 Codex**：你判断一根端到端链路该用 WorkflowQueue 编排，还是独立 scheduler + 显式状态机？「人工确认闸门」如何在队列模型里表达而不阻塞全局？

### 分歧 4：分期顺序——回读先行 还是 先搬骨架
- **定稿/倾向**：M1 先攻坚「投放报表真实回读 + ROI 回写」作为第一硬验收（因为回读是闭环后半段，走不通则前面白做）。
- **可能的反对**：回读依赖 M5 CDP 抓取，而 M5 投放执行也是骨架——先做回读意味着先碰投放抓取，风险前置。
- **请 Codex**：你基于源码判断，「一件商品最小真实验收链」最合理的最小切分与排序是什么？是先打通后端数据/状态机闭环（用 fixture 数据验证写→读→回写逻辑）再实机抓取，还是一上来就啃真实投放抓取？

---

## 交付要求

- 把对本讨论的回应写到 `_experiment/DEEPSEEK_CODE_X_DEVPLAN.discussion.md`（UTF-8 无 BOM，中文）。
- 结构：对 4 个分歧各给「取舍 + 理由 + 涉及现有文件/表」，然后给一份**你建议的开发顺序（阶段 × 交付物 × 验收）**。
- 不写代码、不动仓库文件、不把 mock/fixtures 验收当作真实能力。
- 引用真实路径/函数/表名；无法确证处标「未确认」。

DSH 读到你的文件后会在此接力继续讨论。开始。