"""M3 A/B 优化闭环 · 模板参数按类目重训练（对齐 06 文档第五节末句）。

统计类目下各模板（opt_templates）关联版本（opt_video_variants）的回写数据
（opt_evaluation_feedback）平均 ROI / CTR / 样本数 → 更新
``opt_templates.stats_json`` 与 ``opt_category_memory.template_stats_json``；
样本不足（min_samples，默认 5）不更新 —— 模板 stats 与类目记忆均保持原值，
报告返回 skipped（含原因与样本数）。

- 版本 → 模板归并：composer 落库的 template_id 含 ``-vN`` 变体后缀
  （tpl_x_v1-v2），按基模板 ``base_template_id`` 归并到 opt_templates；
- 有效样本：曝光 > 0 或 成交 > 0 的回写行（空日快照不计样本）；
- 只更新统计快照，不改动模板参数本身 —— 参数落地由调用方依据 stats 决策
  （见 ``best_template_for_category``，返回类目下平均 ROI 最高的模板）；
- 阈值配置化：``RetrainPolicy.from_env()`` 读 M3_AB_RETRAIN_MIN_SAMPLES
  （只出现环境变量名，不写密钥）。
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select

from .. import tables
from ..db import Database
from ..models import utcnow

ENV_RETRAIN_MIN_SAMPLES = "M3_AB_RETRAIN_MIN_SAMPLES"
DEFAULT_MIN_SAMPLES = 5

_VARIANT_SUFFIX_RE = re.compile(r"-v\d+$")


@dataclass
class RetrainPolicy:
    """重训练门槛（样本数下限）。"""

    min_samples: int = DEFAULT_MIN_SAMPLES

    def __post_init__(self) -> None:
        if self.min_samples < 1:
            raise ValueError("min_samples 必须 ≥ 1")

    @classmethod
    def from_env(cls) -> "RetrainPolicy":
        """从环境变量加载（非法值回退默认，绝不抛错）。"""
        try:
            return cls(
                min_samples=int(os.environ.get(ENV_RETRAIN_MIN_SAMPLES, str(DEFAULT_MIN_SAMPLES)))
            )
        except (TypeError, ValueError):
            return cls()


def base_template_id(template_id: str) -> str:
    """去掉 composer 的变体后缀（tpl_x_v1-v2 → tpl_x_v1；无后缀原样返回）。"""
    return _VARIANT_SUFFIX_RE.sub("", template_id or "")


def _signal_rows(rows: list[Any]) -> list[Any]:
    """有效样本：曝光 > 0 或 成交 > 0 的回写行（空日快照不计样本）。"""
    return [
        r
        for r in rows
        if int(r.exposure or 0) > 0 or int(r.orders or 0) > 0
    ]


class TemplateRetrainer:
    """按类目统计模板表现并回写 stats（样本不足不更新）。"""

    def __init__(self, db: Database, policy: Optional[RetrainPolicy] = None):
        self.db = db
        self.policy = policy or RetrainPolicy.from_env()

    def retrain_category(self, category: str) -> dict[str, Any]:
        """重训练单个类目，返回报告 {trained, skipped, category_memory_updated}。"""
        category = (category or "").strip()
        report: dict[str, Any] = {
            "category": category,
            "min_samples": self.policy.min_samples,
            "trained": {},
            "skipped": {},
            "category_memory_updated": False,
        }

        with self.db.session() as s:
            templates = s.execute(
                select(tables.OptTemplate).where(
                    tables.OptTemplate.category == category
                )
            ).scalars().all()
            variants = s.execute(select(tables.OptVideoVariant)).scalars().all()
            feedback = s.execute(select(tables.OptEvaluationFeedback)).scalars().all()

        template_ids = {t.template_id for t in templates}
        groups: dict[str, list[Any]] = defaultdict(list)
        for v in variants:
            base = base_template_id(v.template_id)
            snap_cat = ((v.template_params_snapshot or {}).get("category") or "").strip()
            if base in template_ids or (category and snap_cat == category):
                groups[base].append(v)

        fb_by_variant: dict[str, list[Any]] = defaultdict(list)
        for r in feedback:
            fb_by_variant[r.variant_id].append(r)

        trained: dict[str, dict[str, Any]] = {}
        for tpl in templates:  # 按 opt_templates 行序，结果确定性
            vs = groups.get(tpl.template_id, [])
            rows: list[Any] = []
            for v in vs:
                rows.extend(fb_by_variant.get(v.variant_id, []))
            sig = _signal_rows(rows)
            sample_count = len(sig)
            if sample_count < self.policy.min_samples:
                report["skipped"][tpl.template_id] = {
                    "reason": "insufficient_samples",
                    "sample_count": sample_count,
                }
                continue
            total_exp = sum(max(int(r.exposure or 0), 0) for r in sig)
            avg_roi = round(
                sum(float(r.roi or 0) for r in sig) / sample_count, 4
            )
            avg_ctr = (
                round(sum(int(r.clicks or 0) for r in sig) / total_exp, 4)
                if total_exp > 0
                else 0.0
            )
            stats: dict[str, Any] = {
                "template_id": tpl.template_id,
                "category": category,
                "avg_roi": avg_roi,
                "avg_ctr": avg_ctr,
                "sample_count": sample_count,
                "trained_at": utcnow().date().isoformat(),
            }
            with self.db.session() as s:
                row = s.get(tables.OptTemplate, tpl.template_id)
                if row is not None:
                    row.stats_json = stats
            trained[tpl.template_id] = stats
            report["trained"][tpl.template_id] = stats

        if trained:
            with self.db.session() as s:
                mem = s.get(tables.OptCategoryMemory, category)
                if mem is None:
                    mem = tables.OptCategoryMemory(category=category)
                    s.add(mem)
                mem.template_stats_json = {
                    "category": category,
                    "templates": trained,
                    "updated_at": utcnow().isoformat(timespec="seconds"),
                }
            report["category_memory_updated"] = True
        return report

    def retrain_all(self) -> dict[str, Any]:
        """按类目全量重训练。

        类目集合 = opt_templates.category ∪ 版本快照类目（保证无模板注册的
        历史版本类目也被纳入统计报告）。
        """
        with self.db.session() as s:
            cat_rows = s.execute(
                select(tables.OptTemplate.category).distinct()
            ).all()
            snap_rows = s.execute(
                select(tables.OptVideoVariant.template_params_snapshot)
            ).scalars().all()
        categories: set[str] = {c for (c,) in cat_rows if c}
        for snap in snap_rows:
            c = ((snap or {}).get("category") or "").strip()
            if c:
                categories.add(c)
        reports = {
            c: self.retrain_category(c) for c in sorted(categories)
        }
        return {
            "categories": reports,
            "trained_total": sum(len(r["trained"]) for r in reports.values()),
            "skipped_total": sum(len(r["skipped"]) for r in reports.values()),
        }

    def best_template_for_category(self, category: str) -> Optional[str]:
        """读 stats_json，返回类目下平均 ROI 最高的模板（无训练数据 → None）。"""
        best: Optional[str] = None
        best_roi = -1.0
        with self.db.session() as s:
            rows = s.execute(
                select(tables.OptTemplate).where(
                    tables.OptTemplate.category == (category or "").strip()
                )
            ).scalars().all()
            for t in rows:
                roi = float((t.stats_json or {}).get("avg_roi") or 0)
                if roi > best_roi:
                    best_roi = roi
                    best = t.template_id
        return best
