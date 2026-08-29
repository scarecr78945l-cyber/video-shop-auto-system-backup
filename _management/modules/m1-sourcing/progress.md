# M1 自动选品 · 进度看板（progress）

> 由总工程师持续维护。迭代版本号规则：每次重要返工/改版 +0.1（v1.0 → v1.1）。
> 更新：体系建立日（总控裁决 REC-006/007/008 已落 + 批次 1 已派发）｜ 当前迭代：**v0.1（筹备完成 → S1 开发中）**

## 当前任务看板

| 任务 | 负责 | 进度 | 剩余工作 |
|---|---|---|---|
| [x] 通读宪法/踩坑日志/设计文档(04/09/10/11/03)/基线代码 | 总工 | 100% | 无 |
| [x] 撰写 brief.md（任务书：目标/边界/复用vs新增/里程碑/待决事项） | 总工 | 100% | 无 |
| [x] 撰写 risks.md（风险预判 R-01~R-54，六域全覆盖） | 总工 | 100% | 无 |
| [x] 撰写 context/README.md（数据字典+五维字段+M5/M4 契约草案） | 总工 | 100% | 无 |
| [x] 撰写 context/data-requests.md（跨模块数据需求登记） | 总工 | 100% | 无 |
| [x] 撰写 database/README.md（现有表+新增 m1_ 投放转化表 DDL） | 总工 | 100% | 无 |
| [x] 基线测试回归验证（39 passed，`--basetemp=".pytest-tmp"`） | 总工 | 100% | 无 |
| [x] BLOCKER-001/002/003 总控裁决（REC-006/007/008）+ 04/03 文档口径同步 | 总工 | 100% | 无 |
| [x] S1a 基线改造+DSN 切换（config/db/README） | 子代理 32dfb48b | 100% | ✅ 验收通过（186 passed, 1 skipped） |
| [x] S1b 打分扩展+白名单接线+m1 表（tables/pipeline/迁移/测试） | 子代理 58579182 | 100% | ✅ 验收通过（sourcing 62 passed；全量 331 passed / 4 failed 均为 M0 foundation 既有问题） |
| [x] S2 投放转化回写：`ad_backfill.py` + CLI `ad-sync` + 单测 | 子代理 3e6fd497 | 100% | ✅ 验收通过（sourcing 域 85 passed 串行复跑；子代理自测全量 417 passed, 1 skipped） |
| [x] S3a 探测+选择器校准（fixtures 对照，page_changed 单测） | 子代理 00389792 | 100% | ✅ 验收通过（91 passed；selector-log.md A1~A6 建议登记） |
| [ ] S3b 校准动作实施（A1 config.selectors 迁移 / A2 有米云日期动态化 / A3 飙升榜 fixtures / A4 动态列定位） | 子代理 45e06cf4 | 已派发（中断 1 次，断点恢复中；A3 fixtures 已落盘） | 待完成验收 |
| [ ] S3c 真实采集联调（三源真实入库 ≤50/源、节流熔断观察、日志脱敏、fixtures 对照、验证码即停） | 子代理 c73de00e | 已派发 | 执行中，待验收 |
| [ ] S4 联调与验收：M4/M5 交换联调、日有效候选≥200 度量、打分可解释抽查 | 总工 | 0% | 全部 |
| [ ] S5 迭代：闸门放松、LLM 复核（可选）、PostgreSQL 迁移配合 | 总工 | 0% | 全部 |

## 里程碑进度

- 本模块当前完成度：**30%**（筹备 + S1a/S1b/S2/S3a 验收通过 + fixtures 全链路 e2e 验证通过；S3b 待派发）
- 距离目标还差：S3b 校准动作 → S3c 真实采集（登录态）→ S4 联调验收 → S5 迭代
- 里程碑达成（S1+S2+S3a）：① 配置化——类目白名单 app_config 运行时接线（e2e 验证：白名单外类目转 manual_review）；② 库——默认 DSN 切 `backend/data/db/m1-sourcing.db`，m1_ 投放转化两表可建；③ 投放转化第 5 维数据闭环——ad_backfill 幂等导入（e2e：4 类目导入+重复导入 upserted 不重复）+ 新鲜度/弱样本过滤；④ **选品全链路可测可跑（fixtures 模式）**——run-pipeline 采集 23→入池 TopN，投放转化维度生效，二次运行去重幂等；⑤ 选择器校准基线——selector-log.md（5 来源+A1~A6 建议）+ page_changed 单测 6 例

## 后续排期（可拆子代理的任务）

| 任务 | 建议拆分 | 子代理职责 | 前置 |
|---|---|---|---|
| S1a 库路径+app_config 接线 | 1 子代理 | 改 config.py 默认 DSN、pipeline 注入 app_config 白名单、补单测 | 无 |
| S1b m1 表 DDL+迁移脚本 | 1 子代理 | 建 `m1_ad_conversion_cache/ingests` 表 + migrations/ + 幂等测试 | 无 |
| S2 ad_backfill | 1-2 子代理 | 交换文件解析/校验/幂等导入/新鲜度判定 + 单测 + CLI `ad-sync` | S1b |
| S3 真实采集联调 | 1 子代理 | 共享 Chrome 三源实测、fixtures 刷新对照、page_changed 证据样例 | 登录态就绪（总控/用户） |

> 子代理任务书必须自包含（宪法第 9 节）：输入/输出路径、验收标准、P-001 测试命令、禁 git/禁明文密钥。

## 开发阶段管理方式（总控已确认 · 体系建立日）

1. 本模块总工拥有独立会话，全权管理模块开发全流程（需求→设计→排期→分派→集成→验收→迭代）。
2. 开发任务一律由总工在会话内用 `subagent` 创建子代理执行（**每任务一个子代理**，任务书自包含：背景/目标/输入输出路径/验收标准/宪法要点）；总工不批量自写代码，只负责架构设计、任务拆解、进度管理、验收与集成。
3. 子代理完成后总工必须验收（读产出、跑测试，pytest 一律 `--basetemp=".pytest-tmp"`），验收不合格退回修改。
4. 子代理阻塞先由总工判断；判断不了 → 写 `BLOCKERS.md` 结束回合，总控回复后继续。
5. 子代理产出与问题登记 `agent-activity.md` 与 `BLOCKERS.md`（如有）。

## 可拆子代理任务排期（待总控批准后派发）

**批次 1（S1+S2，不依赖登录态，可先行）**
| 任务包 | 子代理 | 交付物 | 验收标准 |
|---|---|---|---|
| S1a 库路径+app_config 接线 | 子代理-1 | config.py 默认 DSN → `sqlite:///data/db/m1-sourcing.db`；pipeline 注入 app_config 白名单；backend/README 同步 | 既有 39 测试 + 新增单测全绿；后台改白名单下一轮打分生效 |
| S1b m1 表 DDL+迁移脚本 | 子代理-2 | `m1_ad_conversion_cache`/`m1_ad_conversion_ingests` 建表 + `database/migrations/` 幂等脚本 + 单测 | 建表幂等可重入；唯一键防重复导入 |
| S2 ad_backfill | 子代理-3 | `ad_backfill.py`：交换文件解析/校验/幂等导入/新鲜度判定（>7 天视为无数据）+ CLI `ad-sync` + 单测 | fixtures 与假交换文件双通道验证；无文件优雅降级（维度不生效不报错） |

**批次 2（S3，依赖登录态与 BLOCKER-001/003 裁决）**
| 任务包 | 子代理 | 交付物 | 验收标准 |
|---|---|---|---|
| S3 真实采集联调 | 子代理-4 | 共享 Chrome 三源实测各 ≥1 轮真实入库；选择器校准记录；`page_changed` 证据样例；fixtures 刷新对照 | 三源真实数据入库成功；日志脱敏；节流/熔断可观测 |

> 批次 1 前置：BLOCKER-002 裁决（默认 DSN 修改授权）。批次 2 前置：BLOCKER-001（第三源口径）、BLOCKER-003（M5 回写契约）与登录态就绪。
