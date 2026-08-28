"""M3 自动素材优化模块 · 审核闸门（review）第二步：素材评估（子代理-D · v1.0）。

对齐 06 文档第四节第 2 步「素材评估（平台智能诊断回读）」与 10 文档第三节：
平台智能诊断回读的**本地确定性模拟（fixtures 模式）**——输入素材元数据
（resolution/ratio/duration/size/quality 分等）+ 可选平台诊断 dict
（platform_diagnosis，模拟平台诊断回读的 issues/suggestions），
输出评估结论（优秀/良好/待优化）+ 可解释优化项列表。

分级规则（06 文档第四节）：
- 硬规格全过（0 硬失败）且 0 软性不足 → 优秀（excellent）；
- 硬规格全过且 1~2 项软性不足       → 良好（good）；
- 硬规格失败 或 ≥3 项软性不足        → 待优化（needs_optimization）。

硬规格按目标类型对齐 config：video → config.video 五维（分辨率/9:16/时长/大小/格式）；
image → config.image（最小边/主图 1:1 或详情图 3:4）；copywrite → config.copywriting
（标题 15~35 字符/内容非空）。软性不足：质量分 <60、平台诊断回读 issues。
"""

from __future__ import annotations

from typing import Any, Optional

from ..config import M3Config, load_config

# 评估结论枚举（英文存储，落库 reasons_json 可读）
VERDICT_EXCELLENT = "excellent"          # 优秀
VERDICT_GOOD = "good"                    # 良好
VERDICT_NEEDS_OPTIMIZATION = "needs_optimization"  # 待优化

_VERDICT_LABEL = {
    VERDICT_EXCELLENT: "优秀",
    VERDICT_GOOD: "良好",
    VERDICT_NEEDS_OPTIMIZATION: "待优化",
}

QUALITY_SOFT_THRESHOLD = 60.0            # 质量分软性阈值
RATIO_TOLERANCE = 0.01                   # 比例容差
DETAIL_MIN_EDGE_PX = 750                 # 详情图最小边（对齐 images/quality_gate）
DETAIL_RATIO_RANGE = (0.70, 1.05)        # 详情图比例放行区间


# ---------------------------------------------------------------- 元数据解析工具


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_resolution(metadata: dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    """resolution "WxH" 字符串或 width/height 字段 → (w, h)。"""
    res = metadata.get("resolution")
    if res and isinstance(res, str):
        w, _, h = res.partition("x")
        try:
            return int(w), int(h)
        except (TypeError, ValueError):
            pass
    w, h = metadata.get("width"), metadata.get("height")
    if w is not None and h is not None:
        try:
            return int(w), int(h)
        except (TypeError, ValueError):
            return None, None
    return None, None


def _parse_ratio(metadata: dict[str, Any]) -> Optional[float]:
    """ratio 字段（"9:16" / 0.5625）或由分辨率计算 → 宽高比 w/h。"""
    ratio = metadata.get("ratio")
    if ratio is None:
        w, h = _parse_resolution(metadata)
        if w and h:
            return w / h
        return None
    if isinstance(ratio, str):
        a, _, b = ratio.partition(":")
        try:
            return float(a) / float(b)
        except (TypeError, ValueError, ZeroDivisionError):
            try:
                return float(ratio)
            except (TypeError, ValueError):
                return None
    return _to_float(ratio)


def _size_mb(metadata: dict[str, Any]) -> Optional[float]:
    """size_mb 字段；支持 size_bytes 换算。"""
    mb = _to_float(metadata.get("size_mb"))
    if mb is not None:
        return mb
    raw = metadata.get("size_bytes") or metadata.get("size")
    if raw is not None:
        try:
            return float(raw) / (1024 * 1024)
        except (TypeError, ValueError):
            return None
    return None


def _format_of(metadata: dict[str, Any]) -> Optional[str]:
    """format 字段或 file_path 扩展名 → 小写格式。"""
    fmt = metadata.get("format")
    if fmt:
        return str(fmt).lower()
    fp = str(metadata.get("file_path") or "")
    if fp:
        ext = fp.rsplit(".", 1)[-1].lower() if "." in fp else ""
        return ext or None
    return None


# ---------------------------------------------------------------- 各类型硬规格


def _check_video_hard(metadata: dict[str, Any], cfg: M3Config) -> list[dict[str, Any]]:
    """视频五维硬规格（对齐 config.video 与 05/06 文档、P-007）。"""
    v = cfg.video
    fails: list[dict[str, Any]] = []

    w, h = _parse_resolution(metadata)
    if w is None or h is None:
        fails.append({"field": "resolution", "reason": "分辨率缺失", "value": metadata.get("resolution")})
    elif w < v.min_width or h < v.min_height:
        fails.append({
            "field": "resolution",
            "reason": f"分辨率不足 {w}x{h}（需 ≥{v.min_width}x{v.min_height}）",
            "value": f"{w}x{h}",
        })

    ratio = _parse_ratio(metadata)
    target = 9 / 16
    if ratio is None:
        fails.append({"field": "ratio", "reason": "比例缺失", "value": metadata.get("ratio")})
    elif abs(ratio - target) > RATIO_TOLERANCE:
        fails.append({
            "field": "ratio",
            "reason": f"非 9:16 竖屏（ratio={ratio:.3f}）",
            "value": metadata.get("ratio"),
        })

    duration = _to_float(metadata.get("duration"))
    if duration is None:
        fails.append({"field": "duration", "reason": "时长缺失", "value": metadata.get("duration")})
    elif not (v.min_duration <= duration <= v.max_duration):
        fails.append({
            "field": "duration",
            "reason": f"时长 {duration}s 超出 {v.min_duration}~{v.max_duration}s",
            "value": duration,
        })

    size_mb = _size_mb(metadata)
    if size_mb is None:
        fails.append({"field": "size", "reason": "大小缺失", "value": metadata.get("size_mb")})
    elif size_mb > v.max_size_mb:
        fails.append({
            "field": "size",
            "reason": f"大小 {size_mb:.1f}MB 超出 {v.max_size_mb}MB",
            "value": size_mb,
        })

    fmt = _format_of(metadata)
    if fmt is None:
        fails.append({"field": "format", "reason": "格式缺失", "value": metadata.get("file_path")})
    elif fmt not in v.formats:
        fails.append({
            "field": "format",
            "reason": f"格式 {fmt} 不在 {v.formats}",
            "value": fmt,
        })
    return fails


def _check_image_hard(metadata: dict[str, Any], cfg: M3Config) -> list[dict[str, Any]]:
    """主图/详情图硬规格（对齐 config.image 与 images/quality_gate 口径）。"""
    i = cfg.image
    fails: list[dict[str, Any]] = []

    w, h = _parse_resolution(metadata)
    if w is None or h is None:
        fails.append({"field": "resolution", "reason": "分辨率缺失", "value": metadata.get("resolution")})
        return fails

    image_type = str(metadata.get("image_type") or "main").lower()
    min_edge = i.min_edge_px if image_type == "main" else DETAIL_MIN_EDGE_PX
    if min(w, h) < min_edge:
        fails.append({
            "field": "resolution",
            "reason": f"最小边 {min(w, h)}px < {min_edge}px（{w}x{h}）",
            "value": f"{w}x{h}",
        })

    ratio = w / h if h else 0.0
    if image_type == "main":
        if abs(ratio - 1.0) > RATIO_TOLERANCE:
            fails.append({
                "field": "ratio",
                "reason": f"主图非 1:1（ratio={ratio:.3f}）",
                "value": f"{w}x{h}",
            })
    elif not (DETAIL_RATIO_RANGE[0] <= ratio <= DETAIL_RATIO_RANGE[1]):
        fails.append({
            "field": "ratio",
            "reason": f"详情图比例异常（ratio={ratio:.3f}）",
            "value": f"{w}x{h}",
        })
    return fails


def _check_copy_hard(metadata: dict[str, Any], cfg: M3Config) -> list[dict[str, Any]]:
    """文案硬规格（对齐 config.copywriting：标题 15~35 字符、内容非空）。"""
    c = cfg.copywriting
    fails: list[dict[str, Any]] = []

    content = str(metadata.get("content") or "").strip()
    if not content:
        fails.append({"field": "content", "reason": "内容为空", "value": ""})
        return fails

    copy_type = str(metadata.get("copy_type") or "").lower()
    if copy_type in ("", "title"):
        char_len = _to_float(metadata.get("char_len"))
        char_len = int(char_len) if char_len is not None else len(content)
        if not (c.title_min_chars <= char_len <= c.title_max_chars):
            fails.append({
                "field": "title_len",
                "reason": f"标题长度 {char_len} 超出 {c.title_min_chars}~{c.title_max_chars} 字符",
                "value": char_len,
            })
    return fails


def _render(items: list[dict[str, Any]]) -> list[str]:
    """优化项可解释文案（field: reason）。"""
    return [f"{it['field']}: {it['reason']}" for it in items]


# ---------------------------------------------------------------- 评估器


class MaterialEvaluator:
    """素材评估器（fixtures 模式，确定性）：元数据 + 可选平台诊断 → 评估结论。"""

    def __init__(self, config: Optional[M3Config] = None):
        self.config: M3Config = config or load_config()

    def evaluate(
        self,
        metadata: dict[str, Any],
        platform_diagnosis: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """执行素材评估。

        返回：{"verdict","label","hard_failures","soft_issues","optimization_items",
               "passed","result"}——verdict 为优秀/良好/待优化（英文存储），
        result 为 gate 落库口径 pass/reject（优秀/良好 → pass，待优化 → reject）。
        """
        target_type = str(
            metadata.get("target_type") or metadata.get("type") or ""
        ).strip().lower()

        if target_type == "image":
            hard_failures = _check_image_hard(metadata, self.config)
        elif target_type in ("copywrite", "copywriting"):
            hard_failures = _check_copy_hard(metadata, self.config)
        else:  # video / unknown 默认按视频硬规格
            hard_failures = _check_video_hard(metadata, self.config)

        soft_issues: list[dict[str, Any]] = []

        quality = _to_float(metadata.get("quality_score"))
        if quality is not None and quality < QUALITY_SOFT_THRESHOLD:
            soft_issues.append({
                "field": "quality",
                "reason": f"质量分 {quality} 低于 {QUALITY_SOFT_THRESHOLD:.0f}",
                "value": quality,
            })

        if platform_diagnosis:
            issues = (
                platform_diagnosis.get("issues")
                or platform_diagnosis.get("suggestions")
                or platform_diagnosis.get("items")
                or []
            )
            if isinstance(issues, dict):
                issues = [f"{k}: {v}" for k, v in issues.items()]
            for item in issues:
                text = str(item)
                soft_issues.append({"field": "platform", "reason": text, "value": text})

        # 分级：硬规格失败 或 ≥3 软性不足 → 待优化；1~2 软性不足 → 良好；全过 → 优秀
        if hard_failures or len(soft_issues) >= 3:
            verdict = VERDICT_NEEDS_OPTIMIZATION
        elif not soft_issues:
            verdict = VERDICT_EXCELLENT
        else:
            verdict = VERDICT_GOOD

        passed = verdict in (VERDICT_EXCELLENT, VERDICT_GOOD)
        return {
            "verdict": verdict,
            "label": _VERDICT_LABEL[verdict],
            "hard_failures": hard_failures,
            "soft_issues": soft_issues,
            "optimization_items": _render(hard_failures) + _render(soft_issues),
            "passed": passed,
            "result": "pass" if passed else "reject",
        }


def evaluate_material(
    metadata: dict[str, Any],
    platform_diagnosis: Optional[dict[str, Any]] = None,
    config: Optional[M3Config] = None,
) -> dict[str, Any]:
    """模块级便捷入口：素材评估。"""
    return MaterialEvaluator(config).evaluate(metadata, platform_diagnosis)
