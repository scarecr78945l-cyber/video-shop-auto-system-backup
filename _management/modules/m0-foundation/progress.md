# M0 基座与数据治理 · 进度看板（progress）

> 由总工程师持续维护。迭代版本号规则：每次重要返工/改版 +0.1（v1.0 → v1.1）。
> 台账登记见 `_management/logs/agent-activity.md`。

## 当前迭代：v0.1（筹备轮）

| 任务 | 负责 | 进度 | 剩余工作 |
|---|---|---|---|
| [x] 通读宪法/踩坑日志（P-001~P-007）+ 设计文档 09/10/11/02/03/01 + backend 基线（tables.py/config.py/db.py/README） | 总工 | 100% | 无 |
| [x] 撰写模块任务书 `brief.md` | 总工 | 100% | 无 |
| [x] 风险预判 `risks.md`（R01~R21，六类） | 总工 | 100% | 无 |
| [x] 上下文库 `context/README.md`（数据字典/共享表归属/环境变量注册表） | 总工 | 100% | 无 |
| [x] 基座库 Schema 规划 `database/README.md`（DDL/前缀/迁移计划） | 总工 | 100% | 无 |
| [x] 决策记录 `decisions.md`（首轮 6 项关键决策） | 总工 | 100% | 无 |
| [x] P-001 落实：`backend/README.md` 测试命令补 `--basetemp=".pytest-tmp"` | 总工 | 100% | 无 |
| [x] 登记工作台账 `agent-activity.md` | 总工 | 100% | 无 |
| [x] A1-1：workflow_jobs 最终 DDL 落盘（SQLite，含租约/幂等/retry_after/evidence_json） | 总工 | 100% | 无 |
| [x] A1-2：tasks 表最终 DDL 落盘（SQLite，job_id 归属/stage/状态/错误码/租约/幂等） | 总工 | 100% | 无 |
| [x] A1-3：复核五表 DDL（无乱码/对齐 REC-005）+ `backend/foundation/tables.py` 字段命名对齐 DDL（retry_after/evidence_json/Task 补全） | 总工 | 100% | 无 |
| [x] A1-4：repo.py 字段对齐 DDL（retry_after/evidence_json）+ foundation 单测 30 个（五表可建/列对齐/唯一约束/seed 幂等/enqueue/claim/complete/fail/租约 45min 回收/幂等/错误码退避/失败隔离，SQLite 内存库 StaticPool）+ 全量回归全绿 | 总工 | 100% | 无 |
| [x] 基座开发 A（A1 队列基座）验收：`python -m pytest tests -q --basetemp=".pytest-tmp-m0"` → **417 passed, 1 skipped 全绿**（宪法第 12 节独立 basetemp；含 sourcing 41+21+23 + materials + optimization + ads + foundation 30；5 个 foundation 既有失败已全部修复） | 总工 | 100% | 无 |
| [ ] 基座开发 B：调度器进程化（独立进程 + resume_on_startup 断点恢复） | 总工/子代理 | 0% | 排期 A2，待总控批准派发 |
| [ ] 风控落地：预算三重/止损/余额/一键全停 | 总工/子代理 | 0% | 排期 A3 |
| [ ] 工程基座：环境变量化/脱敏巡检/.env.example/迁移脚本 | 总工/子代理 | 0% | 排期 A4/A5 |
| [ ] 治理：数据字典定稿 + 跨模块契约会签 | 总工 | 0% | 排期 A6 |
| [ ] 集成：与 M1~M5 联调 | 总工 | 0% | 排期 A7 |

## 里程碑进度

- 本模块当前完成度：**30%**（筹备 15% + A1 队列基座 15%；**里程碑 v0.2 达成：workflow_jobs 建库可跑 + 队列 API 全绿**）
- 距离目标还差：调度器进程化（A2）→ 风控落地（A3）→ 工程基座（A4/A5）→ 治理（A6）→ 集成（A7）

## 后续开发排期（可拆给子代理的任务标注 ✅）

| # | 任务 | 可拆子代理 | 依赖 | 目标迭代 | 验收标准 |
|---|---|---|---|---|---|
| A1 | 共享表 DDL（SQLAlchemy 模型）+ 队列 API：enqueue/claim/complete/fail、租约（45min 回收）、幂等唯一约束、失败隔离 | ✅ 可拆（自包含任务书） | 无 | v0.2 | 队列单测通过；39 passed 回归不破；pytest 带 `--basetemp` |
| A2 | 调度器进程化：独立进程 + `resume_on_startup` 断点恢复 + systemd/后台托管方案 | ✅ 可拆 | A1 | v0.3 | 进程崩溃恢复测试通过 |
| A3 | 风控规则引擎：预算三重硬约束/自动止损/余额检测/一键全停（`M0_KILL_SWITCH` + `app_config` 键） | ✅ 可拆 | A1 | v0.4 | 规则引擎单测；总开关实测秒级生效 |
| A4 | 工程基座：硬编码路径环境变量化巡检、`_redact_text` 脱敏覆盖、`.env.example` 模板生成 | ✅ 可拆 | 无 | v0.5 | 全库 grep 无硬编码路径/明文密钥；审计日志无敏感值 |
| A5 | SQLite→PostgreSQL 迁移脚本（方言兼容 + 回滚快照） | ✅ 可拆 | A1 | v0.5 | 迁移演练通过；校验脚本核对行数/约束 |
| A6 | 数据字典定稿 + 跨模块契约会签（与 M1~M5 总工，经 `data-audit.md`） | 总工亲自（跨模块不可拆） | 各模块 brief/context 完成 | v0.6 | `data-audit` 核对记录齐全；`data-exchange/` 载体签字 |
| A7 | 与 M1~M5 集成联调（队列/错误码/风控/配置） | 总工亲自 | A1~A6 | v1.0 | 端到端模拟流程跑通（不提交真实商品） |
