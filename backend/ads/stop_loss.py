"""M5 自动小店投放（商品托管）· 止损规则引擎（v0.4）。

实现 08 文档第五节 + 10 文档第一节的止损规则表 S1~S8 与四层资金防线：
  1. 预算三重硬约束（S7，check_budget_triple，任一超限即停）；
  2. 自动止损（S1 暂停 / S3 降档，rule_s1/rule_s3）；
  3. 余额检测（S5，rule_s5，暂停新托管 + 告警人工充值）；
  4. 一键全停（S8，kill_switch_enabled，最高优先级）。
另含诊断回读枚举化（normalize_diagnosis：excellent/good/optimize_1/optimize_n/unknown，
与并行子代理 report.py 同口径，独立实现不互相 import）。

设计约束（本任务宪法）：
  - 全部纯函数 / 数据驱动：输入为快照/账户状态/预算上下文数据（dict 或 ORM 对象，
    _get 统一取值），输出结构化判定结果（RuleVerdict / BudgetVerdict / EngineResult）；
    零浏览器、零 DB 写（app_config 只读由调用方完成）。
  - 金额一律「分」（int）；ROI 为浮点倍数（不走分）。
  - 枚举英文：诊断 excellent/good/optimize_1/optimize_n/unknown；动作
    pause/halt_new/stop_new/degrade_material/record_optimization/record_subsidy/
    record_optimize（别名）/halt_all。
  - 快照列表按 recorded_at 升序语义传入（引擎内对可比较时间戳排序，缺失保持输入顺序）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------- 常量

# 动作枚举（宪法 5：动作 pause/halt_new/stop_new/degrade_material/
# record_optimization/record_subsidy/record_optimize/halt_all）
ACTION_PAUSE = "pause"                              # S1 暂停该托管
ACTION_HALT_NEW = "halt_new"                        # S5 暂停新托管（余额不足）
ACTION_STOP_NEW = "stop_new"                        # S6 停止新增（活跃数超限）
ACTION_DEGRADE_MATERIAL = "degrade_material"        # S3 降素材优先级/调 ROI
ACTION_RECORD_OPTIMIZATION = "record_optimization"  # S2 记录优化项（标记优先重投）
ACTION_RECORD_SUBSIDY = "record_subsidy"            # S4 补贴计入报表（单独统计）
ACTION_RECORD_OPTIMIZE = "record_optimize"          # S2 别名（枚举兼容，主用 record_optimization）
ACTION_HALT_ALL = "halt_all"                        # S8 一键全停

# 诊断中文 → 英文枚举（normalize_diagnosis 权威映射）
_DIAGNOSIS_CN_TO_EN: dict[str, str] = {
    "优秀": "excellent",
    "良好": "good",
    "1项待优化": "optimize_1",
}
_EN_DIAGNOSIS_VALUES = frozenset(("excellent", "good", "optimize_1", "optimize_n"))
# 正则：N 项待优化（N>1 → optimize_n；N==1 → optimize_1）
_OPTIMIZE_RE = re.compile(r"(\d+)\s*项待优化")

# S1 默认止损曝光阈值 / S5 默认余额阈值（分，¥100）/ S6 默认活跃上限
DEFAULT_STOPLOSS_IMPRESSION = 500
DEFAULT_MIN_BALANCE_FEN = 10000
DEFAULT_ACTIVE_CAP = 40
# S3 默认 ROI 止损线比例（目标×80%）
DEFAULT_ROI_FLOOR_RATIO = 0.8

# 引擎逐规则命中时的建议文案（recommendations 聚合，按规则顺序输出）
_RECOMMENDATION_TEMPLATES: dict[str, str] = {
    "S1": "S1 暂停该托管：换素材/调ROI",
    "S2": "S2 记录优化项，标记优先重投",
    "S3": "S3 降素材优先级/建议调ROI",
    "S4": "S4 补贴计入报表（补贴后ROI单独统计）",
    "S5": "S5 余额不足：暂停新托管，人工充值后恢复",
    "S6": "S6 投放中商品数超限：停止新增，等自然淘汰",
    "S7": "S7 预算超限：立即停止相关花钱动作",
    "S8": "S8 一键全停：终止所有投放/托管/采集动作",
}


# ---------------------------------------------------------------- 取值工具（dict / ORM 兼容）

def _get(obj: Any, key: str, default: Any = None) -> Any:
    """统一取值：dict（item）与 ORM 对象（attr）兼容；None/缺失 → default。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_int(value: Any, default: int = 0) -> int:
    """金额/计数归一化为 int（None/缺失 → default；str 尽力解析，失败回落 default）。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _as_float(value: Any, default: float | None = 0.0) -> float | None:
    """ROI 等浮点归一化（str 尽力解析；None/不可解析 → default，default=None 表示跳过判定）。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _sort_snapshots(snapshots: list[Any]) -> list[Any]:
    """按 recorded_at 升序稳定排序；时间戳缺失/不可比较时保持输入顺序（调用方约定升序）。"""
    items = list(snapshots)
    if len(items) < 2:
        return items
    try:
        return sorted(items, key=lambda s: _get(s, "recorded_at", None) or datetime.min)
    except TypeError:
        return items


# ---------------------------------------------------------------- 结构化判定结果

@dataclass
class RuleVerdict:
    """单条止损规则判定结果（evidence 保证可 JSON 序列化）。"""

    rule_id: str                     # S1..S8
    action: str                      # 英文动作枚举
    reason: str                      # 中文原因（含实际值，展示/告警用）
    evidence: dict[str, Any] = field(default_factory=dict)   # 可 JSON 的证据明细
    suggested_actions: list[str] = field(default_factory=list)  # 建议动作（标签/人工指引）


@dataclass
class BudgetVerdict:
    """预算三重硬约束（S7）判定结果。rule: single/daily/plan/none；0=不限。"""

    over_limit: bool
    rule: str                        # single / daily / plan / none
    reason: str
    spend_fen: int
    budget_fen: int


@dataclass
class EngineResult:
    """引擎整体判定结果。halt_all：kill_switch 或 S5 或 S6 命中时为 True。"""

    verdicts: list[RuleVerdict] = field(default_factory=list)
    halt_all: bool = False
    actions: dict[str, int] = field(default_factory=dict)     # action → 命中次数汇总
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 诊断回读枚举化

def normalize_diagnosis(raw: str | None) -> str:
    """后台智能诊断回读值 → 英文枚举（与 report.py 同口径，独立实现）。

    优秀→excellent、良好→good、"1项待优化"→optimize_1、
    正则 `(\\d+)项待优化` 且 N>1 → optimize_n（N==1 亦归一为 optimize_1）、
    空/未知（含非字符串、"N项待优化" 字面量、未识别文本）→ unknown；
    已是英文枚举时原样返回（幂等）。
    """
    if raw is None or not isinstance(raw, str):
        return "unknown"
    text = raw.strip()
    if not text:
        return "unknown"
    if text in _DIAGNOSIS_CN_TO_EN:
        return _DIAGNOSIS_CN_TO_EN[text]
    m = _OPTIMIZE_RE.fullmatch(text)
    if m:
        n = int(m.group(1))
        return "optimize_1" if n == 1 else "optimize_n"
    if text in _EN_DIAGNOSIS_VALUES:
        return text
    return "unknown"


# ---------------------------------------------------------------- S1：止损暂停

def rule_s1_stop_loss(snapshot: Any, threshold_impressions: int = DEFAULT_STOPLOSS_IMPRESSION) -> RuleVerdict | None:
    """S1 花费>0 且 成交=0 且 曝光≥阈值（默认 500）→ 暂停该托管 + 标签「换素材/调ROI」。

    不命中返回 None。snapshot 为 dict 或 AdReportSnapshot（spend/gmv/impressions 单位：分/次）。
    """
    spend = _as_int(_get(snapshot, "spend", 0), 0)
    gmv = _as_int(_get(snapshot, "gmv", 0), 0)
    impressions = _as_int(_get(snapshot, "impressions", 0), 0)
    threshold = _as_int(threshold_impressions, DEFAULT_STOPLOSS_IMPRESSION)
    if spend > 0 and gmv == 0 and impressions >= threshold:
        return RuleVerdict(
            rule_id="S1",
            action=ACTION_PAUSE,
            reason=(
                f"花费>0 且 成交=0 且 曝光≥阈值：暂停该托管并打标签「换素材/调ROI」"
                f"（花费={spend}分，成交=0分，曝光={impressions}次，阈值={threshold}）"
            ),
            evidence={
                "spend": spend,
                "gmv": gmv,
                "impressions": impressions,
                "threshold_impressions": threshold,
            },
            suggested_actions=["换素材", "调ROI"],
        )
    return None


# ---------------------------------------------------------------- S2：诊断优化记录

def rule_s2_optimize_diagnosis(snapshot: Any) -> RuleVerdict | None:
    """S2 诊断=1项待优化（或 N 项待优化）→ 记录优化项到 evidence，标记优先重投。

    诊断回读值经 normalize_diagnosis 归一（中文/英文均可）；不命中返回 None。
    """
    raw = _get(snapshot, "diagnosis", None)
    normalized = normalize_diagnosis(raw)
    if normalized in ("optimize_1", "optimize_n"):
        scope = "1项" if normalized == "optimize_1" else "N项"
        return RuleVerdict(
            rule_id="S2",
            action=ACTION_RECORD_OPTIMIZATION,
            reason=f"诊断={scope}待优化（{normalized}）：记录优化项到 evidence，标记优先重投",
            evidence={
                "diagnosis": normalized,
                "diagnosis_raw": raw,
                "priority_retry": True,
            },
            suggested_actions=["标记优先重投", "优先换素材重投"],
        )
    return None


# ---------------------------------------------------------------- S3：ROI 止损线（连续 2 周期）

def rule_s3_roi_floor(
    snapshots: list[Any],
    target_roi: float,
    floor_ratio: float = DEFAULT_ROI_FLOOR_RATIO,
) -> RuleVerdict | None:
    """S3 最近连续 2 个快照周期 成交ROI < 目标×80% → 降素材优先级/建议调 ROI。

    ROI = 花费>0 ? 成交金额/花费 : 0（花费=0 视为 0 ROI，命中边界）。
    少于 2 周期 / 目标 ROI 不可解析 → 不判定（None）；等于止损线不命中（严格小于）。
    """
    target = _as_float(target_roi, None)
    if target is None:
        return None
    ratio = _as_float(floor_ratio, DEFAULT_ROI_FLOOR_RATIO)
    ordered = _sort_snapshots(snapshots)
    if len(ordered) < 2:
        return None
    periods = ordered[-2:]
    period_data: list[dict[str, Any]] = []
    for s in periods:
        spend = _as_int(_get(s, "spend", 0), 0)
        gmv = _as_int(_get(s, "gmv", 0), 0)
        roi = (gmv / spend) if spend > 0 else 0.0
        period_data.append({"spend_fen": spend, "gmv_fen": gmv, "roi": roi})
    floor = target * ratio
    if all(p["roi"] < floor for p in period_data):
        return RuleVerdict(
            rule_id="S3",
            action=ACTION_DEGRADE_MATERIAL,
            reason=(
                f"最近连续 2 个快照周期成交 ROI 均 < 目标×{ratio:.0%}（目标={target:.2f}，"
                f"止损线={floor:.2f}，实际 ROI={period_data[0]['roi']:.2f}/{period_data[1]['roi']:.2f}）："
                f"降素材优先级/建议调 ROI"
            ),
            evidence={
                "target_roi": target,
                "floor_ratio": ratio,
                "roi_floor": floor,
                "periods": period_data,
                "consecutive_periods": 2,
            },
            suggested_actions=["降素材优先级", "调ROI"],
        )
    return None


# ---------------------------------------------------------------- S4：平台补贴记录

def rule_s4_subsidy(snapshot: Any) -> RuleVerdict | None:
    """S4 平台补贴>0 → 补贴计入报表，补贴后 ROI 单独统计（不进止损判定）。

    纯记录动作，不参与任何停止语义；不命中返回 None。
    """
    subsidy = _as_int(_get(snapshot, "platform_subsidy", 0), 0)
    if subsidy > 0:
        return RuleVerdict(
            rule_id="S4",
            action=ACTION_RECORD_SUBSIDY,
            reason=f"平台补贴>0（{subsidy}分）：计入报表，补贴后 ROI 单独统计（不进止损判定）",
            evidence={
                "platform_subsidy": subsidy,
                "post_subsidy_roi_separate": True,
            },
            suggested_actions=["补贴计入报表", "补贴后ROI单独统计"],
        )
    return None


# ---------------------------------------------------------------- S5：余额检测

def rule_s5_balance(
    account_balance_fen: int,
    min_balance_fen: int = DEFAULT_MIN_BALANCE_FEN,
) -> RuleVerdict | None:
    """S5 余额 < 阈值（默认 ¥100=10000 分）→ 暂停新托管 + 告警人工充值。

    = 阈值不命中（严格小于）；不命中返回 None。金额单位：分。
    """
    balance = _as_int(account_balance_fen, 0)
    threshold = _as_int(min_balance_fen, DEFAULT_MIN_BALANCE_FEN)
    if balance < threshold:
        return RuleVerdict(
            rule_id="S5",
            action=ACTION_HALT_NEW,
            reason=(
                f"余额不足：可用余额 {balance} 分 < 阈值 {threshold} 分（¥{threshold / 100:g}）："
                f"暂停新托管并告警人工充值"
            ),
            evidence={
                "account_balance_fen": balance,
                "min_balance_fen": threshold,
                "shortfall_fen": threshold - balance,
            },
            suggested_actions=["暂停新托管", "告警人工充值"],
        )
    return None


# ---------------------------------------------------------------- S6：活跃数上限

def rule_s6_active_cap(active_count: int, cap: int = DEFAULT_ACTIVE_CAP) -> RuleVerdict | None:
    """S6 投放中商品数 > 上限（默认 40）→ 停止新增，等自然淘汰。

    = 上限不命中（严格大于）；不命中返回 None。
    """
    count = _as_int(active_count, 0)
    limit = _as_int(cap, DEFAULT_ACTIVE_CAP)
    if count > limit:
        return RuleVerdict(
            rule_id="S6",
            action=ACTION_STOP_NEW,
            reason=f"投放中商品数 {count} > 上限 {limit}：停止新增，等自然淘汰",
            evidence={"active_count": count, "cap": limit, "excess": count - limit},
            suggested_actions=["停止新增", "等自然淘汰"],
        )
    return None


# ---------------------------------------------------------------- S7：预算三重硬约束

def check_budget_triple(
    single_spend_fen: int,
    daily_spend_fen: int,
    plan_spend_fen: int,
    budget_single_fen: int = 0,
    budget_daily_fen: int = 0,
    budget_plan_fen: int = 0,
) -> BudgetVerdict:
    """预算三重硬约束（S7）：单笔/日总/计划总预算同时生效，任一超限即停。

    约束语义：预算 <= 0 视为不限（0=不限）；超限判定 spend > budget（严格大于）。
    同时多超限时按 single → daily → plan 顺序取首个（rule 字段标识）。
    未超限时 spend_fen 上报最大花费维度、budget_fen 为其预算（该维度不限时为 0）。
    金额单位：分。
    """
    dims: list[tuple[str, int, int, str]] = [
        ("single", _as_int(single_spend_fen, 0), _as_int(budget_single_fen, 0), "单笔预算"),
        ("daily", _as_int(daily_spend_fen, 0), _as_int(budget_daily_fen, 0), "日总预算"),
        ("plan", _as_int(plan_spend_fen, 0), _as_int(budget_plan_fen, 0), "计划总预算"),
    ]
    for rule, spend, budget, label in dims:
        if budget > 0 and spend > budget:
            return BudgetVerdict(
                over_limit=True,
                rule=rule,
                reason=f"{label}超限：花费 {spend} 分 > 预算 {budget} 分",
                spend_fen=spend,
                budget_fen=budget,
            )
    max_dim = max(dims, key=lambda d: d[1])
    return BudgetVerdict(
        over_limit=False,
        rule="none",
        reason="预算三重约束均未超限（0=不限）",
        spend_fen=max_dim[1],
        budget_fen=max_dim[2],
    )


# ---------------------------------------------------------------- S8：一键全停

def kill_switch_enabled(kill_switch: bool, app_config_value: Any = None) -> bool:
    """S8 一键全停（后台总开关）判定：kill_switch=True 或 app_config 覆盖值开启 → True。

    app_config_value 支持 bool / int / 字符串（"true"/"1"/"yes"/"on" 视为开，
    "false"/"0"/"no"/"off"/"" 视为关；未识别字符串视为关，避免误触发全停）。
    True 时引擎全部动作应被拒绝（秒级终止所有投放/托管/采集动作）。
    """
    if bool(kill_switch):
        return True
    if app_config_value is None:
        return False
    if isinstance(app_config_value, str):
        text = app_config_value.strip().lower()
        if text in ("1", "true", "yes", "on", "enabled"):
            return True
        if text in ("0", "false", "no", "off", "disabled", ""):
            return False
        return False  # 未识别字符串：不视为开启（避免误触发全停）
    return bool(app_config_value)


# ---------------------------------------------------------------- 引擎（S1~S8 逐规则评估）

class StopLossEngine:
    """止损规则引擎：组合 S1~S8 逐规则评估，输出结构化 EngineResult。

    evaluate(campaign, snapshots, *, ...) 全部输入数据由调用方传入（纯函数组合，
    零浏览器、零 DB 写）；金额一律分；快照列表按 recorded_at 升序语义传入。
    kill_switch=True 时短路：halt_all=True 且只返回 S8 verdict；
    其余情况按 S1→S2→S3→S4→S5→S6 顺序评估，S7（budget）如有预算上下文追加在末尾，
    halt_all = S5 或 S6 命中（S7 不触发 halt_all，仅停止相关花钱动作）。
    """

    def evaluate(
        self,
        campaign: Any,
        snapshots: list[Any],
        *,
        account_balance_fen: int,
        min_balance_fen: int = DEFAULT_MIN_BALANCE_FEN,
        active_count: int,
        active_cap: int = DEFAULT_ACTIVE_CAP,
        target_roi: float | None = None,
        roi_floor_ratio: float = DEFAULT_ROI_FLOOR_RATIO,
        threshold_impressions: int = DEFAULT_STOPLOSS_IMPRESSION,
        kill_switch: bool = False,
        budget: dict | BudgetVerdict | None = None,
        subsidy_only_report: bool = True,
    ) -> EngineResult:
        # ---- S8 一键全停：最高优先级，短路（只返回 S8 verdict）
        if kill_switch_enabled(kill_switch):
            v8 = RuleVerdict(
                rule_id="S8",
                action=ACTION_HALT_ALL,
                reason="一键全停（后台总开关）已开启：秒级终止所有投放/托管/采集动作",
                evidence={"kill_switch": bool(kill_switch)},
                suggested_actions=["终止所有投放/托管/采集动作"],
            )
            return EngineResult(
                verdicts=[v8],
                halt_all=True,
                actions={ACTION_HALT_ALL: 1},
                recommendations=[_RECOMMENDATION_TEMPLATES["S8"]],
            )

        verdicts: list[RuleVerdict] = []
        ordered = _sort_snapshots(snapshots)
        latest = ordered[-1] if ordered else None

        # ---- S1 止损暂停（基于最新快照；无快照跳过）
        if latest is not None:
            v1 = rule_s1_stop_loss(latest, threshold_impressions)
            if v1 is not None:
                verdicts.append(v1)

        # ---- S2 诊断优化记录（最新快照优先，无快照回落 campaign.diagnosis）
        s2_input = latest if latest is not None else campaign
        v2 = rule_s2_optimize_diagnosis(s2_input)
        if v2 is not None:
            verdicts.append(v2)

        # ---- S3 ROI 止损线（最近连续 2 周期；目标 ROI 参数缺失时回落 campaign.target_roi）
        roi_target = target_roi if target_roi is not None else _as_float(_get(campaign, "target_roi", None), None)
        if roi_target is not None:
            v3 = rule_s3_roi_floor(ordered, roi_target, roi_floor_ratio)
            if v3 is not None:
                verdicts.append(v3)

        # ---- S4 平台补贴记录（仅报表；subsidy_only_report=False 时调用方自行处理，本引擎不产出）
        if latest is not None and subsidy_only_report:
            v4 = rule_s4_subsidy(latest)
            if v4 is not None:
                verdicts.append(v4)

        # ---- S5 余额检测（暂停新托管 + 告警人工充值）
        v5 = rule_s5_balance(account_balance_fen, min_balance_fen)
        if v5 is not None:
            verdicts.append(v5)

        # ---- S6 活跃数上限（停止新增，等自然淘汰）
        v6 = rule_s6_active_cap(active_count, active_cap)
        if v6 is not None:
            verdicts.append(v6)

        # ---- S7 预算三重硬约束（budget 上下文可选；追加在末尾，不触发 halt_all）
        budget_verdict = self._resolve_budget(budget)
        if budget_verdict is not None and budget_verdict.over_limit:
            verdicts.append(
                RuleVerdict(
                    rule_id="S7",
                    action=ACTION_PAUSE,
                    reason=budget_verdict.reason,
                    evidence={
                        "budget_rule": budget_verdict.rule,
                        "spend_fen": budget_verdict.spend_fen,
                        "budget_fen": budget_verdict.budget_fen,
                    },
                    suggested_actions=["立即停止相关投放动作", "调整预算"],
                )
            )

        # ---- 汇总
        halt_all = any(v.rule_id in ("S5", "S6") for v in verdicts)
        actions: dict[str, int] = {}
        for v in verdicts:
            actions[v.action] = actions.get(v.action, 0) + 1
        recommendations = [
            _RECOMMENDATION_TEMPLATES[v.rule_id]
            for v in verdicts
            if v.rule_id in _RECOMMENDATION_TEMPLATES
        ]
        return EngineResult(
            verdicts=verdicts,
            halt_all=halt_all,
            actions=actions,
            recommendations=recommendations,
        )

    @staticmethod
    def _resolve_budget(budget: dict | BudgetVerdict | None) -> BudgetVerdict | None:
        """归一化 budget 上下文为 BudgetVerdict；None → None。

        支持三种形状：
          - BudgetVerdict 实例：原样使用；
          - {"over_limit": bool, "rule": str, ...}（validate_submit budget_state 形状）：直接构造；
          - {"single_spend_fen":..., "daily_spend_fen":..., "plan_spend_fen":...,
             "budget_single_fen":..., "budget_daily_fen":..., "budget_plan_fen":...}：走 check_budget_triple。
        """
        if budget is None:
            return None
        if isinstance(budget, BudgetVerdict):
            return budget
        if isinstance(budget, dict):
            if "over_limit" in budget:
                return BudgetVerdict(
                    over_limit=bool(budget.get("over_limit")),
                    rule=str(budget.get("rule") or "none"),
                    reason=str(budget.get("reason") or ""),
                    spend_fen=_as_int(budget.get("spend_fen"), 0),
                    budget_fen=_as_int(budget.get("budget_fen"), 0),
                )
            return check_budget_triple(
                single_spend_fen=_as_int(budget.get("single_spend_fen"), 0),
                daily_spend_fen=_as_int(budget.get("daily_spend_fen"), 0),
                plan_spend_fen=_as_int(budget.get("plan_spend_fen"), 0),
                budget_single_fen=_as_int(budget.get("budget_single_fen"), 0),
                budget_daily_fen=_as_int(budget.get("budget_daily_fen"), 0),
                budget_plan_fen=_as_int(budget.get("budget_plan_fen"), 0),
            )
        raise TypeError(
            f"budget 上下文类型不支持: {type(budget).__name__}（支持 dict / BudgetVerdict / None）"
        )


__all__ = [
    "ACTION_DEGRADE_MATERIAL",
    "ACTION_HALT_ALL",
    "ACTION_HALT_NEW",
    "ACTION_PAUSE",
    "ACTION_RECORD_OPTIMIZATION",
    "ACTION_RECORD_OPTIMIZE",
    "ACTION_RECORD_SUBSIDY",
    "ACTION_STOP_NEW",
    "BudgetVerdict",
    "DEFAULT_ACTIVE_CAP",
    "DEFAULT_MIN_BALANCE_FEN",
    "DEFAULT_ROI_FLOOR_RATIO",
    "DEFAULT_STOPLOSS_IMPRESSION",
    "EngineResult",
    "RuleVerdict",
    "StopLossEngine",
    "check_budget_triple",
    "kill_switch_enabled",
    "normalize_diagnosis",
    "rule_s1_stop_loss",
    "rule_s2_optimize_diagnosis",
    "rule_s3_roi_floor",
    "rule_s4_subsidy",
    "rule_s5_balance",
    "rule_s6_active_cap",
]
