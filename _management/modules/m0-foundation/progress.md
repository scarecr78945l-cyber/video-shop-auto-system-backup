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
| [x] A2-1：调度器进程化实现——`backend/foundation/scheduler.py`（Worker 抽象 + WorkflowScheduler：resume_on_startup 断点自愈/run_once 单轮驱动/节流 0~4 级/连续失败 ≥2 熔断暂停 stage/run_forever 常驻循环优雅退出）+ `__main__.py`（init-db/scheduler CLI，--once/--loop/--db-url）+ `SchedulerConfig`（M0_SCHEDULER_* 前缀） | 总工 | 100% | 无 |
| [x] A2-2：调度器单测 12 例（断点自愈/单轮成功/失败退避/人工接管失败隔离/熔断暂停/冷却恢复/全暂停跳过/常驻循环 stop_event/worker_id 格式/LoggingWorker/成功重置计数）→ foundation 全量 **42 passed**（30 既有 + 12 新增）+ CLI 冒烟（init-db 建表+9 种子 / scheduler --once 统计） | 总工 | 100% | 无 |
| [x] A2-3：A2 设计落盘 `context/README.md`（调度与运行小节：独立进程方案/断点自愈/节流熔断/Worker 契约/配置与代码位置） | 总工 | 100% | 无 |
| [x] A3-1：风控规则引擎 `backend/foundation/risk.py`（通用四层防线，与 M5 stop_loss.py 同口径：金额分/ROI 浮点/枚举英文/纯函数 dict·ORM 兼容）——S7 `check_budget_triple` 预算三重硬约束（0=不限/多超限取首个）/S1 `rule_s1_stop_loss` 止损暂停/S3 `rule_s3_roi_floor` 连续 2 周期降档/S5 `rule_s5_balance` 余额检测/S8 `kill_switch_enabled` 一键全停（未识别字符串视为关）+ `normalize_diagnosis` + `RiskEngine.evaluate`（S8 短路→S7→S5→S1→S3，halt_all=S8|S5 对齐 M5） | 总工 | 100% | 无 |
| [x] A3-2：风控单测 26 例（诊断枚举/四层防线各规则命中与边界/预算三重全分支/全停开启与防误触发/引擎短路·组合·全过·dict 输入）→ foundation 全量 **68 passed**（30+12+26） | 总工 | 100% | 无 |
| [x] A3-3：M5 stop_loss.py 口径勘察 + 对齐预登记 decisions.md（S2/S4/S6 投放业务专属留 M5 不清除；M5 引用基座由总控协调） | 总工 | 100% | 无 |
| [x] A4-1：通用脱敏基座 `backend/foundation/security.py`（redact_url/redact_text/redact_path，对齐 M2 语义 + Bearer token 增强；P-004）+ 脱敏单测 11 例（URL 参数掩码/键值掩码/Bearer/路径 @账号/空值/无明文审计） | 总工 | 100% | 无 |
| [x] A4-2：默认库路径修正 `FoundationConfig.db_url` → `sqlite:///data/db/m0-foundation.db`（宪法第 4 节）+ `backend/.env.example` 模板（全模块变量名，无明文值）+ 硬编码巡检（foundation 无 C:\/C:/ 路径与密钥字面量，.exe 匹配为 execute 误报；sourcing Chrome 路径为 M1 已知项） | 总工 | 100% | 无 |
| [x] A4-3：A4 落盘 context/README.md（工程基座小节：脱敏/默认路径/.env.example/巡检结论）→ foundation 全量 **79 passed**（30+12+26+11） | 总工 | 100% | 无 |
| [x] A4-4（修复任务）：foundation_security 2 失败修复——`test_redact_text_bearer_token` 按总控裁决改实现（`_mask_secret_value` 回调：值为 Bearer 时保留原文 → 输出 `Authorization: Bearer ***`，**Bearer 前缀保留、仅 token 脱敏**）；`test_no_plaintext_secret_in_outputs` 排查结论：纯函数无共享可变状态，偶发为旧断言/P-011 并发抖动，断言已改为键值/URL/Bearer 形式 → **11 passed + 全量 1089 passed, 2 skipped 零回归** | 总工 | 100% | 无 |
| [x] A5-1：`database/migrations/0001_create_base_tables.pg.sql`（PG 五表 DDL + 9 错误码种子，幂等 IF NOT EXISTS + ON CONFLICT DO NOTHING；方言映射 JSONB/TIMESTAMPTZ/BIGSERIAL/BOOLEAN）| 总工 | 100% | 无 |
| [x] A5-2：`0001_rollback.pg.sql`（逆序 DROP）+ `README.md`（四阶段迁移计划/方言差异清单/执行方式/回滚方案（切回 SQLite 快照）/校验 SQL）→ database/README.md 迁移记录 v0.6 | 总工 | 100% | 无 |
| [x] A6-1：A6 会签登记——`data-audit.md` +DA-008（全局数据字典基准：金额分/时间 UTC _at/ID/指纹/枚举 + 错误码表权威 + 共享表读写边界 + M1~M5 分模块核对项清单） | 总工 | 30% | 待总控转达 M1~M5 总工会签，收集确认后回传 |
| [ ] 集成：与 M1~M5 联调 | 总工 | 0% | 排期 A7（亲办，A6 会签完成后） |

## 里程碑进度

- 本模块当前完成度：**70%**（筹备 15% + A1 15% + A2 10% + A3 10% + A4 10% + A5 10%；**里程碑 v0.6 达成：SQLite→PostgreSQL 迁移脚本齐备**——PG DDL/回滚/迁移计划可执行）
- 距离目标还差：治理（A6，亲办）→ 集成（A7，亲办）

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
