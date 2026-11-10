# -*- coding: utf-8 -*-
"""P0-2 批次 2（C1-a）：VersionSelector + classify_arrival（round-149 独立授权实现）。

依据 round-145/147/148 冻结契约（R146-1/R148 §三）：

- **select_final**：同统计身份 S 的候选快照集合内，按**独立字段 platform_updated_at**选最终有效版本。
  - `selection_rule` domain = `{unique_max_time}`（唯一胜者规则）；
  - `manual_reason` domain = `{max_time_tie, all_times_null}`（并列 / 全空 → manual_required）；
  - opaque key / id / hash / captured_at **不参与选版排序**；胜者只看非空 platform_updated_at 唯一最大；
  - 展示列表排序与胜者判定分离：`sorted_snapshot_ids` 按 `(platform_updated_at ASC NULLS LAST, snapshot_id ASC)`，
    `null_time_candidates` 按 `snapshot_id ASC`——展示次序不影响结果。
- **classify_arrival**：比对"新到快照"与"既有决策锚点"判定正常到达或时间倒退（evidence_reason=time_regression），
  不替代 select_final（prior/new 比较证据不是完整 S 候选集的最终选择）。
- tagged result：
  - `selected(snapshot_id, evidence)`；selection_rule=unique_max_time，manual_reason=null；
  - `manual_required(reason, evidence)`；selection_rule=null，manual_reason∈{max_time_tie, all_times_null}。
- 输入为空 / 非法候选 → `SelectorInputError`（明确契约）。
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence

# 三域 disjoint exact-set（round-147 §1.2；round-150 R150-2）
# SELECTION_RULE_VALUES 只含字符串枚举 unique_max_time；manual 的 selection_rule=null 是字段可空状态，
# 不作为第二个字符串枚举（R150-2）。
SELECTION_RULE_VALUES = {"unique_max_time"}
MANUAL_REASON_VALUES = {"max_time_tie", "all_times_null"}
EVIDENCE_REASON_VALUES = {"time_regression"}

AGGREGATION_VERSION = "aggr_v1"  # round-145 manifest


class SelectorInputError(ValueError):
    """selector/classify_arrival 输入非法（空候选、缺少 platform_updated_at 等）。"""


@dataclass(frozen=True)
class SnapshotCandidate:
    """selector 输入候选：必须含 snapshot_id 与 platform_updated_at（可空）。"""
    snapshot_id: int
    platform_updated_at: Optional[datetime.datetime]

    def __post_init__(self) -> None:
        if type(self.snapshot_id) is not int or self.snapshot_id <= 0:
            raise SelectorInputError(
                f"snapshot_id 必须为正 int，got {self.snapshot_id!r}")
        if self.platform_updated_at is not None:
            if not isinstance(self.platform_updated_at, datetime.datetime) \
                    or self.platform_updated_at.tzinfo is None \
                    or self.platform_updated_at.utcoffset() is None:
                raise SelectorInputError(
                    "platform_updated_at 非空时必须 timezone-aware（round-134 _is_aware 同规则）")


@dataclass(frozen=True)
class DecisionBasis:
    """决策依据（JSON 形状与 round-145/147 五向量一致）。"""
    sorted_snapshot_ids: tuple  # (time ASC NULLS LAST, id ASC)
    selected_id: Optional[int]
    selection_rule: Optional[str]           # unique_max_time | None(manual)
    manual_reason: Optional[str]            # None(selected) | max_time_tie | all_times_null
    null_time_candidates: tuple             # (id ASC)
    regressions: tuple = ()                  # (snapshot_id, reason, detail)
    aggregation_version: str = AGGREGATION_VERSION
    policy_version: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "version_selector": {
                "sorted_snapshot_ids": list(self.sorted_snapshot_ids),
                "selected_id": self.selected_id,
                "selection_rule": self.selection_rule,
                "manual_reason": self.manual_reason,
                "null_time_candidates": list(self.null_time_candidates),
            },
            "regressions": [
                {"snapshot_id": rid, "reason": reason, "detail": detail}
                for (rid, reason, detail) in self.regressions
            ],
            "aggregation_version": self.aggregation_version,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True)
class SelectionResult:
    """tagged result：selected 或 manual_required 之一。"""
    kind: str                                   # "selected" | "manual_required"
    snapshot_id: Optional[int]
    manual_reason: Optional[str]
    evidence: DecisionBasis

    def to_dict(self) -> dict:
        d = self.evidence.to_dict()
        # R150-1：manual 顶层 exact-set 与 selected 一致，仅 kind/snapshot_id/evidence；
        # reason 已放在 evidence.version_selector.manual_reason，不再额外输出顶层 reason。
        return {"kind": self.kind, "snapshot_id": self.snapshot_id, "evidence": d}


def _norm_time(dt: datetime) -> datetime:
    """规范化为 UTC aware（供比较与 key 统一）。"""
    return dt.astimezone(datetime.timezone.utc)


def _validate_candidate(c) -> None:
    """公开入口候选不变量重验（R150-2）：类型/正 int/aware 时间，不依赖构造器已运行。"""
    if not isinstance(c, SnapshotCandidate):
        raise SelectorInputError(
            f"候选必须是 SnapshotCandidate，got {type(c).__name__}")
    if type(c.snapshot_id) is not int or c.snapshot_id <= 0:
        raise SelectorInputError("候选 snapshot_id 必须为正 int")
    if c.platform_updated_at is not None:
        if not isinstance(c.platform_updated_at, datetime.datetime) \
                or c.platform_updated_at.tzinfo is None \
                or c.platform_updated_at.utcoffset() is None:
            raise SelectorInputError(
                "候选 platform_updated_at 非空时必须 timezone-aware（utcoffset() 非空）")


def _display_sort_key(c) -> tuple:
    """时间 ASC NULLS LAST + id ASC 展示排序键（R150-1：is_null 标志避免与真实 datetime.max 碰撞）。"""
    if c.platform_updated_at is None:
        return (1, 0, c.snapshot_id)  # is_null=1 → NULL 排最后
    t = c.platform_updated_at.astimezone(datetime.timezone.utc)
    return (0, t, c.snapshot_id)       # is_null=0 → 时间 ASC


def select_final_from_candidates(candidates: Sequence[SnapshotCandidate]) -> SelectionResult:
    """同 S 候选集合内选最终有效版本（纯函数，round-145 §1.1/§1.3 契约）。

    - 胜者只看非空 platform_updated_at 唯一最大；
    - 全部空 → manual_required(all_times_null)；
    - 非空集合唯一最大 → selected(该 id)；
    - 非空集合最大并列 → manual_required(max_time_tie)（混合 NULL 时 NULL 候选进
      null_time_candidates，不参与比较）；
    - 展示排序：sorted = (time ASC NULLS LAST, id ASC)；null 列表按 id ASC——不影响判定；
    - 公开入口重验候选类型/正 int/aware 时间（R150-2）。
    """
    if not candidates:
        raise SelectorInputError("候选集合为空")
    for c in candidates:
        _validate_candidate(c)
    if len({c.snapshot_id for c in candidates}) != len(candidates):
        raise SelectorInputError("候选 snapshot_id 重复")

    non_null = [c for c in candidates if c.platform_updated_at is not None]
    null_ids = tuple(sorted(c.snapshot_id for c in candidates
                            if c.platform_updated_at is None))

    # 展示排序（R150-1：is_null 标志先行）
    sorted_all = sorted(candidates, key=_display_sort_key)
    sorted_ids = tuple(c.snapshot_id for c in sorted_all)

    regressions: List[tuple] = []

    if not non_null:
        basis = DecisionBasis(
            sorted_snapshot_ids=sorted_ids, selected_id=None,
            selection_rule=None, manual_reason="all_times_null",
            null_time_candidates=null_ids, regressions=tuple(regressions),
        )
        return SelectionResult("manual_required", None, "all_times_null", basis)

    # 非空集合按时间取唯一最大
    max_time = max(_norm_time(c.platform_updated_at) for c in non_null)
    maxima = [c for c in non_null if _norm_time(c.platform_updated_at) == max_time]
    if len(maxima) > 1:
        basis = DecisionBasis(
            sorted_snapshot_ids=sorted_ids, selected_id=None,
            selection_rule=None, manual_reason="max_time_tie",
            null_time_candidates=null_ids, regressions=tuple(regressions),
        )
        return SelectionResult("manual_required", None, "max_time_tie", basis)

    winner = maxima[0]
    basis = DecisionBasis(
        sorted_snapshot_ids=sorted_ids, selected_id=winner.snapshot_id,
        selection_rule="unique_max_time", manual_reason=None,
        null_time_candidates=null_ids, regressions=tuple(regressions),
    )
    return SelectionResult("selected", winner.snapshot_id, None, basis)


def classify_arrival(
    new_snapshot: SnapshotCandidate,
    prior_selected: SnapshotCandidate,
) -> dict:
    """判决"新到快照 vs 既有决策锚点"：normal 或 time_regression（R146-1/GV5；round-150 R150-1/2）。

    - 不替代 select_final：prior/new 是单个快照的比较证据，不是完整 S 候选集的最终选择。
    - 公开入口重验类型/aware（R150-2）。
    - new < prior → time_regression：
        - `sorted_snapshot_ids` 按时间 ASC（新到早先出现）→ [new, prior]（时间 ASC, id ASC 展示规则）；
        - `detail` 使用 UTC `Z` 规范表示（R150-1），并与 regressions.detail 一致。
    - 否则 normal（新到相等或更晚）→ sorted 按时间 ASC。
    """
    _validate_candidate(new_snapshot)
    _validate_candidate(prior_selected)
    if new_snapshot.platform_updated_at is None or prior_selected.platform_updated_at is None:
        raise SelectorInputError("classify_arrival 要求 new 与 prior 均非空 platform_updated_at")

    new_t = _norm_time(new_snapshot.platform_updated_at)
    prior_t = _norm_time(prior_selected.platform_updated_at)

    # 展示列表：时间 ASC, id ASC（R150-1：不再固定 prior/new 角色顺序）
    display_ids = (new_snapshot.snapshot_id, prior_selected.snapshot_id) \
        if (new_t, new_snapshot.snapshot_id) <= (prior_t, prior_selected.snapshot_id) \
        else (prior_selected.snapshot_id, new_snapshot.snapshot_id)

    def _z(dt: datetime.datetime) -> str:
        return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    if new_t < prior_t:
        detail = (f"platform_updated_at {_z(new_t)} is earlier than prior maximum "
                  f"{_z(prior_t)}")
        basis = DecisionBasis(
            sorted_snapshot_ids=display_ids,
            selected_id=prior_selected.snapshot_id,
            selection_rule="unique_max_time", manual_reason=None,
            null_time_candidates=(),
            regressions=((new_snapshot.snapshot_id, "time_regression", detail),),
        )
        return {"kind": "time_regression", "detail": detail,
                "evidence_reason": "time_regression", "evidence": basis.to_dict()}

    # 正常到达：new 非倒退（相等或更大）
    basis = DecisionBasis(
        sorted_snapshot_ids=display_ids,
        selected_id=None, selection_rule=None, manual_reason=None,
        null_time_candidates=(),
        regressions=(),
    )
    return {"kind": "normal", "detail": None,
            "evidence_reason": None, "evidence": basis.to_dict()}