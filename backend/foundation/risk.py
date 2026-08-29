"""M0 风控规则引擎（通用，10 文档第一节四层资金防线）。

总控裁决（共享规则以基座为准，M5 引用由总控协调）：本模块与 M5
`backend/ads/stop_loss.py` 同口径——金额一律「分」int、ROI 浮点倍数、枚举英文、
纯函数/数据驱动（dict/ORM 兼容 `_get`）、结构化 `RuleVerdict`/`BudgetVerdict`/`EngineResult`，
函数签名与语义完全对齐（M5 后续可直接 import 本模块替换自有实现）。

覆盖四层防线：
  1. 预算三重硬约束（S7 `check_budget_triple`）：单笔/日总/计划总同时生效，任一超限即停；0=不限；
  2. 自动止损（S1 `rule_s1_stop_loss` 暂停+标签「换素材/调ROI」/ S3 `rule_s3_roi_floor` 连续 2 周期降档）；
  3. 余额检测（S5 `rule_s5_balance`：低于阈值暂停新托管+告警人工充值）；
  4. 一键全停（S8 `kill_switch_enabled`：最高优先级，未识别字符串视为关防误触发）。
S2/S4/S6（诊断优化记录/补贴统计/活跃上限）为投放业务专属规则，留在 M5 不清除。

设计约束：零浏览器、零 DB 写；输入 dict 或 ORM 对象；快照按 recorded_at 升序语义传入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------- 常量

# 动作枚举（对齐 M5 stop_loss.py）
ACTION_PAUSE = "pause"                        # S1 暂停该托管
ACTION_HALT_NEW = "halt_new"                  # S5 暂停新托管（余额不足）
ACTION_DEGRADE_MATERIAL = "degrade_material"  # S3 降素材优先级/调 ROI
ACTION_HALT_ALL = "halt_all"                  # S8 一键全停

# S1 默认止损曝光阈值 / S5 默认余额阈值（分，¥100）/ S3 默认 ROI 止损线比例
DEFAULT_STOPLOSS_IMPRESSION = 500
DEFAULT_MIN_BALANCE_FEN = 10000
DEFAULT_ROI_FLOOR_RATIO = 0.8

# 诊断中文 → 英文枚举（normalize_diagnosis 权威映射，对齐 M5）
_DIAGNOSIS_CN_TO_EN: dict[str, str] = {
    "优秀": "excellent",
    "良好": "good",
    "1项待优化": "optimize_1",
}
_EN_DIAGNOSIS_VALUES = frozenset(("excellent", "good", "optimize_1", "optimize_n"))
_OPTIMIZE_RE = re.compile(r"(\d+)\s*项待优化")


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
    """按 recorded_at 升序稳定排序；时间戳缺失/不可比较时保持输入顺序。"""
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
    """单条风控规则判定结果（evidence 可 JSON 序列化）。"""

    rule_id: str                     # S1/S3/S5/S7/S8
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
    """引擎整体判定结果。halt_all：kill_switch 或 S5 命中时为 True（对齐 M5 语义）。"""

    verdicts: list[RuleVerdict] = field(default_factory=list)
    halt_all: bool = False
    actions: dict[str, int] = field(default_factory=dict)     # action → 命中次数汇总
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 诊断回读枚举化

def normalize_diagnosis(raw: str | None) -> str:
    """后台智能诊断回读值 → 英文枚举（对齐 M5 stop_loss.py 同口径）。

    优秀→excellent、良好→good、"1项待优化"→optimize_1、
    正则「数字+项待优化」且 N>1 → optimize_n（N==1 亦归一 optimize_1）、
    空/未知/未识别文本 → unknown；已是英文枚举时原样返回（幂等）。
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

    不命中返回 None。snapshot 为 dict 或快照对象（spend/gmv/impressions 单位：分/次）。
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


# ---------------------------------------------------------------- 引擎（四层防线评估）

class RiskEngine:
    """风控规则引擎：组合四层防线（S8→S7→S5→S1→S3）逐规则评估，输出结构化 EngineResult。

    evaluate(campaign, snapshots, *, ...) 全部输入数据由调用方传入（纯函数组合，
    零浏览器、零 DB 写）；金额一律分；快照列表按 recorded_at 升序语义传入。
    kill_switch=True 时短路：halt_all=True 且只返回 S8 verdict；
    其余按 S7（预算，有上下文时）→ S5（余额）→ S1（止损暂停）→ S3（ROI 降档）评估；
    halt_all = S8 或 S5 命中（对齐 M5 语义：预算超限不触发 halt_all，仅停止花钱动作）。
    """

    def evaluate(
        self,
        campaign: Any,
        snapshots: list[Any],
        *,
        account_balance_fen: int,
        min_balance_fen: int = DEFAULT_MIN_BALANCE_FEN,
        target_roi: float | None = None,
        roi_floor_ratio: float = DEFAULT_ROI_FLOOR_RATIO,
        threshold_impressions: int = DEFAULT_STOPLOSS_IMPRESSION,
        kill_switch: bool = False,
        app_config_kill_switch: Any = None,
        budget: BudgetVerdict | dict | None = None,
    ) -> EngineResult:
        # ---- S8 一键全停：最高优先级，短路（只返回 S8 verdict）
        if kill_switch_enabled(kill_switch, app_config_kill_switch):
            v8 = RuleVerdict(
                rule_id="S8",
                action=ACTION_HALT_ALL,
                reason="一键全停：终止所有投放/托管/采集动作（秒级）",
                evidence={"kill_switch": True},
                suggested_actions=["停止所有动作", "人工检查"],
            )
            return EngineResult(verdicts=[v8], halt_all=True, actions={ACTION_HALT_ALL: 1}, recommendations=[v8.reason])

        verdicts: list[RuleVerdict] = []
        halt_all = False

        # ---- S7 预算三重硬约束（有预算上下文才评估）
        if budget is not None:
            bv = budget if isinstance(budget, BudgetVerdict) else BudgetVerdict(**budget)
            if bv.over_limit:
                verdicts.append(
                    RuleVerdict(
                        rule_id="S7",
                        action=ACTION_PAUSE,
                        reason=bv.reason,
                        evidence={"over_limit": True, "rule": bv.rule, "spend_fen": bv.spend_fen, "budget_fen": bv.budget_fen},
                        suggested_actions=["停止相关花钱动作", "调整预算"],
                    )
                )

        # ---- S5 余额检测
        v5 = rule_s5_balance(account_balance_fen, min_balance_fen)
        if v5 is not None:
            verdicts.append(v5)
            halt_all = True  # 对齐 M5：S5 命中 → halt_all（暂停新托管）

        # ---- S1 止损暂停（快照维度；多快照取最近命中）
        for snapshot in snapshots:
            v1 = rule_s1_stop_loss(snapshot, threshold_impressions)
            if v1 is not None:
                verdicts.append(v1)
                break  # 单条命中即可

        # ---- S3 ROI 降档（连续 2 周期）
        if target_roi is not None:
            v3 = rule_s3_roi_floor(snapshots, target_roi, roi_floor_ratio)
            if v3 is not None:
                verdicts.append(v3)

        actions: dict[str, int] = {}
        for v in verdicts:
            actions[v.action] = actions.get(v.action, 0) + 1
        return EngineResult(
            verdicts=verdicts,
            halt_all=halt_all,
            actions=actions,
            recommendations=[v.reason for v in verdicts],
        )


__all__ = [
    "ACTION_PAUSE",
    "ACTION_HALT_NEW",
    "ACTION_DEGRADE_MATERIAL",
    "ACTION_HALT_ALL",
    "DEFAULT_STOPLOSS_IMPRESSION",
    "DEFAULT_MIN_BALANCE_FEN",
    "DEFAULT_ROI_FLOOR_RATIO",
    "RuleVerdict",
    "BudgetVerdict",
    "EngineResult",
    "normalize_diagnosis",
    "rule_s1_stop_loss",
    "rule_s3_roi_floor",
    "rule_s5_balance",
    "check_budget_triple",
    "kill_switch_enabled",
    "RiskEngine",
]
