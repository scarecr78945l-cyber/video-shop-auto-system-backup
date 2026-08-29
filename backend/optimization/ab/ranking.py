"""M3 A/B 优化闭环 · 素材排序（供 M5 投放绑定选择）。

排序口径（对齐 06 文档第五节「供投放绑定排序：高效 > 潜力 > 探索期」）：
同商品 / 类目下先按 evaluation（高效 > 潜力 > 探索期），再按 score 降序；
同 evaluation 同 score 保持原顺序（Python ``sorted`` 稳定，按 variant_no 升序迭代）。

输出形状：``[(variant_id, platform_material_id, evaluation, score)]``。

- 无回写数据的版本 → evaluation=exploration、score=0（排最后）；
- ``platform_material_id`` 取自 opt_video_variants（上传层回填）；
  ``only_uploaded=True`` 时仅输出已上传平台的版本；
- 类目排序按 ``template_params_snapshot.category`` 过滤（Python 侧过滤，
  兼容 SQLite JSON 存储，不依赖 JSON1 扩展）。
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select

from .. import tables
from ..db import Database
from .evaluate import EXPLORATION, EvaluationService

EVALUATION_ORDER: dict[str, int] = {
    "efficient": 0,    # 高效（M2/M5 共口径，DA-008）
    "potential": 1,
    "exploring": 2,    # 探索期
}


class MaterialRanker:
    """素材排序器：读 opt_video_variants + 最新回写快照 → 排序输出元组列表。"""

    def __init__(self, db: Database, service: Optional[EvaluationService] = None):
        self.db = db
        self.service = service or EvaluationService(db)

    def rank_for_product(
        self, product_id: str, *, only_uploaded: bool = False
    ) -> list[tuple[str, str, str, float]]:
        """同商品下全部版本排序（variant_no 升序作为稳定基准）。"""
        with self.db.session() as s:
            rows = s.execute(
                select(tables.OptVideoVariant)
                .where(tables.OptVideoVariant.product_id == product_id)
                .order_by(tables.OptVideoVariant.variant_no.asc())
            ).scalars().all()
            variants = [self._as_row(r) for r in rows]
        return self._rank(variants, only_uploaded=only_uploaded)

    def rank_for_category(
        self, category: str, *, only_uploaded: bool = False
    ) -> list[tuple[str, str, str, float]]:
        """同类别目下全部版本排序（按版本快照类目过滤）。"""
        category = (category or "").strip()
        with self.db.session() as s:
            rows = s.execute(
                select(tables.OptVideoVariant).order_by(
                    tables.OptVideoVariant.variant_no.asc()
                )
            ).scalars().all()
            variants = [
                self._as_row(r)
                for r in rows
                if ((r.template_params_snapshot or {}).get("category") or "").strip()
                == category
            ]
        return self._rank(variants, only_uploaded=only_uploaded)

    @staticmethod
    def _as_row(r: Any) -> dict[str, Any]:
        return {
            "variant_id": r.variant_id,
            "platform_material_id": r.platform_material_id or "",
        }

    def _rank(
        self, variants: list[dict[str, Any]], *, only_uploaded: bool
    ) -> list[tuple[str, str, str, float]]:
        latest = self.service.latest_map([v["variant_id"] for v in variants])
        items: list[tuple[str, str, str, float]] = []
        for v in variants:
            pm = v["platform_material_id"]
            if only_uploaded and not pm:
                continue
            info = latest.get(v["variant_id"]) or {}
            items.append(
                (
                    v["variant_id"],
                    pm,
                    info.get("evaluation") or EXPLORATION,
                    float(info.get("score") or 0.0),
                )
            )
        return self.sort(items)

    @staticmethod
    def sort(
        items: list[tuple[str, str, str, float]]
    ) -> list[tuple[str, str, str, float]]:
        """排序核心（纯函数）：evaluation 序 → score 降序 → 稳定。

        未知 evaluation 值按探索期处理（排最后），保证外来数据不破坏排序。
        """
        return sorted(
            items,
            key=lambda it: (EVALUATION_ORDER.get(it[2], 2), -float(it[3])),
        )
