# M1 自动选品 · 模块任务书（brief）

> 模块 ID：`m1-sourcing` ｜ 总工程师：M1 总工 ｜ 版本：v1.0
> 依据文档：`04-自动选品模块设计.md`、`09-数据模型与任务编排.md`、`10-风险合规与风控清单.md`、`11-里程碑与落地路线.md`、`03-系统总体架构设计.md`、`backend/README.md`
> 状态：**筹备阶段已完成，进入排期与开发阶段**

## 一、模块目标

一句话：**三源采集 → 去重 → 合规三态 → 数据补全 → 五维打分（含投放转化）→ TopN 入商品池**，为 M4 上架提供高质量候选商品，并通过 M5 托管转化数据回流持续校准「投放转化」维度，形成「选品→上架→投放→回写→再选品」的自我进化闭环。

## 二、范围与边界

### 负责（本模块内）
1. 三源采集：视频号商机中心（`opportunities`）/ 有米云（`youmi`）/ 抖店电商罗盘（`doudian`，基线已实现，与 04 文档「考古加」存在口径差异，见下方待决事项）——Playwright 共享 Chrome CDP，选择器全配置化。
2. 去重：`image_phash` + `source_core_attributes_hash` + 多榜/多源合并。
3. 合规三态：`hard_reject / candidate / manual_review`（复用 `compliance.py`，标题清洗、品牌/禁售/功效词过滤）。
4. 数据补全：1688 以图搜款 + 订单确认页逐 SKU 询价（不下单）、淘宝同款参考素材收集。
5. 五维打分：热度趋势 35 / 利润率 30 / 售后风险 20 / 供给稳定 15 / **投放转化（新增，权重可配，默认 10，无数据时折入其他四维）**，打分理由逐条可解释。
6. 排序取 TopN → 商品池（`products.state=pool`），人工复核闸门 `manual_review → pool`。
7. 调度器：账本 / 节流 0~4 级 / 熔断探针 / 实时榜降频 / 断点续跑（进程化）。
8. 类目白名单配置化：`config.category_whitelist` + `app_config` 表运行时覆盖（**基线未接线，需补**）。
9. 模块数据库 `backend/data/db/m1-sourcing.db` 的建表、迁移与维护。

### 不负责（边界外）
- ❌ 素材收集（M2）、素材优化（M3）——本模块只产出「淘宝参考素材 URL」供 M2 消费。
- ❌ 上架执行（M4）——本模块只提供商品池与字段契约；`listing_upload` 队列由 M4 编排。
- ❌ 投放执行与报表（M5）——`ad_report_snapshots` 表归 M5 所有，本模块**只读回写结果**（经数据交换文件），不建同名表。
- ❌ 生图/图片审核（M3 范围）、定价最终策略（本模块只算建议售价，最终定价 M4 校验）。
- ❌ 任何 git 操作、其他模块库文件读写、浏览器登录态管理与分发。

### 依赖其他模块
| 依赖 | 内容 | 方式 |
|---|---|---|
| M0 基座 | 共享 Chrome（CDP）、`app_config` 配置约定、WorkflowJob 错误码体系 | 环境变量/配置 + 共享表只读 |
| M5 投放 | 类目级托管 ROI/成交额回流（`ad_report_snapshots` 聚合结果） | 数据交换文件 `_management/data-exchange/m5-ad-conversion.json`（见 context） |
| M4 上架 | 商品池消费方（我提供 → M4 读） | 数据交换文件 `m1-pool-*.json` 或只读视图（由总控裁定口径） |
| M2 素材 | 淘宝参考素材 URL 交接 | `products.ad_conversion`/证据表 + 交换文件 |

### 对外提供
1. 商品池（`products` 表，`state=pool`）→ M4 上架。
2. 类目级「投放转化」历史数据消费接口（打分输入）——由 M5 回写驱动。
3. 打分理由（`score_breakdown` JSON）→ 管理后台展示与审计。
4. 采集账本/熔断状态（`source_*` 表）→ 总控 dashboard 监控。

## 三、基线复用 vs 新增（关键结论）

### 可复用（基线已实现，39 测试覆盖，仅需小修/接线）
| 组件 | 现状 | 需要做的 |
|---|---|---|
| `config.py` | 三源+询价源+打分权重全配置化；`ad_conversion_weight=10` 已存在 | ①默认库地址改为 `sqlite:///data/db/m1-sourcing.db`；②`ad_conversion_by_category` 增加「真实数据加载入口」 |
| `models.py` | `SourceItem/ProductCandidate/ScoreBreakdown/ScoreDimension/Quote` 完整 | 基本不动；如需 M5 契约字段扩展先评审 |
| `scoring.py` | **投放转化维度已实现**：无数据 `active=False` → 权重折入四维（和=100） | 增加「数据新鲜度」维度：ROI 快照过期 >N 天应视为无数据（防陈旧回写污染打分） |
| `compliance.py` | 三态 + 标题清洗 + 白名单（构造入参可注入） | **接线 app_config**：运行时白名单优先读 `app_config`（`repo.get_config_value`） |
| `dedup.py` | phash + 属性指纹 + 多源合并 | 不动 |
| `pipeline.py` | 全链路编排 + 持久化 | ①live 模式投放转化数据改为从「M5 交换文件/app_config」加载（替代空配置）；②app_config 白名单传入 `ComplianceEngine` |
| `scheduler.py` | 账本/节流/熔断/降频/断点 | 不动（进程化部署由总控/运维排期） |
| `collectors/*` | 商机中心/有米云/抖店罗盘/1688/淘宝 + fixtures 离线 | 维护性工作：选择器校准、`page_changed` 证据 |
| `cli.py` | 命令行全套 | 增加 `ad-sync`（导入 M5 回写）命令 |

### 需新增（本轮开发）
| 新增项 | 说明 | 验收 |
|---|---|---|
| **M5 回写接入器** `ad_backfill.py` | 读取 `_management/data-exchange/m5-ad-conversion.json`（或 app_config 指定路径）→ 校验/幂等导入 → 更新 `m1_ad_conversion_cache` | 幂等可重入；快照时间戳可审计；无文件时优雅降级（维度不生效） |
| **投放转化本地缓存表** `m1_ad_conversion_cache` | 类目级 ROI/成交额 + 快照期 + 样本数 | 见 `database/README.md` DDL |
| **app_config 白名单接线** | 运行时读 `app_config.category_whitelist` → 注入 `ComplianceEngine` | 后台改白名单 → 下一轮打分生效，有单测 |
| **真实采集接入验证** | `launch-browsers`/`probe-browsers`/`collect --mode auto` 全链路实测（共享 Chrome CDP 9223/有米云 9555） | 三源各 1 轮真实采集，结果入库，日志脱敏 |
| **考古加 vs 抖店罗盘口径决策落地** | 见待决事项 D-1 | 总控决策后执行其一 |
| **打分数据新鲜度** | 投放转化数据过期判定（默认 7 天） | 单测覆盖 |

### 待决事项（需总控/用户决策，已列入 BLOCKERS/decisions 跟踪）
- **D-1**：04 设计文档三源为「考古加/有米云/商机中心」，基线实现为「抖店电商罗盘/有米云/商机中心」（考古加采集器未实现）。选项：①按设计补考古加采集器（成本高，登录态+五榜单选择器）；②以抖店罗盘为正式第三源并更新 04/03 文档；③两者并存（考古加为可选第四源）。**倾向 ②**（基线已实测打通，风险最低）。
- **D-2**：本模块库地址 `backend/data/db/m1-sourcing.db`（任务指定）与基线默认 `sourcing.db` 的关系：建议**基线默认值直接改为新路径**（`init-db` 建新库），旧库数据不做迁移（开发期无生产数据）；如总控要求保留旧库兼容，则默认值不动、仅文档说明。**倾向改默认值**。

## 四、交付物清单

| 交付物 | 验收标准 |
|---|---|
| `brief.md`（本文件） | 总控评审通过 |
| `risks.md` | 覆盖任务书指定风险域，每条有应对方案 |
| `context/README.md` + `context/data-requests.md` | 数据字典/契约可与 M5/M4 对齐，字段口径明确 |
| `database/README.md` | 现有表 + 新增投放转化表 DDL + 迁移记录 |
| `progress.md` | 实时反映完成度/剩余/子代理拆分 |
| 代码：`ad_backfill.py` + app_config 接线 + db 路径调整 | 新增单测全绿 + 既有 39 测试回归通过（`--basetemp=".pytest-tmp"`） |
| 真实采集联调记录 | 三源真实采集 ≥1 轮成功入库，证据 JSON 留痕 |
| 跨模块契约（M5 回写 / M4 出池） | 经总控确认口径，登记 `data-audit.md` |

## 五、里程碑拆解（对齐 11 文档 M2 阶段，细化到本模块）

| 阶段 | 任务 | 迭代版本 | 完成标准 |
|---|---|---|---|
| S0 筹备 | 通读文档/基线、写任务书/风险/字典/库规划 | v0.1 | 本回合交付 4+2 文件，总控验收 |
| S1 配置与库 | db 路径调整、app_config 白名单接线、m1 新表 DDL 落地 | v0.2 | 39+新增测试全绿 |
| S2 投放转化回写 | `ad_backfill.py` + 数据新鲜度 + fixtures→live 双通道 | v0.3 | 幂等导入单测 + 无数据降级验证 |
| S3 真实采集 | 共享 Chrome 三源实测、选择器校准、`page_changed` 证据 | v0.4 | 三源各 ≥1 轮真实入库，节流/熔断可观测 |
| S4 联调与验收 | 与 M4/M5 数据交换联调、日有效候选 ≥200 度量、打分可解释性抽查 | v1.0 | 对齐 04 第五节验收标准（去重率/拦截率/询价成功率/同款匹配率可观测） |
| S5 迭代 | 人工闸门放松策略、LLM 复核（可选）、PostgreSQL 迁移配合 | v1.1+ | 按 11 文档 M4 阶段数据回流验证 |

## 六、纪律与约束（本模块强制）
1. 禁止 git 命令；备份由总控执行。
2. 只操作本模块库 `backend/data/db/m1-sourcing.db`；共享表（`app_config`）只读。
3. 任何 md/代码/日志禁止明文密钥/Token/Cookie；日志走 `_redact_text` 脱敏。
4. pytest 一律 `--basetemp=".pytest-tmp-m1"`（P-001 + P-011/宪法第 12 节：独立 basetemp；全量回归由总控统一执行）。
5. 新增表一律 `m1_` 前缀；跨模块数据走 `data-audit.md` 审计 + `_management/data-exchange/` 交换文件。

## 七、实现快照（v1.0 收官 · 体系建立日）

**选品全链路可测可跑（fixtures + 真实采集双通道）**，sourcing 域 **108 passed**（`.pytest-tmp-m1`）。

| 能力 | 实现位置 | 状态 |
|---|---|---|
| 三源采集 | `collectors/{opportunities,youmi,doudian}.py`（CDP 9223 共享/9555 有米云） | ✅ 真实采集打通（101 条入库，s3c.db 留证） |
| 去重 | `dedup.py`（sha256 指纹 + phash + 多源合并） | ✅ 既有+回归 |
| 合规三态 | `compliance.py` + app_config `category.whitelist` 运行时接线（REC-010） | ✅ 测试覆盖 |
| 数据补全 | `collectors/{alibaba,taobao}.py`（1688 询价/淘宝素材） | ✅ fixtures 可测；真实待实测（A6） |
| 五维打分 | `scoring.py`（投放转化维度无数据权重折入四维） | ✅ e2e 生效验证 |
| 投放转化回写 | `ad_backfill.py` + `m1_ad_conversion_cache/ingests` + CLI `ad-sync` | ✅ C-2 会签（M5 侧互认） |
| 调度器 | `scheduler.py`（账本/节流/熔断/降频/断点） | ✅ 既有+回归 |
| 选择器校准 | `context/selector-log.md` v1.1（5 来源 + A1~A6 + 三源实测） | ✅ A1/A2/A4 落地，A5 实测确认，A3/A6 待 v1.1+ |
| 库 | `backend/data/db/m1-sourcing.db`（REC-007）+ 幂等迁移脚本 | ✅ |

**v1.1+ 迭代项**：A3 飙升榜 URL、A6 图片/宽泛选择器收敛、商机中心多筛选、9223 僵尸页清理（P-016）、S4 联调（日有效候选≥200 度量）、S5（闸门放松/LLM 复核/PostgreSQL）。
