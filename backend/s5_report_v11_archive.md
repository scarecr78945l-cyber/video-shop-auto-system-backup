# S5 人工闸门按达标自动放松 · 子代理交付报告（v1.1+）

> 任务：M1 S5 闸门放松配置化（app_config 键，v1.1+ 迭代项）
> 日期：2026-09-01 ｜ 状态：✅ 完成，sourcing 域全绿

## 一、app_config 键名表（点分隔命名空间，REC-010/DA-008 纪律）

| 键 | 类型 | 默认 | 口径 |
|---|---|---|---|
| `gate.relax.enabled` | bool | `false` | 总开关；`false`=不放松（默认行为零变化） |
| `gate.relax.min_samples` | int | `50` | 最小样本数（窗口内 通过+拒绝 合计） |
| `gate.relax.pass_rate` | float | `0.95` | 通过率阈值（通过/(通过+拒绝)，取值 (0,1]） |
| `gate.relax.window_days` | int | `30` | 统计窗口（天）：`products.created_at >= now - window_days` |
| `gate.relax.categories` | list[str] | `[]` | 类目子集；空=全部类目参与，非空=仅这些类目可放松 |

- 键名权威：`backend/sourcing/gate.py`（`KEY_ENABLED` 等常量 + `RELAX_KEYS`）。
- **与 REC-010 键名纪律一致性**：`category.whitelist`（REC-010/DA-008 定稿）确立「点分隔命名空间 + 键缺失/类型非法/异常回落默认 + 只读经 `repo.get_config_value`」约定；`gate.relax.*` 完全同约定（`gate` 为命名空间、`relax` 为策略域，五键平级），无下划线键名，无 config.py 字段镜像（纯运行时配置，区别于 `category.whitelist` 的 config 字段 + app_config 双层）。
- **只读纪律**：本模块只实现读取与计算逻辑，不写 app_config（写经总控协调）。

## 二、复核统计口径（对齐 R-54 / 10 文档第五节）

- 通过数 = 窗口内该类目 `products.state='pool'`；拒绝数 = `state='rejected'`（在途 `manual_review` 与 `hard_reject` 不计）。
- 样本数 = 通过 + 拒绝；通过率 = 通过 / 样本数（无样本 → 0）。
- **放行条件（全部满足）**：`enabled 且 样本数 ≥ min_samples 且 通过率 ≥ pass_rate 且 类目命中 categories 子集`。
- 保守边界：空类目（未归类）一律不放松（无法按类目统计，R-54 兜底）。
- 10 文档第五节「选品复核：高风险类目强制 manual_review，通过率连续达标（如 95%×50 品）可放松」→ 默认 `min_samples=50 / pass_rate=0.95 / window_days=30` 即该口径的配置化落地。

## 三、实现说明

| 文件 | 变更 |
|---|---|
| `backend/sourcing/gate.py`（新） | `GateRelaxConfig`（默认不放松）/ `DEFAULT_GATE_RELAX` / `load_gate_relax_config(session)`（类型校验回落，绝不抛异常）/ `GateRelaxStats`（passed/rejected/sample_size/pass_rate）/ `compute_category_stats` / `decide_relax`（纯判定）/ **`should_relax_category(db, category, config) -> (bool, reasons)`** / `relax_manual_review(db, config=None, dry_run=True, categories=None, limit=None) -> RelaxReport` |
| `backend/sourcing/pipeline.py` | 构造时读 `gate.relax.*`（`self.gate_relax`，失败回落默认）；`run()`/`run_from_items()` 人工复核前调用 `_relax_manual_review`：达标 manual_review 候选 `state → pool`，放行理由追加 `compliance.reasons`（随 compliance_reasons 落库审计），计数 `result.gate_relaxed`；补全/打分/TopN 以 `state=='pool'` 为准（默认 enabled=false 时与 `is_candidate` 等价，**零变化**） |
| `backend/sourcing/cli.py` | `gate-relax` 命令：缺省 **dry-run 只报告不放行**；`--apply` 实际放行；`--category` 类目子集覆盖；`--limit` |
| `backend/sourcing/models.py` | `PipelineResult.gate_relaxed: int = 0`（加法字段，向后兼容） |
| `backend/tests/test_gate_relax.py`（新） | 16 用例（见下） |
| `_management/modules/m1-sourcing/context/README.md` | 新增第七节（键名表/口径/实现/用法）；C-1 键名纪律注记同步 |
| `_management/modules/m1-sourcing/decisions.md` | +1 条 D-12（闸门放松配置化决策，含与 R-54/10 文档第五节口径对齐说明） |

- 生效点 = manual_review 品在人工复核前自动按策略放行：①流水线内新候选（`_relax_manual_review`）；②存量在闸商品（`relax_manual_review` / CLI）。
- reasons 逐条可解释（对齐打分可解释纪律）：未启用/空类目/子集外/样本不足/通过率不足/达标放行各有明确中文理由与数值。
- app_config 只读；未运行 git；未写明文密钥；UTF-8 无 BOM（5 个 py 文件实测 BOM=False）；未读写其他模块库。

## 四、测试结果（工作目录 backend，`--basetemp=".pytest-tmp-m1"`）

1. **验收命令**：`python -m pytest tests/test_gate_relax.py tests/test_pipeline.py tests/test_compliance.py tests/test_compliance_appconfig.py -q --basetemp=".pytest-tmp-m1"` → **34 passed**。
2. **sourcing 域全量回归**（17 文件既有 + test_gate_relax 新文件，共 18 文件）→ **149 passed**（既有 17 文件 133 = 历史 130 基线 + 并行子代理新增 3；新增 test_gate_relax 16；无回归）。
3. **M1 API 层**：`test_api_m1_sourcing.py` → 13 passed。
4. **CLI 冒烟**（临时库 s5-smoke.db 实测）：dry-run 只报告（家居日用达标可放行 1 / 宠物用品样本不足保持 1）；`--apply --category 宠物用品` 子集覆盖仅判定该子集（0 放行）；`--apply` 全量放行家居日用 mr-1（state→pool）、宠物用品 mr-2 保持 manual_review。

### test_gate_relax.py 覆盖清单（16 用例）
未启用不放松（默认配置）｜app_config 无键回落 disabled｜样本不足不放松｜通过率不足不放松｜达标自动放行（should_relax_category=True + relax_manual_review 实际写库）｜dry-run 只报告不放行｜categories 子集过滤｜relax categories 覆盖｜app_config 注入（临时库 get_config_value）｜类型非法/越界回落默认｜窗口过滤（>30 天不计）｜空类目保守不放松｜pipeline 默认零变化｜pipeline 启用达标自动放行入池（含放行理由落 compliance.reasons）｜pipeline 子集外保持｜CLI dry-run 后 apply。

## 五、验收标准对照

| 验收标准 | 结果 |
|---|---|
| 1. sourcing 域测试全绿（验收命令 + 16 文件 123 基线无回归） | ✅ 验收命令 34 passed；sourcing 域 18 文件 149 passed 无回归（历史 123/130 基线之上，并行子代理新增测试亦全绿） |
| 2. 默认 enabled=false 行为零变化；放松逻辑 reasons 可解释 | ✅ 默认 GateRelaxConfig disabled 路径与既有 `is_candidate` 语义等价（`state=='pool'` 过滤在默认下与 is_candidate 一致），回归证明；reasons 逐条中文可解释 |
| 3. 未运行 git；未写明文密钥；UTF-8 无 BOM；未读写其他模块库；不写 app_config（只读） | ✅ 全部满足 |

## 六、遗留/提示（供总工验收）

- **重要**：pytest 9.1.1 在包含 `tmp_path` 用例的会话开始时会对 `--basetemp` 目录执行 `rm_rf` 重建（`TempPathFactory.getbasetemp`），本报告与 `s5-smoke.db` 会被下一次同 basetemp 的 pytest 运行清除——**请在验收读取后再跑 pytest**，或先移出本目录存档。
- 后续若需「仅统计真正经过人工复核的商品」（compliance_state='manual_review' 且 state='pool' 作为通过数），可加配置旋钮演进；当前口径按任务书「通过数=进入 pool 的、拒绝数=rejected」字面实现。
- `gate.relax.categories` 写库建议由总控经后台/迁移脚本统一写入（本模块只读）。
