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
| [x] **素材相关性门（REC-迁移-03 C3，M3 侧 · v1.1-③）** | 门禁迁移子代理（验收待总工） | 100% | 无（review/relevance.py：Qwen-VL 判定接口抽象 + mock 判定器 + 前 15 秒抽帧 + StyleClusterer 款式聚类；gate.py 新增 RelevanceGate，gate_type=relevance，related→passed/unrelated→rejected/multi_style→manual_review；`review/__init__.py` 已导出；test_optimization_review.py 22 用例全绿；M3 全量 **327 passed, 1 skipped** 零回归；Qwen-VL 真实模式待 API 契约确认，环境就绪自动启用） |

## 里程碑进度

- 本模块当前完成度：**96%**（v1.0 全链路 90% + M5 回写联调 v1.1-① + 模板重训练数据驱动 v1.1-② + 素材相关性门 v1.1-③）
- 已达成：v1.0 全链路闭环 + **M5 回写联调**（ingest 摄取，金额分→元/ROI 换算/中文诊断/unmatched 隔离/幂等）+ **模板重训练数据驱动**（M5 回写摄取 → retrain_all → stats/类目记忆落库 → best_template 决策；样本闸门 min_samples、空日不计样本；M3 全范围 **305 passed, 1 skipped** 全绿）
- 已达成（v1.1-③）：**素材相关性门**（REC-迁移-03 C3，M3 侧）——review/relevance.py（Qwen-VL 判定抽象 + mock 判定器 + 抽帧 + 款式聚类）+ gate.py RelevanceGate 编排落库；契约登记 DA-010 + `_management/data-exchange/m2-m3-m4-relevance-gate.json`；M3 全量 **327 passed, 1 skipped** 零回归
- 剩余：③④ 依赖用户侧环境（上传真实化待小店账号 / 真实 ffmpeg 待环境安装，待确认清单）+ Qwen-VL 真实判定器（待 API 契约确认，环境就绪自动启用）

## 后续排期（v1.1+ 迭代任务包）

| 顺序 | 任务包 | 前置 | 说明 |
|---|---|---|---|
| 1 | M5 投放效果回写联调（EvaluationService ↔ M5 报表快照） | M5 数据层就绪 | 经 data-audit 数据联动，总控协调 |
| 2 | 模板参数按类目重训练数据驱动（ab.retrain ↔ opt_templates/opt_category_memory） | 回写数据积累 | 样本 <5 不更新的闸门已实现 |
| 3 | 上传真实化（ApiUploader 接口契约实测 + Playwright UI 兜底 + 半自动） | 用户提供小店账号 | REC-002 契约替换点已预留 |
| 4 | 真实 ffmpeg 出片验证（FFmpegProcessRunner + skipif 用例启用） | 环境安装 ffmpeg | 无需改代码，环境就绪自动启用 |
| 5 | C3 相关性门收尾（relevance 导出 + 专项测试 + 契约文件） | 与 C3 迁移子代理对表 | ✅已完成（门禁迁移子代理：导出/22 用例/契约 JSON 全落地，M3 全量 327 passed；待总工验收） |

---

## 总工恢复记录（新任总工接管）

- **日期**：2026-08-29 13:56 ｜ **新任总工**：M3 自动素材优化（模块 ID：m3-optimization）
- **背景**：原 M3 总工代理运行环境损坏无法恢复；全部代码/测试/文档备份完好（git v0.1~v0.38 + GitHub），总控指派新任总工接管 M3 模块后续开发全流程管理。
- **恢复上下文通读**：AGENT_CONSTITUTION.md（角色/交付物/数据隔离/UTF-8 第 11 节/pytest 独立 basetemp 第 12 节/子代理管理第 9 节）；全局踩坑日志 P-001~P-016；M3 模块交付物全量（brief/risks/progress/decisions/context/README.md/data-requests.md/database/README.md，BLOCKERS 无阻塞）；`backend/optimization/` 代码（骨架 + copywriting/images/video/review/ab/upload 六子包）；`_management/data-exchange/old-system-assets/`（C3 迁移由独立子代理执行）。
- **模块状态确认**：
  1. **迭代版本 v1.1，完成度 95%**：v1.0 全链路闭环（三路输出 + 审核闸门 + A/B 闭环 + 上传抽象）+ v1.1-① M5 回写联调（ab/ingest.py 摄取入口）+ v1.1-② 模板重训练数据驱动（retrain_all/stats/类目记忆/best_template 决策）全部验收通过。
  2. **测试基线**：本轮复跑 M3 全范围 **305 passed, 1 skipped**（`--basetemp=".pytest-tmp-m3"`，P-001/P-011），与 progress 既有记录一致，无回归。
  3. **剩余**：③ 上传真实化（待用户提供小店账号）；④ 真实 ffmpeg 出片验证（待环境安装 ffmpeg）——均依赖用户侧环境，列入待确认清单。
  4. **发现项（C3 相关性门中间状态）**：`backend/optimization/review/relevance.py`（462 行）+ `gate.py` 内 `RelevanceGate` 已落地（三态判定/款式聚类/mock 自动降级），但：a) `review/__init__.py` 未导出 relevance 符号；b) `backend/tests/` 无 relevance 专项测试（test_optimization_review.py 未覆盖）；c) `gate.py` 引用的契约文件 `_management/data-exchange/m2-m3-m4-relevance-gate.json` 当前不存在。已列入「后续排期」第 5 项跟踪，待与 C3 迁移子代理对表收尾。
- **后续动作**：等总控派发（C3 迁移验收配合、上传真实化/ffmpeg 验证、v1.2 迭代包等）。
- **备注**：未运行任何 git 命令；未读写其他模块库；未写明文密钥；全部文件经 write/edit 工具 UTF-8 无 BOM（宪法第 11 节）。
