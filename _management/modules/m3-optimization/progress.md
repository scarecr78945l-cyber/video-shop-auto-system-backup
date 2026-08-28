# M3 自动素材优化 · 进度看板（progress）

> 由总工程师持续维护。迭代版本号规则：每次重要返工/改版 +0.1（v1.0 → v1.1）。

## 当前迭代：v1.0（集成阶段，排期已批准）

> 总控 2025 体系建立日批准 v1.0 集成排期（v0.19 已提交并推送 GitHub）：拆 3 个子代理并行——①审核闸门 review；②A/B 闭环 ab；③上传素材库 upload；最后端到端集成测试。裁决：REC-001（图片资产域归 M3）、REC-002（上传双轨 UploadService，M3_UPLOAD_MODE=api|ui|semi 配置化，先 fixtures 模拟）。

| 任务 | 负责 | 进度 | 剩余工作 |
|---|---|---|---|
| [x] 阅读设计文档（06/09/10/11/03/05）+ 撰写任务书 | 总工 | 100% | 无（brief.md 已交付） |
| [x] 风险预判（LLM 密钥配额/ffmpeg 硬规格/生图拒审/合规/评估回流/上传方式） | 总工 | 100% | 无（risks.md 已交付） |
| [x] 数据字典 + 跨模块契约（context/） | 总工 | 100% | 无（context/README.md + data-requests.md 已交付） |
| [x] 数据库 Schema 规划（opt_*） | 总工 | 100% | 无（database/README.md 规划稿） |
| [x] 跨模块数据联动申请登记 | 总工 | 100% | 总控已批准，转达后生效 |
| [x] 公共骨架：backend/optimization 包（config/db/tables/models/compliance）+ fixtures 样本 | 总工 | 100% | 无（骨架已建，供子代理使用） |
| [x] 文案管线 + 规则预审扩展（v0.2） | 子代理-A（验收通过） | 100% | 无（copywriting 子包 + 27 用例全绿） |
| [x] 主图/详情图管线（v0.4） | 子代理-B（验收通过） | 100% | 无（images 子包 + 38 用例全绿，含 P-011 加固修复） |
| [x] 视频二创流水线（v0.3） | 子代理-C1/C2（验收通过） | 100% | 无（video 子包 + 66 用例全绿） |
| [ ] 审核闸门 review（v1.0-1） | 子代理-D（验收通过） | 100% | 无（review 子包 5 文件，规则预审/素材评估/人工抽检 + 测试通过） |
| [ ] A/B 闭环 ab（v1.0-2） | 子代理-E（验收通过） | 100% | 无（ab 子包 6 文件，评分/标签/排序/版本管理/重训练 + 测试通过） |
| [ ] 上传素材库 upload（v1.0-3） | 子代理-F（验收通过） | 100% | 无（upload 子包 7 文件，UploadService api/ui/semi + 测试通过） |
| [x] 端到端集成测试（v1.0-4） | 总工（集成验收） | 100% | 无（test_optimization_e2e.py 2 用例；修复集成缺口：VideoVariantRepo 回填 platform_material_id） |

## 里程碑进度

- 本模块当前完成度：**90%**（三路输出 60% + v1.0 集成三组件 ~20% + 端到端集成 ~10%）
- 已达成：**v1.0 里程碑——全链路闭环代码+测试完成**：三路输出（文案 27 / 主图详情图 38 / 视频二创 66 例）+ v1.0 集成（review / ab / upload 共 165 例 + 端到端 2 例）；全量回归 **1016 passed, 2 skipped**（`--basetemp=".pytest-tmp-m3"`，P-011 纪律）
- 剩余：v1.1+ 迭代——模板参数按类目重训练生效、真实小店账号实测上传（REC-002 api/ui/semi 切换）、真实 ffmpeg 出片、M5 回写联调

## 后续排期（v1.1+ 迭代任务包）

| 顺序 | 任务包 | 前置 | 说明 |
|---|---|---|---|
| 1 | M5 投放效果回写联调（EvaluationService ↔ M5 报表快照） | M5 数据层就绪 | 经 data-audit 数据联动，总控协调 |
| 2 | 模板参数按类目重训练数据驱动（ab.retrain ↔ opt_templates/opt_category_memory） | 回写数据积累 | 样本 <5 不更新的闸门已实现 |
| 3 | 上传真实化（ApiUploader 接口契约实测 + Playwright UI 兜底 + 半自动） | 用户提供小店账号 | REC-002 契约替换点已预留 |
| 4 | 真实 ffmpeg 出片验证（FFmpegProcessRunner + skipif 用例启用） | 环境安装 ffmpeg | 无需改代码，环境就绪自动启用 |
