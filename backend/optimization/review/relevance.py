"""M3 自动素材优化模块 · 审核闸门（review）· 素材相关性门（REC-迁移-03 C3，v1.0）。

对齐旧系统 `material_gate`（`auto_flow._collect_and_judge_materials`：Qwen-VL
前 15 秒抽帧相关性判定 + `material_clustering` 款式聚类 → 多款式必须人工确认，
禁止自动选品/采购）与迁移清单 C3 第 1 项（M3 复用 gate.py 框架新增 relevance 审核类型）。

实现策略（同 ffmpeg 层：接口抽象 + fixtures mock，环境就绪自动启用真实模式）：
- ``detect_qwen_vl()``：探测 Qwen-VL API Key（只读环境变量名 config.relevance.api_key_env，
  不读值不落盘；任何失败返回 False，绝不抛异常）；
- ``RelevanceJudge``（ABC）：``judge(material, frames) -> 判定 dict``（三态
  related/unrelated/multi_style）。``MockRelevanceJudge`` 确定性 fixtures 判定
  （material['mock_verdict'] 注入或帧描述关键词启发式）；``QwenVLRelevanceJudge``
  真实实现骨架（待 Qwen-VL API 契约确认，构造只读环境变量名，不写明文密钥，
  judge 抛 RelevanceJudgeError 不静默）；
- ``FrameSampler``（ABC）：``extract_frames(material) -> [帧记录]``（前 15 秒等距
  抽帧）。``MockFrameSampler`` 返回 fixtures 帧描述；``FFmpegFrameSampler`` 用
  ffmpeg -ss 抽帧（runner 可注入 Mock 测试；ffmpeg 缺失构造即抛错，含安装指引）；
- ``StyleClusterer``：款式聚类（material_clustering 语义）——不相关优先淘汰；
  款式数 >1 → multi_style（多款式需人工确认目标款，禁止自动创建衍生商品）；
- ``build_relevance_judge()`` / ``build_frame_sampler()``：按 config.relevance.mode
  （auto/mock/qwen）构造，未知 mode 显式抛错不静默。

三态映射（与 opt_review_records.result 对齐）：related→pass（放行）/
unrelated→reject（淘汰，不进入询价/上架链）/ multi_style→manual_review（人工确认）。

错误码：RelevanceJudgeError.error_code 限定 WorkflowJob 码表子集
TIMEOUT/UNEXPECTED/NO_MATCH（其余归一 UNEXPECTED；对齐 ffmpeg.py 口径）。
零网络、零明文密钥（P-004）、零跨库访问。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Optional

from ..config import M3Config, load_config

# ---------------------------------------------------------------- 三态判定码
VERDICT_RELATED = "related"            # 相关 → 放行
VERDICT_UNRELATED = "unrelated"        # 不相关 → reject（淘汰）
VERDICT_MULTI_STYLE = "multi_style"    # 多款式 → manual_review（人工确认目标款）

_VERDICT_LABEL = {
    VERDICT_RELATED: "相关",
    VERDICT_UNRELATED: "不相关",
    VERDICT_MULTI_STYLE: "多款式",
}

# 三态 → 落库 result（与 opt_review_records.result 对齐：pass/reject/manual_review）
VERDICT_TO_RESULT = {
    VERDICT_RELATED: "pass",
    VERDICT_UNRELATED: "reject",
    VERDICT_MULTI_STYLE: "manual_review",
}

# WorkflowJob 错误码子集（本层可用；其余归一 UNEXPECTED，对齐 ffmpeg.py）
RELEVANCE_ERROR_CODES = frozenset({"TIMEOUT", "UNEXPECTED", "NO_MATCH"})

# 旧系统收敛规则：多款式必须人工确认目标款，禁止自动创建衍生商品（08-17 修正）
MULTI_STYLE_MANUAL_NOTE = "多款式需人工确认目标款，禁止自动创建衍生商品"

# Mock 帧描述关键词启发式（仅 fixtures 模式；真实模式由 Qwen-VL 判定）
_UNRELATED_KEYWORDS = ("不相关", "无关", "不同商品", "unrelated", "not related")
_MULTI_STYLE_KEYWORDS = ("多款式", "多个款式", "不同款式", "多款", "multi style", "multiple styles")


# ---------------------------------------------------------------- 异常


class RelevanceJudgeError(Exception):
    """相关性判定异常，error_code 限定 WorkflowJob 码表子集（TIMEOUT/UNEXPECTED/NO_MATCH）。"""

    def __init__(self, error_code: str, message: str = "", evidence: Optional[dict] = None):
        if error_code not in RELEVANCE_ERROR_CODES:
            error_code = "UNEXPECTED"
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message
        self.evidence = evidence or {}


# ---------------------------------------------------------------- 环境探测


def detect_qwen_vl(config: Optional[M3Config] = None) -> bool:
    """探测 Qwen-VL API Key（环境变量名 config.relevance.api_key_env）。

    只检查环境变量**是否存在且非空**，绝不读取/落盘 Key 值；任何异常返回 False
    （绝不抛异常，对齐 ffmpeg.detect_ffmpeg 语义）。
    """
    cfg = config or load_config()
    try:
        name = str(cfg.relevance.api_key_env or "")
        if not name:
            return False
        value = os.environ.get(name)
        return bool(value and str(value).strip())
    except Exception:  # noqa: BLE001 —— 探测绝不抛异常
        return False


# ---------------------------------------------------------------- 判定器


class RelevanceJudge(ABC):
    """相关性判定器抽象：Qwen-VL（真实）/ Mock（fixtures 确定性）。"""

    mode: str = "unknown"

    @abstractmethod
    def judge(self, material: dict[str, Any], frames: list[dict[str, Any]]) -> dict[str, Any]:
        """判定素材与目标商品的相关性。

        material: M2 素材 + 目标商品上下文（title/file_path/duration/target_product_title/
                  frame_descriptions/style_hints/mock_verdict 等，见模块 docstring）。
        frames: FrameSampler.extract_frames 输出（前 15 秒抽帧记录）。
        返回：{"verdict","label","confidence","reason","evidence"}——verdict 三态
        （related/unrelated/multi_style），evidence 留判定依据（帧描述/商品上下文摘要，
        不含明文密钥）。
        """


class MockRelevanceJudge(RelevanceJudge):
    """fixtures 确定性判定器（Qwen-VL 无 Key / mode=mock 时使用）。

    判定优先级：
    1. material['mock_verdict'] ∈ {related, unrelated, multi_style} —— fixtures 显式注入；
    2. 否则按帧描述关键词启发式（_UNRELATED_KEYWORDS / _MULTI_STYLE_KEYWORDS）；
    3. 默认 related（干净素材默认相关，反例由 fixtures 显式注入）。
    零网络、零 API Key（R-M2-17 同款离线纪律）。
    """

    mode = "mock"

    def __init__(self, config: Optional[M3Config] = None):
        self.config: M3Config = config or load_config()

    def judge(self, material: dict[str, Any], frames: list[dict[str, Any]]) -> dict[str, Any]:
        explicit = str(material.get("mock_verdict") or "").strip()
        if explicit in (VERDICT_RELATED, VERDICT_UNRELATED, VERDICT_MULTI_STYLE):
            return self._build(explicit, reason=f"fixtures 显式注入 mock_verdict={explicit}", material=material)

        descriptions = " ".join(
            str(f.get("description") or "") for f in (frames or [])
        ).lower()
        if any(kw in descriptions for kw in _UNRELATED_KEYWORDS):
            return self._build(
                VERDICT_UNRELATED,
                reason="mock 帧描述命中「不相关」关键词",
                material=material,
            )
        if any(kw in descriptions for kw in _MULTI_STYLE_KEYWORDS):
            return self._build(
                VERDICT_MULTI_STYLE,
                reason="mock 帧描述命中「多款式」关键词",
                material=material,
            )
        return self._build(
            VERDICT_RELATED,
            reason="mock 默认判定：无反例信号视为相关（反例由 fixtures 注入）",
            material=material,
        )

    @staticmethod
    def _build(verdict: str, reason: str, material: dict[str, Any]) -> dict[str, Any]:
        return {
            "verdict": verdict,
            "label": _VERDICT_LABEL[verdict],
            "confidence": 1.0,
            "reason": reason,
            "evidence": {
                "mode": "mock",
                "asset_id": material.get("asset_id"),
                "title": str(material.get("title") or "")[:200],
                "target_product_title": str(material.get("target_product_title") or "")[:200],
            },
        }


class QwenVLRelevanceJudge(RelevanceJudge):
    """真实 Qwen-VL 相关性判定器**骨架**（待 Qwen-VL API 契约/登录态确认）。

    当前状态：
    - 构造只读 config.relevance（mode/api_key_env/超时等），**不写明文密钥**
      （P-004：仅引用环境变量名，值经 os.environ 读取）；
    - `judge` 抛 RelevanceJudgeError（UNEXPECTED）——骨架占位，不静默降级。

    待 API 契约确认后的切换步骤（见汇报）：
    1. 在 context/README.md 登记 Qwen-VL API 契约 + 环境变量清单（仅变量名）；
    2. 实现 judge()：前 15 秒抽帧图 + 目标商品上下文 → Qwen-VL 多模态判定
       → 结构化解析三态（related/unrelated/multi_style）+ 帧描述/款式描述留证据；
    3. 超时/限流按全局码表抛 RelevanceJudgeError（TIMEOUT/RATE_LIMIT→归一 TIMEOUT）。
    """

    mode = "qwen"

    def __init__(self, config: Optional[M3Config] = None):
        self.config: M3Config = config or load_config()
        self._api_key_env = str(self.config.relevance.api_key_env or "QWEN_VL_API_KEY")

    def judge(self, material: dict[str, Any], frames: list[dict[str, Any]]) -> dict[str, Any]:
        raise RelevanceJudgeError(
            "UNEXPECTED",
            (
                "QwenVLRelevanceJudge.judge：待 Qwen-VL API 契约确认后实现"
                f"（api_key_env={self._api_key_env}，密钥仅走环境变量；"
                f"frames={len(frames or [])}，material_id={material.get('asset_id')}）"
            ),
            evidence={"api_key_env": self._api_key_env, "frame_count": len(frames or [])},
        )


# ---------------------------------------------------------------- 抽帧


class FrameSampler(ABC):
    """前 15 秒抽帧抽象：Mock（fixtures 描述）/ FFmpeg（真实抽帧图）。"""

    @abstractmethod
    def extract_frames(self, material: dict[str, Any]) -> list[dict[str, Any]]:
        """抽取素材前 15 秒内等距帧。

        返回 [{"at_seconds", "path"|None, "description"|None}]；
        失败抛 RelevanceJudgeError（错误码 TIMEOUT/UNEXPECTED/NO_MATCH）。
        """


class MockFrameSampler(FrameSampler):
    """fixtures 抽帧：返回 material['frame_descriptions']（列表/字符串均可）。

    未提供描述时按标题合成一条占位描述（"<标题> 画面"），保证后续判定有输入；
    真实模式由 FFmpegFrameSampler 抽帧 + Qwen-VL 生成描述。
    """

    mode = "mock"

    def __init__(self, config: Optional[M3Config] = None):
        self.config: M3Config = config or load_config()

    def extract_frames(self, material: dict[str, Any]) -> list[dict[str, Any]]:
        raw = material.get("frame_descriptions")
        if raw is None:
            title = str(material.get("title") or "").strip()
            raw = [f"{title} 画面"] if title else ["无画面描述（mock 模式缺省）"]
        if isinstance(raw, str):
            raw = [raw]
        return [
            {
                "at_seconds": round(
                    self.config.relevance.frame_window_seconds * i / max(1, len(list(raw)) - 1), 3
                )
                if len(list(raw)) > 1
                else 0.0,
                "path": None,
                "description": str(d),
            }
            for i, d in enumerate(list(raw))
        ]


class FFmpegFrameSampler(FrameSampler):
    """真实抽帧：ffmpeg -ss 在素材前 15 秒窗口等距抽帧（对齐旧系统 Qwen-VL 前 15 秒判定）。

    - runner 可注入（测试用 MockFFmpegRunner；默认 FFmpegProcessRunner，ffmpeg 缺失
      构造即抛 RelevanceJudgeError，含安装指引——不静默）；
    - 抽帧时间点：窗口 = min(duration, config.relevance.frame_window_seconds)，
      frame_count 等距（含首尾）；-ss 前置快速 seek；
    - 输出帧写入 work_dir（默认 data_dir/frames_relevance/，可注入覆盖）；
    - 无 file_path → NO_MATCH（缺输入不判定）。
    """

    mode = "real"

    def __init__(
        self,
        config: Optional[M3Config] = None,
        runner: Any = None,
        work_dir: Optional[str] = None,
    ):
        self.config: M3Config = config or load_config()
        if runner is None:
            from ..video.ffmpeg import FFmpegProcessRunner, VideoToolError

            try:
                runner = FFmpegProcessRunner()
            except VideoToolError as exc:
                raise RelevanceJudgeError("UNEXPECTED", str(exc.message)) from exc
        self.runner = runner
        self.work_dir = work_dir or str(self.config.data_dir / "frames_relevance")

    def extract_frames(self, material: dict[str, Any]) -> list[dict[str, Any]]:
        import os as _os

        path = material.get("file_path")
        if not path:
            raise RelevanceJudgeError(
                "NO_MATCH", "素材缺少 file_path，无法抽帧", evidence={"asset_id": material.get("asset_id")}
            )
        _os.makedirs(self.work_dir, exist_ok=True)
        try:
            duration = float(material.get("duration") or self.config.relevance.frame_window_seconds)
        except (TypeError, ValueError):
            duration = float(self.config.relevance.frame_window_seconds)
        window = min(max(duration, 0.0), float(self.config.relevance.frame_window_seconds))
        count = max(1, int(self.config.relevance.frame_count))
        times = [window * i / (count - 1) for i in range(count)] if count > 1 else [0.0]

        frames: list[dict[str, Any]] = []
        for i, t in enumerate(times):
            out_path = _os.path.join(self.work_dir, f"frame_{i:02d}_{int(t)}s.jpg")
            cmd = [
                "ffmpeg", "-ss", f"{t:.3f}",
                "-i", str(path), "-frames:v", "1", "-q:v", "2",
                str(out_path),
            ]
            self.runner.transcode(cmd, float(self.config.relevance.timeout_seconds))
            frames.append({"at_seconds": round(t, 3), "path": out_path, "description": None})
        return frames


# ---------------------------------------------------------------- 款式聚类


class StyleClusterer:
    """款式聚类器（material_clustering 语义，对齐旧系统聚类规则）。

    输入：material（style_hints 款式提示列表，真实模式由 Qwen-VL 帧描述聚类产出）
    与判定器 verdict。输出：
    - style_count / styles：去重保序后的款式清单（空 → 1 个缺省款）；
    - verdict：聚类后最终判定——不相关优先淘汰（unrelated 不因多款式改判）；
      款式数 >1 → multi_style（多款式需人工确认目标款，禁止自动创建衍生商品）；
      否则沿用判定器 verdict；
    - evidence：聚类依据留痕（款式清单/判定器 verdict）。
    """

    def cluster(
        self, material: dict[str, Any], judgement: dict[str, Any]
    ) -> dict[str, Any]:
        judge_verdict = str(judgement.get("verdict") or VERDICT_RELATED)
        hints = material.get("style_hints") or []
        if isinstance(hints, str):
            hints = [hints]
        styles: list[str] = []
        for h in hints:
            text = str(h or "").strip()
            if text and text not in styles:
                styles.append(text)

        if judge_verdict == VERDICT_UNRELATED:
            # 不相关优先淘汰：无论款式多少都不进入询价/上架链
            verdict = VERDICT_UNRELATED
        elif len(styles) > 1:
            # 多款式必须人工确认目标款（08-17 修正后的收敛规则）
            verdict = VERDICT_MULTI_STYLE
        else:
            verdict = judge_verdict

        return {
            "verdict": verdict,
            "label": _VERDICT_LABEL[verdict],
            "style_count": max(1, len(styles)),
            "styles": styles or ["单款（无款式提示，按 1 款计）"],
            "judge_verdict": judge_verdict,
            "evidence": {
                "style_hints": styles,
                "judge_verdict": judge_verdict,
                "clustered_verdict": verdict,
            },
        }


# ---------------------------------------------------------------- 工厂与便捷入口


def build_relevance_judge(config: Optional[M3Config] = None) -> RelevanceJudge:
    """按 config.relevance.mode 构造判定器：auto（默认，有 Key 自动真实）/ mock / qwen。

    - mock → MockRelevanceJudge（fixtures 确定性，零 Key 零外网）；
    - qwen → 无 Key 抛 RelevanceJudgeError（不静默）；有 Key → QwenVLRelevanceJudge 骨架；
    - auto → 有 Key 走真实骨架，无 Key 自动降级 mock（环境就绪自动启用真实模式）；
    - 未知 mode → 抛错显式暴露配置错误。
    """
    cfg = config or load_config()
    mode = str(cfg.relevance.mode or "auto").strip().lower()
    if mode == "mock":
        return MockRelevanceJudge(cfg)
    if mode == "qwen":
        if not detect_qwen_vl(cfg):
            raise RelevanceJudgeError(
                "UNEXPECTED",
                f"relevance.mode=qwen 但未检测到环境变量 {cfg.relevance.api_key_env}"
                "（密钥仅走环境变量，禁止明文配置）",
                evidence={"api_key_env": cfg.relevance.api_key_env},
            )
        return QwenVLRelevanceJudge(cfg)
    if mode == "auto":
        return QwenVLRelevanceJudge(cfg) if detect_qwen_vl(cfg) else MockRelevanceJudge(cfg)
    raise RelevanceJudgeError("UNEXPECTED", f"未知 relevance.mode: {mode!r}")


def build_frame_sampler(
    config: Optional[M3Config] = None,
    runner: Any = None,
    work_dir: Optional[str] = None,
) -> FrameSampler:
    """按 config.relevance.mode 构造抽帧器（与 build_relevance_judge 同策略）。

    真实模式（qwen / auto 且有 Key）需要 ffmpeg 抽帧——ffmpeg 缺失时构造
    FFmpegFrameSampler 抛 RelevanceJudgeError（含安装指引，不静默降级）。
    """
    cfg = config or load_config()
    mode = str(cfg.relevance.mode or "auto").strip().lower()
    if mode == "mock":
        return MockFrameSampler(cfg)
    if mode == "qwen":
        return FFmpegFrameSampler(cfg, runner=runner, work_dir=work_dir)
    if mode == "auto":
        return FFmpegFrameSampler(cfg, runner=runner, work_dir=work_dir) if detect_qwen_vl(cfg) else MockFrameSampler(cfg)
    raise RelevanceJudgeError("UNEXPECTED", f"未知 relevance.mode: {mode!r}")


def judge_relevance(
    material: dict[str, Any],
    config: Optional[M3Config] = None,
    judge: Optional[RelevanceJudge] = None,
    frame_sampler: Optional[FrameSampler] = None,
    clusterer: Optional[StyleClusterer] = None,
) -> dict[str, Any]:
    """模块级便捷入口：抽帧 → 判定 → 款式聚类（纯函数，不落库）。

    返回：{"verdict","label","confidence","reason","result","style_count","styles",
           "frames","mode","evidence"}——result 为落库口径 pass/reject/manual_review
    （对齐 opt_review_records.result：related→pass / unrelated→reject /
    multi_style→manual_review）。
    """
    cfg = config or load_config()
    j = judge or build_relevance_judge(cfg)
    fs = frame_sampler or build_frame_sampler(cfg)
    cl = clusterer or StyleClusterer()

    frames = fs.extract_frames(material)
    judgement = j.judge(material, frames)
    clustering = cl.cluster(material, judgement)
    verdict = clustering["verdict"]
    result = VERDICT_TO_RESULT[verdict]

    return {
        "verdict": verdict,
        "label": clustering["label"],
        "confidence": float(judgement.get("confidence") or 1.0),
        "reason": str(judgement.get("reason") or ""),
        "result": result,
        "style_count": clustering["style_count"],
        "styles": clustering["styles"],
        "frames": [
            {"at_seconds": f.get("at_seconds"), "description": f.get("description")}
            for f in frames
        ],
        "mode": getattr(j, "mode", "unknown"),
        "evidence": {
            "judge": judgement.get("evidence") or {},
            "clustering": clustering.get("evidence") or {},
        },
    }
