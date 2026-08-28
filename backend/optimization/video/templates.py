"""M3 视频二创流水线 · 模板参数规划层（子代理-C2 · v0.3）。

按类目构造二创模板默认参数（对齐 06 文档第一节模板参数与
_management/modules/m3-optimization/context/README.md 1.2 数据字典，
以及 tables.OptTemplate 列默认值 —— 即模板参数的「配置」来源）：

- ``opening_seconds`` 片头秒数（默认 3）
- ``subtitle_style`` 字幕样式 JSON（位置/字号/描边，默认 bottom/36/True）
- ``badge_position`` 角标位（默认 top-right）
- ``bgm_loudness`` BGM 响度 LUFS（默认 -16.0）
- ``cut_count`` 混剪片段数（默认 3）
- ``params_version`` 参数版本（模板重训练后 +1，默认 1）

并输出三段式结构规划：片头（商品+卖点卡点）→ 中段（原片/混剪片段序列）→
片尾（行动引导）。类目微调经 ``CATEGORY_ADJUSTMENTS`` 数据驱动（可配置扩展），
``build_template(..., overrides=...)`` 支持逐字段覆盖（未来模板重训练/人工调参）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# 模板参数默认值（= tables.OptTemplate 列默认 / context README 1.2 口径）
TEMPLATE_DEFAULTS: dict[str, Any] = {
    "opening_seconds": 3,
    "subtitle_style": {"position": "bottom", "font_size": 36, "stroke": True},
    "badge_position": "top-right",
    "bgm_loudness": -16.0,
    "cut_count": 3,
    "params_version": 1,
    "template_name": "默认三段式",
}

# 类目微调（数据驱动；未列类目 → 纯默认值）。值只覆盖有差异的字段。
CATEGORY_ADJUSTMENTS: dict[str, dict[str, Any]] = {
    "家居日用": {"opening_seconds": 3, "cut_count": 3},
    "宠物用品": {"opening_seconds": 3, "cut_count": 2},
    "食品": {"opening_seconds": 2, "cut_count": 3},
    "服饰": {"opening_seconds": 3, "cut_count": 4},
}

# 三段式结构规划常量（片尾秒数 / 各段要素，未来可配置化）
ENDING_SECONDS = 2
OPENING_ELEMENTS = ["商品展示", "卖点卡点"]
ENDING_ELEMENTS = ["行动引导"]


@dataclass
class TemplatePlan:
    """模板参数规划结果：template_id + 参数快照 + 三段式结构。"""

    template_id: str
    category: str
    params: dict[str, Any] = field(default_factory=dict)
    segments: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        """落库快照（opt_video_variants.template_params_snapshot 用，JSON 可序列化）。"""
        return {
            "template_id": self.template_id,
            "category": self.category,
            "params": dict(self.params),
            "segments": dict(self.segments),
        }


def _sanitize_id(part: str) -> str:
    """类目 → 安全 id 片段（保留字母数字与中文，其余替换为 _）。"""
    return re.sub(r"[^\w]", "_", part or "default").strip("_") or "default"


def _resolve_params(category: str, defaults: dict[str, Any], overrides: Optional[dict[str, Any]]) -> dict[str, Any]:
    """默认值 → 类目微调 → 显式覆盖（后层优先）。"""
    params: dict[str, Any] = dict(defaults)
    cat_key = (category or "").strip()
    adjust = CATEGORY_ADJUSTMENTS.get(cat_key)
    if adjust:
        params.update(adjust)
    if overrides:
        params.update(overrides)
    return params


class TemplatePlanner:
    """模板参数规划器（默认值可注入覆盖，未来 app_config / 类目重训练使用）。"""

    def __init__(self, defaults: Optional[dict[str, Any]] = None):
        self.defaults: dict[str, Any] = dict(TEMPLATE_DEFAULTS)
        if defaults:
            self.defaults.update(defaults)

    def build(
        self,
        category: str = "",
        overrides: Optional[dict[str, Any]] = None,
        asset_duration: Optional[float] = None,
    ) -> TemplatePlan:
        """按类目构造默认参数 + 三段式结构规划。"""
        params = _resolve_params(category, self.defaults, overrides)
        version = int(params.get("params_version", 1))
        template_id = f"tpl_{_sanitize_id(category)}_v{version}"
        segments = plan_segments(params, asset_duration)
        return TemplatePlan(
            template_id=template_id,
            category=(category or "").strip(),
            params=params,
            segments=segments,
        )


def plan_segments(
    params: dict[str, Any],
    asset_duration: Optional[float] = None,
    cut_count: Optional[int] = None,
) -> dict[str, Any]:
    """三段式结构规划（片头 / 中段 / 片尾）。

    - 片头：opening_seconds 秒，要素「商品展示 + 卖点卡点」；
    - 中段：原片或混剪片段序列 —— cut_count 个片段均分（时长 = 总时长 - 片头 - 片尾），
      片段数 1 视为原片（kind="original"），>1 视为混剪（kind="mashup"）；
    - 片尾：固定 2 秒「行动引导」。
    素材时长不足片头+片尾时，中段为空（kind="original"）。
    """
    opening = max(int(params.get("opening_seconds", TEMPLATE_DEFAULTS["opening_seconds"])), 0)
    cut = int(cut_count if cut_count is not None else params.get("cut_count", TEMPLATE_DEFAULTS["cut_count"]))
    cut = max(cut, 0)
    try:
        duration = float(asset_duration) if asset_duration is not None else 0.0
    except (TypeError, ValueError):
        duration = 0.0

    middle_total = max(duration - opening - ENDING_SECONDS, 0.0)
    segments: list[dict[str, Any]] = []
    if cut > 0 and middle_total > 0:
        seg_dur = middle_total / cut
        for i in range(cut):
            start = opening + i * seg_dur
            end = min(opening + (i + 1) * seg_dur, duration)
            segments.append({
                "index": i + 1,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(max(end - start, 0.0), 3),
            })

    return {
        "opening": {
            "type": "opening",
            "seconds": opening,
            "elements": list(OPENING_ELEMENTS),
        },
        "middle": {
            "type": "middle",
            "kind": "mashup" if len(segments) > 1 else "original",
            "segments": segments,
            "cut_count": len(segments),
        },
        "ending": {
            "type": "ending",
            "seconds": ENDING_SECONDS,
            "elements": list(ENDING_ELEMENTS),
        },
        "total_seconds": round(duration, 3),
    }


def build_template(
    category: str = "",
    overrides: Optional[dict[str, Any]] = None,
    defaults: Optional[dict[str, Any]] = None,
    asset_duration: Optional[float] = None,
) -> TemplatePlan:
    """模块级便捷入口：按类目构造模板参数 + 三段式结构规划。"""
    return TemplatePlanner(defaults).build(category, overrides, asset_duration)
