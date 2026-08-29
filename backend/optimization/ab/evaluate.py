"""M3 A/B 优化闭环 · 评估标签与幂等回写（对齐 06 文档第五节 + context README 1.4 评估标签）。

- 标签计算（阈值配置化，边界 >= 达标；枚举与 M2/M5 共口径 exploring/efficient/potential，DA-008）：:

    高效 efficient    = ROI ≥ roi_high（默认 2.0）
                          或 (CTR ≥ ctr_qualify（默认 2%）且 ROI ≥ roi_potential（默认 1.0）)
    潜力 potential    = 有数据（exposure ≥ min_exposure，默认 100）未达高效
                          （含「有曝光无成交」，及有成交但未达高效标准——成交待观察）
    探索期 exploring  = 无数据 / 低数据（exposure < min_exposure）

- 回写：``EvaluationService.record()`` 先按原始指标重算 score+evaluation，再经
  ``EvaluationRepo.upsert``（公共骨架只使用不修改）按 (variant_id, report_date)
  唯一幂等覆盖；骨架 upsert 会把 platform_material_id 置空，本层回写后补写该列
  （本模块自有表，直接经 db.session，属使用而非修改骨架）。
- stale（无新数据）：``mark_stale`` 检查最新快照 report_date 距今是否超过
  stale_days（默认 7）；超期 → stale=1，否则 stale=0（幂等自愈）。
- 无回写数据：``latest()`` 返回 None → 排序层按 score=0 / exploring 处理。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select

from .. import tables
from ..db import Database
from ..models import EvaluationSnapshot
from ..repo import EvaluationRepo
from .scoring import MaterialScorer, ctr_of

HIGH_EFFICIENCY = "efficient"
POTENTIAL = "potential"
EXPLORATION = "exploring"
EVALUATION_VALUES = (HIGH_EFFICIENCY, POTENTIAL, EXPLORATION)

# ---------- 环境变量名（只出现名字，不出现密钥值） ----------

ENV_EVAL_ROI_HIGH = "M3_AB_EVAL_ROI_HIGH"
ENV_EVAL_CTR_QUALIFY = "M3_AB_EVAL_CTR_QUALIFY"
ENV_EVAL_ROI_POTENTIAL = "M3_AB_EVAL_ROI_POTENTIAL"
ENV_EVAL_MIN_EXPOSURE = "M3_AB_EVAL_MIN_EXPOSURE"
ENV_EVAL_STALE_DAYS = "M3_AB_EVAL_STALE_DAYS"

DEFAULT_ROI_HIGH = 2.0
DEFAULT_CTR_QUALIFY = 0.02
DEFAULT_ROI_POTENTIAL = 1.0
DEFAULT_MIN_EXPOSURE = 100
DEFAULT_STALE_DAYS = 7


@dataclass
class EvaluationPolicy:
    """评估标签阈值（默认值可经环境变量覆盖，注入构造亦可）。"""

    roi_high: float = DEFAULT_ROI_HIGH
    ctr_qualify: float = DEFAULT_CTR_QUALIFY
    roi_potential: float = DEFAULT_ROI_POTENTIAL
    min_exposure: int = DEFAULT_MIN_EXPOSURE
    stale_days: int = DEFAULT_STALE_DAYS

    def __post_init__(self) -> None:
        if self.min_exposure < 0 or self.stale_days < 0:
            raise ValueError("min_exposure / stale_days 不能为负")
        if self.roi_high < 0 or self.ctr_qualify < 0 or self.roi_potential < 0:
            raise ValueError("标签阈值不能为负")

    @classmethod
    def from_env(cls) -> "EvaluationPolicy":
        """从环境变量加载（非法值回退默认，绝不抛错）。"""
        def _f(name: str, default: Any, cast: Any) -> Any:
            try:
                return cast(os.environ.get(name, "") or default)
            except (TypeError, ValueError):
                return default

        return cls(
            roi_high=_f(ENV_EVAL_ROI_HIGH, DEFAULT_ROI_HIGH, float),
            ctr_qualify=_f(ENV_EVAL_CTR_QUALIFY, DEFAULT_CTR_QUALIFY, float),
            roi_potential=_f(ENV_EVAL_ROI_POTENTIAL, DEFAULT_ROI_POTENTIAL, float),
            min_exposure=_f(ENV_EVAL_MIN_EXPOSURE, DEFAULT_MIN_EXPOSURE, int),
            stale_days=_f(ENV_EVAL_STALE_DAYS, DEFAULT_STALE_DAYS, int),
        )


def label_for(
    exposure: Any,
    clicks: Any,
    spend: Any,
    orders: Any,
    roi: Any,
    diagnosis: Any,
    policy: Optional[EvaluationPolicy] = None,
) -> str:
    """按阈值计算评估标签（边界 >= 达标）。

    spend 保留为签名参数（回写快照完整口径），当前标签判定不依赖花费。
    """
    p = policy or EvaluationPolicy()
    exp = int(exposure or 0)
    ords = int(orders or 0)
    r = float(roi or 0)

    # 无数据 / 低数据 → 探索期
    if exp <= 0 and ords <= 0:
        return EXPLORATION
    if exp < p.min_exposure:
        return EXPLORATION
    # 高效：ROI 达标，或 CTR 达标且 ROI 达潜力线
    if r >= p.roi_high:
        return HIGH_EFFICIENCY
    if ctr_of(clicks, exp) >= p.ctr_qualify and r >= p.roi_potential:
        return HIGH_EFFICIENCY
    # 有曝光无成交 / 有成交未达高效 → 潜力（成交待观察）
    return POTENTIAL


class EvaluationService:
    """评估标签 + 幂等回写 + stale 标记（A/B 闭环回写层）。"""

    def __init__(
        self,
        db: Database,
        policy: Optional[EvaluationPolicy] = None,
        scorer: Optional[MaterialScorer] = None,
        repo: Optional[EvaluationRepo] = None,
    ):
        self.db = db
        self.policy = policy or EvaluationPolicy.from_env()
        self.scorer = scorer or MaterialScorer()
        self.repo = repo or EvaluationRepo(db)

    # ---------- 回写 ----------

    def record(
        self,
        snap: EvaluationSnapshot,
        *,
        platform_material_id: str = "",
        recompute: bool = True,
    ) -> str:
        """计算 score/evaluation 并幂等回写，返回 feedback_id。

        recompute=True（默认）：始终按原始指标重算（同输入幂等，M5 回写口径一致）；
        platform_material_id：骨架 upsert 会置空该列，此处补写（本模块自有表）。
        """
        if recompute:
            snap.score = self.scorer.score(
                snap.roi, ctr_of(snap.clicks, snap.exposure), snap.diagnosis
            )
            snap.evaluation = label_for(
                snap.exposure, snap.clicks, snap.spend, snap.orders,
                snap.roi, snap.diagnosis, self.policy,
            )
        snap.stale = False  # 新回写视为新鲜数据
        feedback_id = self.repo.upsert(snap)
        if platform_material_id:
            with self.db.session() as s:
                row = s.get(tables.OptEvaluationFeedback, feedback_id)
                if row is not None:
                    row.platform_material_id = platform_material_id
        return feedback_id

    def record_metrics(
        self,
        variant_id: str,
        report_date: str,
        *,
        exposure: Any = 0,
        clicks: Any = 0,
        spend: Any = 0.0,
        orders: Any = 0,
        roi: Any = 0.0,
        diagnosis: Optional[dict[str, Any]] = None,
        platform_material_id: str = "",
    ) -> str:
        """便捷入口：原始指标 → EvaluationSnapshot → record()。"""
        snap = EvaluationSnapshot(
            variant_id=variant_id,
            report_date=report_date,
            exposure=int(exposure or 0),
            clicks=int(clicks or 0),
            spend=float(spend or 0),
            orders=int(orders or 0),
            roi=float(roi or 0),
            diagnosis=diagnosis or {},
        )
        return self.record(snap, platform_material_id=platform_material_id)

    # ---------- 读 ----------

    def latest(self, variant_id: str) -> Optional[dict[str, Any]]:
        """最新回写快照（无数据 → None，排序层按 0 分 / exploring 处理）。"""
        return self.repo.latest_by_variant(variant_id)

    def latest_map(self, variant_ids: list[str]) -> dict[str, dict[str, Any]]:
        """批量取各素材最新快照（report_date 升序覆盖，{variant_id: {…}}）。"""
        ids = [v for v in variant_ids if v]
        if not ids:
            return {}
        with self.db.session() as s:
            rows = s.execute(
                select(tables.OptEvaluationFeedback)
                .where(tables.OptEvaluationFeedback.variant_id.in_(ids))
                .order_by(tables.OptEvaluationFeedback.report_date.asc())
            ).scalars().all()
        latest: dict[str, dict[str, Any]] = {}
        for r in rows:
            latest[r.variant_id] = {
                "report_date": r.report_date,
                "score": float(r.score or 0),
                "evaluation": r.evaluation or EXPLORATION,
                "stale": bool(r.stale),
            }
        return latest

    # ---------- stale（无新数据标记） ----------

    def mark_stale(self, variant_id: str, today: Optional[str] = None) -> bool:
        """最新快照超期（report_date < today - stale_days）→ stale=1，否则 0。

        幂等自愈：重复调用结果一致；返回标记后的 stale 状态。
        """
        latest = self.latest(variant_id)
        if latest is None:
            return False
        base = date.fromisoformat(today or date.today().isoformat())
        cutoff = (base - timedelta(days=self.policy.stale_days)).isoformat()
        stale = latest["report_date"] < cutoff
        with self.db.session() as s:
            row = s.execute(
                select(tables.OptEvaluationFeedback).where(
                    tables.OptEvaluationFeedback.variant_id == variant_id,
                    tables.OptEvaluationFeedback.report_date == latest["report_date"],
                )
            ).scalar_one_or_none()
            if row is not None:
                row.stale = int(stale)
        return stale

    def mark_stale_all(self, today: Optional[str] = None) -> int:
        """批量 stale 标记，返回被标记为 stale 的素材数（无数据素材不计）。"""
        with self.db.session() as s:
            variant_ids = [
                row[0]
                for row in s.execute(
                    select(tables.OptEvaluationFeedback.variant_id).distinct()
                ).all()
            ]
        return sum(1 for vid in variant_ids if self.mark_stale(vid, today=today))
