"""M3 视频二创流水线 · 编排层（子代理-C2 · v0.3）。

输入（原始素材 asset dict + 文案候选 CopywriteDraft 列表 + 模板参数 TemplatePlan）
→ 为每个 variant_no（≥2 版，不同片头/文案/节奏）生成 ffmpeg 命令序列
（经 ``build_transcode_cmd``，extra_filters 含字幕 drawtext 与角标）→
经 runner（本机未装 ffmpeg 走 ``MockFFmpegRunner``，环境就绪自动切
``FFmpegProcessRunner``）出片 → 出片后 ``validate_specs`` 五维硬规格校验
（失败记录 failures，upload_status 不落 uploaded）→ 落 ``opt_video_variants``
（template_params_snapshot / spec_check_json / compliance_json / evaluation=exploration）。

字幕内容取文案候选并过 ``optimization.compliance.check_text`` 预审：
命中即该版作废、改用备选文案（rejected 留证据）；全部候选命中 → 该版跳过
（记入 ``composer.skipped``，不落库）。变体间差异化：v1 取模板参数原值，
vN(N≥2) 片头秒数 +1（≤5）、混剪片段数 -1（≥1）、BGM 响度 -0.5（节奏差异）。

``run_pipeline(asset, product, variants=2)`` 一站式入口（fixtures 离线可跑）：
拆解（无 Key 规则降级）→ 模板规划 → 文案候选（口播稿 + 投放文案 + 角标）→ 出片落库。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select

from .. import tables
from ..compliance import check_text
from ..config import M3Config, load_config
from ..copywriting.ads import generate_ads, generate_badges
from ..copywriting.script import generate_script
from ..db import Database
from ..models import CopywriteDraft
from ..repo import new_id
from .breakdown import BreakdownGenerator
from .ffmpeg import (
    FFmpegProcessRunner,
    FFmpegRunner,
    MockFFmpegRunner,
    build_transcode_cmd,
    detect_ffmpeg,
    validate_specs,
)
from .templates import TemplatePlan, build_template, plan_segments

# 变体差异化常量（不同片头/节奏）
MAX_OPENING_SECONDS = 5
SUBTITLE_TRUNCATE = 24          # 字幕屏显最大字符（超出截断加 …，合规预审用全量内容）
BADGE_TRUNCATE = 8              # 角标屏显最大字符
TRANSCODE_TIMEOUT = 300.0       # 出片超时（秒）


# ---------------------------------------------------------------- 工具函数


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def probe_from_asset(asset: dict) -> dict:
    """原始素材 asset dict → ffprobe 元数据形状（{width,height,duration,size_bytes,format}）。

    Mock 出片预设用：resolution "WxH" 解析、size_mb → bytes、后缀判 mov/mp4。
    """
    res = str(asset.get("resolution") or "720x1280")
    w, _, h = res.partition("x")
    try:
        width, height = int(w), int(h)
    except (TypeError, ValueError):
        width, height = 720, 1280
    size_mb = _to_float(asset.get("size_mb"))
    size_bytes = int(size_mb * 1024 * 1024) if size_mb is not None else None
    fmt = "mov" if str(asset.get("file_path") or "").lower().endswith(".mov") else "mp4"
    return {
        "width": width,
        "height": height,
        "duration": _to_float(asset.get("duration")),
        "size_bytes": size_bytes,
        "format": fmt,
    }


def _escape_drawtext(text: str) -> str:
    """drawtext filter 文本转义（\\ ' : % 是 ffmpeg filter 语法敏感字符）。"""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("%", "\\%")
    )


def _truncate(text: str, max_chars: int) -> str:
    """屏显截断（字幕/角标用；合规预审始终基于全量内容）。"""
    t = str(text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars].rstrip() + "…"


def _subtitle_filter(text: str, style: dict[str, Any]) -> str:
    """字幕 drawtext（位置/字号/描边取自模板参数 subtitle_style）。"""
    style = style or {}
    position = str(style.get("position") or "bottom")
    font_size = int(style.get("font_size") or 36)
    stroke = bool(style.get("stroke", True))
    margin = 40
    y = f"h-th-{margin}" if position == "bottom" else f"{margin}"
    border = ":borderw=2:bordercolor=black" if stroke else ""
    return (
        f"drawtext=text='{_escape_drawtext(text)}':fontcolor=white:fontsize={font_size}"
        f":x=(w-text_w)/2:y={y}{border}:line_spacing=4"
    )


def _badge_filter(text: str, position: str) -> str:
    """角标 drawtext（位置取自模板参数 badge_position，box 底衬）。"""
    pos = str(position or "top-right")
    if pos == "top-left":
        xy = "x=24:y=24"
    elif pos == "bottom-right":
        xy = "x=w-tw-24:y=h-th-24"
    elif pos == "bottom-left":
        xy = "x=24:y=h-th-24"
    else:  # top-right 默认
        xy = "x=w-tw-24:y=24"
    return (
        f"drawtext=text='{_escape_drawtext(text)}':fontcolor=white:fontsize=28:{xy}"
        ":box=1:boxcolor=black@0.5:boxborderw=8"
    )


def _pick_draft(
    drafts: list[CopywriteDraft],
    copy_type: str,
    variant_no: int,
) -> tuple[Optional[CopywriteDraft], list[dict[str, Any]]]:
    """按 (copy_type, variant_no) 偏好序选候选：命中合规 → 记录并继续找备选。

    偏好：同 copy_type 同 variant_no → 同 copy_type 任意版本。
    返回 (选中候选或 None, 被合规拦截的候选清单)。
    """
    ordered: list[CopywriteDraft] = []
    seen_contents: set[str] = set()
    for d in drafts:
        if d.copy_type != copy_type or d.content in seen_contents:
            continue
        seen_contents.add(d.content)
        ordered.append(d)
    ordered.sort(key=lambda d: 0 if d.variant_no == variant_no else 1)

    rejected: list[dict[str, Any]] = []
    for d in ordered:
        hits = check_text(d.content)
        if hits:
            rejected.append({
                "copy_type": d.copy_type,
                "variant_no": d.variant_no,
                "content": d.content,
                "hits": hits,
            })
            continue
        return d, rejected
    return None, rejected


# ---------------------------------------------------------------- 落库（opt_video_variants）


class VideoVariantRepo:
    """视频二创版本落库（同骨架 CopywriteRepo 模式；(product_id, variant_no) 幂等覆盖）。"""

    def __init__(self, db: Database):
        self.db = db

    def upsert(self, record: dict[str, Any]) -> str:
        variant_id = record.get("variant_id") or new_id("vv")
        with self.db.session() as s:
            row = s.execute(
                select(tables.OptVideoVariant).where(
                    tables.OptVideoVariant.product_id == record["product_id"],
                    tables.OptVideoVariant.variant_no == int(record["variant_no"]),
                )
            ).scalar_one_or_none()
            if row is None:
                row = tables.OptVideoVariant(variant_id=variant_id)
                s.add(row)
            row.product_id = record["product_id"]
            row.source_asset_id = record["source_asset_id"]
            row.variant_no = int(record["variant_no"])
            row.template_id = record.get("template_id", "")
            row.copywrite_ids = list(record.get("copywrite_ids", []))
            row.template_params_snapshot = record.get("template_params_snapshot", {})
            row.file_path = record.get("file_path", "")
            row.spec_check_json = record.get("spec_check_json", {})
            row.spec_ok = int(bool(record.get("spec_ok", False)))
            row.compliance_json = record.get("compliance_json", {})
            row.review_status = record.get("review_status", "pending")
            row.upload_status = record.get("upload_status", "local")
            row.evaluation = record.get("evaluation", "exploration")
            s.flush()
            return row.variant_id

    def list_by_product(self, product_id: str) -> list[dict[str, Any]]:
        with self.db.session() as s:
            rows = s.execute(
                select(tables.OptVideoVariant)
                .where(tables.OptVideoVariant.product_id == product_id)
                .order_by(tables.OptVideoVariant.variant_no)
            ).scalars().all()
            return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(r: Any) -> dict[str, Any]:
        return {
            "variant_id": r.variant_id,
            "product_id": r.product_id,
            "source_asset_id": r.source_asset_id,
            "variant_no": r.variant_no,
            "template_id": r.template_id,
            "copywrite_ids": list(r.copywrite_ids or []),
            "template_params_snapshot": r.template_params_snapshot or {},
            "file_path": r.file_path,
            "spec_check_json": r.spec_check_json or {},
            "spec_ok": bool(r.spec_ok),
            "compliance_json": r.compliance_json or {},
            "review_status": r.review_status,
            "upload_status": r.upload_status,
            "evaluation": r.evaluation,
        }


# ---------------------------------------------------------------- 编排器


class VideoComposer:
    """视频二创编排器：文案候选 + 模板参数 → 多版 ffmpeg 出片 → 硬规格校验 → 落库。

    runner 默认：detect_ffmpeg() 就绪 → FFmpegProcessRunner（真实出片）；
    否则 MockFFmpegRunner（probe 预设取 probe_from_asset(asset)）—— fixtures 离线可跑。
    """

    def __init__(
        self,
        config: Optional[M3Config] = None,
        db: Optional[Database] = None,
        runner: Optional[FFmpegRunner] = None,
        timeout: float = TRANSCODE_TIMEOUT,
    ):
        self.config = config or load_config()
        self.db = db
        self.runner = runner
        self.timeout = float(timeout)
        self.repo = VideoVariantRepo(db) if db is not None else None
        self.skipped: list[dict[str, Any]] = []   # 全部文案候选命中合规 → 该版跳过（留证据）

    # ---------- 主流程 ----------

    def compose(
        self,
        asset: dict[str, Any],
        drafts: list[CopywriteDraft],
        template: TemplatePlan,
        variants: int = 2,
    ) -> list[dict[str, Any]]:
        """为每个 variant_no 出片并落库，返回版本记录列表（跳过版不进库）。"""
        if not drafts:
            raise ValueError("文案候选为空：compose 至少需要一个 CopywriteDraft")
        product_id = str(drafts[0].product_id or asset.get("product_id") or "")
        asset_id = str(asset.get("asset_id") or "")
        runner = self._get_runner(asset)
        self.skipped = []
        rows: list[dict[str, Any]] = []

        for variant_no in range(1, int(variants) + 1):
            if variant_no >= 2:
                # v2+ 文案差异化：优先投放文案（ad），不足时回退口播稿（script）
                subtitle, rejected_sub = _pick_draft(drafts, "ad", variant_no)
                if subtitle is None:
                    subtitle, rejected_script = _pick_draft(drafts, "script", variant_no)
                    rejected_sub += rejected_script
            else:
                # v1：口播稿字幕优先，不足时回退投放文案
                subtitle, rejected_sub = _pick_draft(drafts, "script", variant_no)
                if subtitle is None:
                    subtitle, rejected_ad = _pick_draft(drafts, "ad", variant_no)
                    rejected_sub += rejected_ad
            badge, rejected_bd = _pick_draft(drafts, "badge", variant_no)

            if subtitle is None:
                self.skipped.append({
                    "variant_no": variant_no,
                    "reason": "no_compliant_subtitle",
                    "rejected": rejected_sub,
                })
                continue

            params = self._variant_params(template, variant_no)
            segments = plan_segments(
                params, asset.get("duration"), cut_count=params.get("cut_count")
            )
            snapshot = {
                "template_id": f"{template.template_id}-v{variant_no}",
                "category": template.category,
                "params": params,
                "segments": segments,
            }

            shown = _truncate(subtitle.content, SUBTITLE_TRUNCATE)
            extra_filters = [_subtitle_filter(shown, params.get("subtitle_style") or {})]
            if badge is not None:
                extra_filters.append(_badge_filter(
                    _truncate(badge.content, BADGE_TRUNCATE),
                    params.get("badge_position") or "top-right",
                ))

            output = self._output_path(product_id, variant_no)
            cmd = build_transcode_cmd(
                str(asset.get("file_path") or ""), str(output), self.config.video,
                extra_filters=extra_filters,
            )

            transcode_error = ""
            try:
                runner.transcode(cmd, timeout=self.timeout)
            except Exception as exc:  # noqa: BLE001 —— 失败留证据不中断整批
                transcode_error = f"{type(exc).__name__}: {exc}"

            probe: dict[str, Any] = {}
            if not transcode_error:
                try:
                    probe = runner.probe(str(output))
                except Exception as exc:  # noqa: BLE001
                    probe = {"error": f"{type(exc).__name__}: {exc}"}
            spec_check = validate_specs(probe, self.config.video)

            compliance_json = {
                "subtitle": {
                    "copy_type": subtitle.copy_type,
                    "variant_no": subtitle.variant_no,
                    "full_content": subtitle.content,
                    "shown_content": shown,
                    "hits": [],
                    "passed": True,
                    "rejected": rejected_sub,
                },
                "badge": (
                    {
                        "copy_type": badge.copy_type,
                        "variant_no": badge.variant_no,
                        "content": badge.content,
                        "hits": [],
                        "passed": True,
                    }
                    if badge is not None
                    else {"selected": False}
                ),
                "pre_check": "compliance.check_text",
                "transcode_error": transcode_error,
            }

            copywrite_ids = [f"{subtitle.copy_type}:{subtitle.variant_no}"]
            if badge is not None:
                copywrite_ids.append(f"{badge.copy_type}:{badge.variant_no}")

            record: dict[str, Any] = {
                "product_id": product_id,
                "source_asset_id": asset_id,
                "variant_no": variant_no,
                "template_id": snapshot["template_id"],
                "copywrite_ids": copywrite_ids,
                "template_params_snapshot": snapshot,
                "file_path": str(output) if not transcode_error else "",
                "spec_check_json": {
                    "passed": spec_check["passed"],
                    "failures": spec_check["failures"],
                    "probe": probe,
                },
                "spec_ok": spec_check["passed"],
                "compliance_json": compliance_json,
                "review_status": "pending",
                "upload_status": "local",   # 出片+预审阶段不落 uploaded（P-007：校验失败更不允许）
                "evaluation": "exploration",
            }
            if self.repo is not None:
                record["variant_id"] = self.repo.upsert(record)
            rows.append(record)
        return rows

    # ---------- 内部工具 ----------

    def _get_runner(self, asset: dict[str, Any]) -> FFmpegRunner:
        if self.runner is not None:
            return self.runner
        if detect_ffmpeg():
            return FFmpegProcessRunner()
        return MockFFmpegRunner(probe_from_asset(asset))

    def _variant_params(self, template: TemplatePlan, variant_no: int) -> dict[str, Any]:
        """变体差异化：v1 取模板原值；vN(N≥2) 片头 +1（≤5）、混剪片段 -1（≥1）、BGM -0.5。"""
        params: dict[str, Any] = dict(template.params)
        n = int(variant_no)
        if n >= 2:
            params["opening_seconds"] = min(
                int(params.get("opening_seconds", 3)) + (n - 1), MAX_OPENING_SECONDS
            )
            params["cut_count"] = max(
                int(params.get("cut_count", 3)) - (n - 1), 1
            )
            params["bgm_loudness"] = round(
                float(params.get("bgm_loudness", -16.0)) - 0.5 * (n - 1), 1
            )
            params["params_version"] = int(params.get("params_version", 1))
        return params

    def _output_path(self, product_id: str, variant_no: int) -> Path:
        out_dir = Path(self.config.data_dir) / "video_variants"
        out_dir.mkdir(parents=True, exist_ok=True)
        formats = tuple(self.config.video.formats)
        ext = "mp4" if "mp4" in formats else (formats[0] if formats else "mp4")
        return out_dir / f"{product_id}_v{variant_no:02d}.{ext}"


# ---------------------------------------------------------------- 一站式入口


def run_pipeline(
    asset: dict[str, Any],
    product: dict[str, Any],
    variants: int = 2,
    config: Optional[M3Config] = None,
    db: Optional[Database] = None,
    runner: Optional[FFmpegRunner] = None,
) -> dict[str, Any]:
    """一站式入口：拆解 → 模板规划 → 文案候选 → 多版出片落库（fixtures 离线可跑）。

    product 形如 {"product_id", "category", "sku_spec_json"}（M1 只读引用）。
    db 缺省 → 内存库（不触碰本模块真实 m3-optimization.db）；runner 缺省 → Mock。
    """
    cfg = config or load_config()
    if db is None:
        db = Database(load_config(db_url="sqlite:///:memory:"))
        db.create_all()

    product_id = str(product["product_id"])
    category = str(product.get("category") or "")
    sku_spec = product.get("sku_spec_json") or {}

    breakdown = BreakdownGenerator(cfg).generate(product_id, category, sku_spec)
    template = build_template(category, asset_duration=asset.get("duration"))

    drafts: list[CopywriteDraft] = [generate_script(product_id, category, sku_spec, cfg)]
    drafts += generate_ads(product_id, category, sku_spec, cfg)
    drafts += generate_badges(product_id, category, sku_spec, cfg)

    composer = VideoComposer(cfg, db=db, runner=runner)
    rows = composer.compose(asset, drafts, template, variants=variants)

    return {
        "product_id": product_id,
        "asset_id": str(asset.get("asset_id") or ""),
        "breakdown": breakdown.to_dict(),
        "template": template.snapshot(),
        "draft_count": len(drafts),
        "skipped": list(composer.skipped),
        "variants": rows,
    }
