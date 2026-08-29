# M3 自动素材优化 · 进度看板（progress）

> 由总工程师持续维护。迭代版本号规则：每次重要返工/改版 +0.1（v1.0 → v1.1）。

## 当前迭代：v1.1（迭代阶段，总控已确认方向）

> 总控 2025 体系建立日确认 v1.1+ 迭代方向：①M5 回写联调（data-audit 联动，评估标签回流消费）——**已完成（v1.1-①）**；②模板重训练数据驱动（样本闸门已就绪）；③上传真实化（用户提供小店账号后）；④真实 ffmpeg 验证（环境就绪自动启用）。依赖用户侧环境的两项（③④）列入待确认清单。

| 任务 | 负责 | 进度 | 剩余工作 |
|---|---|---|---|
| [x] 阅读设计文档（06/09/10/11/03/05）+ 撰写任务书 | 总工 | 100% | 无（brief.md 已交付） |
| [x] 风险预判（LLM 密钥配额/ffmpeg 硬规格/生图拒审/合规/评估回流/上传方式） | 总工 | 100% | 无（risks.md 已交付） |
| [x] 数据字典 + 跨模块契约（context/） | 总工 | 100% | 无（context/README.md + data-requests.md 已交付） |
| [x] 数据库 Schema 规划（opt_*） | 总工 | 100% | 无（database/README.md 规划稿） |
| [x] 公共骨架：backend/optimization 包（config/db/tables/models/compliance）+ fixtures 样本 | 总工 | 100% | 无（骨架已建，供子代理使用） |
| [x] 文案管线 + 规则预审扩展（v0.2） | 子代理-A（验收通过） | 100% | 无（copywriting 子包 + 27 用例全绿） |
| [x] 主图/详情图管线（v0.4） | 子代理-B（验收通过） | 100% | 无（images 子包 + 38 用例全绿，含 P-011 加固修复） |
| [x] 视频二创流水线（v0.3） | 子代理-C1/C2（验收通过） | 100% | 无（video 子包 + 66 用例全绿） |
| [x] 审核闸门 review（v1.0-1） | 子代理-D（验收通过） | 100% | 无（review 子包 5 文件 + 测试通过） |
| [x] A/B 闭环 ab（v1.0-2） | 子代理-E（验收通过） | 100% | 无（ab 子包 6 文件 + 64 用例全绿） |
| [x] 上传素材库 upload（v1.0-3） | 子代理-F（验收通过） | 100% | 无（upload 子包 7 文件 + 测试通过） |
| [x] 端到端集成测试（v1.0-4） | 总工（集成验收） | 100% | 无（test_optimization_e2e.py 2 用例；修复集成缺口：VideoVariantRepo 回填） |
| [x] **M5 回写联调（v1.1-①）** | 总工（联调验收） | 100% | 无（ab/ingest.py 摄取入口 + test_optimization_m5_integration.py 5 用例全绿；全量 1021 passed 无回归） |
| [x] **模板重训练数据驱动（v1.1-②）** | 总工（验收通过） | 100% | 无（test_optimization_retrain_driven.py 2 用例：摄取→retrain_all→stats/类目记忆落库→best_template 决策；修复 retrain.best_template_for_category 空 stats 误选缺陷） |

## 里程碑进度

- 本模块当前完成度：**95%**（v1.0 全链路 90% + M5 回写联调 v1.1-① + 模板重训练数据驱动 v1.1-②）
- 已达成：v1.0 全链路闭环 + **M5 回写联调**（ingest 摄取，金额分→元/ROI 换算/中文诊断/unmatched 隔离/幂等）+ **模板重训练数据驱动**（M5 回写摄取 → retrain_all → stats/类目记忆落库 → best_template 决策；样本闸门 min_samples、空日不计样本；M3 全范围 **305 passed, 1 skipped** 全绿）
- 剩余：③④ 依赖用户侧环境（上传真实化待小店账号 / 真实 ffmpeg 待环境安装，待确认清单）

## 后续排期（v1.1+ 迭代任务包）

| 顺序 | 任务包 | 前置 | 说明 |
|---|---|---|---|
| 1 | M5 投放效果回写联调（EvaluationService ↔ M5 报表快照） | M5 数据层就绪 | 经 data-audit 数据联动，总控协调 |
| 2 | 模板参数按类目重训练数据驱动（ab.retrain ↔ opt_templates/opt_category_memory） | 回写数据积累 | 样本 <5 不更新的闸门已实现 |
| 3 | 上传真实化（ApiUploader 接口契约实测 + Playwright UI 兜底 + 半自动） | 用户提供小店账号 | REC-002 契约替换点已预留 |
| 4 | 真实 ffmpeg 出片验证（FFmpegProcessRunner + skipif 用例启用） | 环境安装 ffmpeg | 无需改代码，环境就绪自动启用 |
