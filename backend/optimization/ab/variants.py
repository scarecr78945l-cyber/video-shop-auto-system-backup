"""M3 A/B 优化闭环 · A/B 版本管理（同一商品 ≥2 版素材）。

- ``list_variants``：同一 product 的 opt_video_variants 版本清单
  （复用 ``video.VideoVariantRepo``，只读使用不修改 video 子包）；
- ``difference_summary``：版本间差异摘要 —— template_id / copywrite_ids /
  节奏参数快照比对（opening_seconds / cut_count / bgm_loudness /
  badge_position / subtitle_style，对齐 context README 1.2 模板参数）；
- ``check_ab_ready``：是否已具备 ≥2 版（A/B 最小门槛），不足给出提示
  （对齐 06 文档第五节「同一商品产出 ≥2 版素材」）。
"""

from __future__ import annotations

from typing import Any, Optional

from ..db import Database
from ..video.composer import VideoVariantRepo

# 节奏参数快照中参与差异比对的字段（对齐模板参数配置）
PARAM_DIFF_FIELDS: tuple[str, ...] = (
    "opening_seconds",
    "cut_count",
    "bgm_loudness",
    "badge_position",
    "subtitle_style",
)
AB_MIN_VARIANTS = 2


class VariantManager:
    """A/B 版本清单 + 差异摘要 + 门槛提示。"""

    def __init__(self, db: Database):
        self.db = db
        self.repo = VideoVariantRepo(db)

    def list_variants(self, product_id: str) -> list[dict[str, Any]]:
        """版本清单（variant_no 升序，字段为 VideoVariantRepo 输出形状）。"""
        return self.repo.list_by_product(product_id)

    def difference_summary(self, product_id: str) -> dict[str, Any]:
        """版本间差异摘要：template_id / copywrite_ids / 节奏参数比对。"""
        variants = self.list_variants(product_id)
        summary: dict[str, Any] = {
            "product_id": product_id,
            "variant_count": len(variants),
            "differences": {},
            "identical_fields": [],
            "hint": "",
        }
        if len(variants) < 2:
            summary["hint"] = (
                f"版本不足 {AB_MIN_VARIANTS} 版，无法进行差异比对"
                f"（当前 {len(variants)} 版）"
            )
            return summary

        def _values(extract) -> dict[int, Any]:
            out: dict[int, Any] = {}
            for v in variants:
                val = extract(v)
                if val is not None:
                    out[int(v["variant_no"])] = val
            return out

        template_values = _values(lambda v: v.get("template_id"))
        copy_values = _values(lambda v: sorted(v.get("copywrite_ids") or []))
        param_values = {
            f: _values(
                lambda v, f=f: (v.get("template_params_snapshot") or {})
                .get("params", {})
                .get(f)
            )
            for f in PARAM_DIFF_FIELDS
        }

        def _record(key: str, values: dict[int, Any]) -> None:
            # list/dict 不可哈希 → 转 repr 判同（subtitle_style 为 dict）
            uniq = {
                repr(val) if isinstance(val, (list, dict)) else val
                for val in values.values()
            }
            if len(uniq) <= 1:
                summary["identical_fields"].append(key)
            else:
                summary["differences"][key] = {
                    "values": {str(k): val for k, val in values.items()},
                    "same": False,
                }

        _record("template_id", template_values)
        _record("copywrite_ids", copy_values)
        for f in PARAM_DIFF_FIELDS:
            _record(f, param_values[f])

        summary["identical_fields"] = sorted(set(summary["identical_fields"]))
        if summary["differences"]:
            summary["hint"] = (
                "版本间存在差异字段: " + ", ".join(sorted(summary["differences"]))
            )
        else:
            summary["hint"] = (
                "各版本模板/文案/节奏参数完全一致，"
                "建议调整差异以支撑 A/B 对照"
            )
        return summary

    def check_ab_ready(self, product_id: str) -> dict[str, Any]:
        """A/B 门槛检查：版本数 ≥2 可开启闭环，不足给出提示。"""
        count = len(self.list_variants(product_id))
        ready = count >= AB_MIN_VARIANTS
        hint = (
            ""
            if ready
            else (
                f"同一商品 A/B 至少需要 {AB_MIN_VARIANTS} 版素材"
                f"（不同片头/文案/节奏），当前仅 {count} 版"
                f"（product_id={product_id}），请补充产出后再开启 A/B 闭环。"
            )
        )
        return {
            "product_id": product_id,
            "variant_count": count,
            "ab_ready": ready,
            "needed": max(AB_MIN_VARIANTS - count, 0),
            "hint": hint,
        }
