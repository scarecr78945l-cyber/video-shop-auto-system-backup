# REPORT_v0.4_stop_loss · M5 止损规则引擎交付说明

> 子代理：M5 v0.4 监控层·止损规则引擎 ｜ 日期：v0.4 第二子任务 ｜ 直接上级：M5 总工
> 实现依据：`_management/modules/m5-ads/context/README.md` 三节止损规则表（S1~S8 权威）、
> `10-风险合规与风控清单.md` 第一节四层资金防线、`08-自动小店投放模块设计（商品托管）.md` 第五节。
> 状态：**全部验收命令通过，无阻塞**。

## 一、文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/ads/stop_loss.py` | 新增 | 止损规则引擎（纯函数/数据驱动，零浏览器零 DB 写） |
| `backend/tests/test_ads_stop_loss.py` | 新增 | 28 个纯数据驱动用例（文件内自建 fixtures，零 DB） |
| `_management/modules/m5-ads/REPORT_v0.4_stop_loss.md` | 新增 | 本交付说明 |

未改动任何既有文件（config/ui_config/interfaces/tables/models/settings/executor/repo 及既有测试全部只读）；
未创建除上述之外的 ads 文件；未触碰 report.py（并行子代理尚未产出，本文件独立实现同口径不 import）。

## 二、接口说明（backend/ads/stop_loss.py）

### 诊断回读枚举化
- `normalize_diagnosis(raw: str | None) -> str`：优秀→`excellent`、良好→`good`、`1项待优化`→`optimize_1`、
  正则 `(\d+)项待优化` 且 N>1→`optimize_n`（N==1 亦归一为 optimize_1，容忍首尾空白与数字-项间空白）、
  空/未知/非字符串/`N项待优化` 字面量→`unknown`；已是英文枚举幂等原样返回（与 report.py 同口径，独立实现）。

### 规则判定纯函数（每个规则一个函数，输出 `RuleVerdict`）
`RuleVerdict(rule_id, action, reason, evidence: dict(可JSON), suggested_actions: list)`：

| 函数 | 规则 | 动作 | 命中条件 |
|---|---|---|---|
| `rule_s1_stop_loss(snapshot, threshold_impressions=500)` | S1 | `pause` | 花费>0 且 成交=0 且 曝光≥阈值；reason 含实际值 + 标签「换素材/调ROI」 |
| `rule_s2_optimize_diagnosis(snapshot)` | S2 | `record_optimization` | 诊断归一为 optimize_1/optimize_n；evidence 记 `priority_retry=True` |
| `rule_s3_roi_floor(snapshots, target_roi, floor_ratio=0.8)` | S3 | `degrade_material` | 最近连续 2 周期 成交ROI<目标×80%（ROI=花费>0?gmv/spend:0）；<2 周期不判定；等于止损线不命中 |
| `rule_s4_subsidy(snapshot)` | S4 | `record_subsidy` | 平台补贴>0；纯记录（补贴后 ROI 单独统计，不进止损） |
| `rule_s5_balance(account_balance_fen, min_balance_fen=10000)` | S5 | `halt_new` | 余额<阈值（¥100=10000 分）；=阈值不命中 |
| `rule_s6_active_cap(active_count, cap=40)` | S6 | `stop_new` | 投放中商品数>上限；=上限不命中 |

### 四层资金防线
- `check_budget_triple(single_spend_fen, daily_spend_fen, plan_spend_fen, budget_single_fen=0, budget_daily_fen=0, budget_plan_fen=0) -> BudgetVerdict`（S7）：
  `BudgetVerdict(over_limit, rule: single/daily/plan/none, reason, spend_fen, budget_fen)`；0=不限（不超限）；
  预算≤0 视为不限；超限判定 spend>budget；同时多超限按 single→daily→plan 取首个；未超限时 spend_fen=最大花费维度、budget_fen=其预算。
- `kill_switch_enabled(kill_switch: bool, app_config_value=None) -> bool`（S8）：kill_switch=True 或 app_config 覆盖值开启→True；
  字符串 `true/1/yes/on/enabled` 视为开，`false/0/no/off/disabled/""` 视为关，未识别字符串视为关（避免误触发全停）。
- `StopLossEngine.evaluate(campaign, snapshots, *, account_balance_fen, min_balance_fen=10000, active_count, active_cap=40, target_roi=None, roi_floor_ratio=0.8, threshold_impressions=500, kill_switch=False, budget=None, subsidy_only_report=True) -> EngineResult`：
  `EngineResult(verdicts, halt_all, actions: dict[action→count], recommendations)`。
  逐规则 S1→S2→S3→S4→S5→S6 评估（顺序稳定），S7（budget 上下文，可选）追加末尾；kill_switch=True 短路：halt_all=True 且只返回 S8 verdict；
  halt_all = kill_switch 或 S5 或 S6 命中（S7 不触发 halt_all）；target_roi 缺省回落 campaign.target_roi，仍无则跳过 S3；
  S1/S2/S4 用最新快照（S2 无快照时回落 campaign.diagnosis）；`subsidy_only_report=False` 时不产出 S4 verdict；
  budget 支持三种形状：BudgetVerdict 实例 / `{"over_limit":...}` 预计算结果（validate_submit budget_state 形状）/ 六值 dict（内部走 check_budget_triple）。

## 三、测试结果（backend，Python 3.12）

```
> python -m pytest tests/test_ads_stop_loss.py -q --basetemp=".pytest-tmp-m5"
28 passed in 0.12s

> python -m pytest tests/test_ads_stop_loss.py tests/test_ads_repo.py tests/test_ads_tables.py -q --basetemp=".pytest-tmp-m5"
55 passed in 1.56s        # 与既有 ads 测试协同全绿（28 + 27）

> python -c "from ads.stop_loss import StopLossEngine, check_budget_triple, kill_switch_enabled, normalize_diagnosis"
import OK

> python -m pytest tests/test_ads_settings.py tests/test_ads_executor.py -q --basetemp=".pytest-tmp-m5"
50 passed in 0.21s        # 额外回归：既有 v0.3 执行层测试不受影响
```

## 四、S1~S8 覆盖对照表（测试断言）

| 规则 | 命中用例 | 边界/不命中用例 |
|---|---|---|
| S1 止损暂停 | test_s1_hit_full_values（花费>0/成交=0/曝光≥500 + 默认阈值 + 自定义阈值） | test_s1_no_hit_boundaries（无花费/有成交/曝光 499/空快照） |
| S2 诊断记录 | test_s2_hit_optimize_1_and_n（1项待优化/optimize_1/3项/5 项/optimize_n + priority_retry） | test_s2_no_hit（优秀/良好/excellent/good/None/空串/未知） |
| S3 ROI 止损线 | test_s3_hit_two_consecutive_periods（连续 2 周期 ROI<1.6）、test_s3_zero_spend_counts_as_zero_roi（花费=0→ROI=0 命中） | test_s3_insufficient_periods（1 周期/无快照）、test_s3_floor_boundary_not_hit（ROI==1.6 及达标不命中） |
| S4 补贴记录 | test_s4_subsidy_hit（补贴 200 分 → record_subsidy + 单独统计标记） | test_s4_subsidy_zero_no_hit（0/缺失/None） |
| S5 余额检测 | test_s5_balance_hit（9999<10000、默认阈值、缺额上报） | test_s5_balance_boundary_equal_not_hit（=阈值/超阈值不命中） |
| S6 活跃上限 | test_s6_active_cap_hit（41>40、默认 cap、超额上报） | test_s6_active_cap_boundary_equal_not_hit（=上限/低于上限不命中） |
| S7 预算三重约束 | test_budget_triple_each_dimension_over（单笔/日/计划各自超限）、test_budget_triple_multiple_over_first_wins（同时多超限取首个）、test_budget_triple_zero_unlimited（0=不限 + 单维不限其余仍生效）、引擎级 test_engine_verdicts_order_and_actions_summary / test_engine_budget_s7_and_subsidy_flag（S7 verdict、不影响 halt_all、BudgetVerdict 实例直传） | test_budget_triple_all_pass（全过 rule=none + 最大花费维度上报） |
| S8 一键全停 | test_kill_switch_true_and_app_config_override（True / app_config 覆盖 / "true"/"1"/"on"/1）、test_engine_kill_switch_short_circuit（引擎短路：只返回 S8 verdict、halt_all=True、actions={"halt_all":1}） | test_kill_switch_false_and_string_values（False/None/False/"false"/"0"/""/"off"/0/未识别字符串） |

引擎集成另覆盖：全清空场景（verdicts=[]/halt_all=False）、S5+S6 汇总 halt_all、verdicts 顺序稳定 S1→S7、
actions 汇总（pause 计数=2 = S1+S7）、recommendations 聚合顺序、无快照时 S1/S2/S3/S4 跳过且 S5/S6 仍评估、subsidy_only_report=False 抑制 S4。

## 五、纪律合规

1. 零新增表/库、零 DB 写：全部纯函数，测试零 DB fixture（未追加 conftest，仅文件内自建 dict fixtures）。
2. 未运行任何 git 命令、未安装任何软件。
3. 无明文密钥（本文件不含任何凭证字段）。
4. 金额=分 int；ROI 浮点倍数不走分；无时间运算（快照排序对缺失/不可比较时间戳保持输入顺序，不产生时间戳值）。
5. 枚举英文：诊断 excellent/good/optimize_1/optimize_n/unknown；动作 pause/halt_new/stop_new/degrade_material/
   record_optimization/record_subsidy/record_optimize（S2 别名常量，主用 record_optimization）/halt_all。
6. 中文文件 UTF-8 无 BOM（write 工具写入）；未用 PowerShell 写中文。
7. 未改动 config.py 及任何既有 ads 文件；仅新增 stop_loss.py / test_ads_stop_loss.py / 本 REPORT。

## 六、偏差与说明

1. **S2 动作口径**：宪法动作枚举含 `record_optimize` 与 `record_optimization`，任务正文明确 S2 动作=「record_optimization」；
   实现以任务正文为准（S2 用 record_optimization），`record_optimize` 保留为模块级别名常量（ACTION_RECORD_OPTIMIZE）供枚举兼容。
2. **引擎 budget 参数三形状**：任务仅写 `budget=None`；为可测可接，实现支持 BudgetVerdict 实例 /
   `{"over_limit":...}` 预计算形状（与 v0.3 `validate_submit` 的 budget_state 形状兼容）/ 六值 dict（内部走 check_budget_triple）。
   S7 verdict 追加在 S5/S6 之后（规则表顺序 S7 在 S8 前，S8 短路独立），不参与 halt_all（严格按任务：halt_all=kill_switch 或 S5 或 S6）。
3. **subsidy_only_report 语义**：True（默认）→ S4 命中产出 record_subsidy verdict（纯记录）；False → 不产出 S4 verdict
   （补贴由调用方另行处理，避免重复记录）。S3 的 ROI 恒用未含补贴的 gmv（补贴后 ROI 单独统计，不并入止损判定，与 08/10 文档一致）。
4. **S7 动作取 `pause`**：动作枚举无 S7 专值，「立即停止相关投放动作」语义最贴近 pause；与 S1 同值不影响 actions 汇总计数（pause 计数=2 时即 S1+S7）。
5. **未识别字符串 kill_switch 取关**：默认关、仅显式 truthy 开启，避免配置脏值误触发最高优先级全停（文档化于 docstring）。
6. **测试用例数**：28（在任务 18~28 区间上限），覆盖 S1~S8 各至少 1 命中 + 边界，全部纯数据驱动。

## 七、后续衔接（供总工验收）

- 与并行子代理 report.py 的口径对齐点：`normalize_diagnosis` 映射（优秀/良好/1项待优化/N项待优化 → 英文枚举）已按同口径独立实现，验收时可交叉断言两文件结果一致。
- v0.4 下一子任务（若排期）建议：监控回读编排层把 repo 快照/账户状态接入 `StopLossEngine.evaluate`，
  S7 六值由 `sum_spend_since` + config 预算字段组装；kill_switch 由 `kill_switch_enabled(cfg.kill_switch, read_app_config(session, key))` 计算后传入。
