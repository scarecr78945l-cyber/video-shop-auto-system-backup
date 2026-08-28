"""M3 视频二创流水线 · ffmpeg/ffprobe 层（子代理-C1 · v0.3）。

对齐方案文档 05 第三节（ffmpeg 输出参数锁定示例）与 06 第一节（硬性输出规格），
以及 _management/modules/m3-optimization/context/README.md 数据字典与 P-007
（素材不合规格被平台拒审）。五维硬规格：分辨率 ≥720×1280｜9:16（容差 ±0.01）｜
MOV/MP4｜≤500M｜时长 5~300s（config.VideoSpec）。

实现策略（本机 ffmpeg/ffprobe 未安装，已探测确认）：先实现 + 测试用 Mock，
环境就绪后自动切换 ——
- ``detect_ffmpeg()``：探测 ffmpeg/ffprobe（env M3_FFMPEG_PATH / M3_FFPROBE_PATH 优先，
  兼容 FFMPEG_PATH / FFPROBE_PATH，再走 PATH）；两者齐备返回版本字符串，否则 None，绝不抛异常。
- ``FFmpegProcessRunner``：subprocess 实现（ffprobe JSON 探测 + ffmpeg 转码）；二进制缺失
  raise ``VideoToolError``（含安装指引：winget / ffmpeg.org 官网 / brew / apt / M3_FFMPEG_PATH），不静默。
- ``MockFFmpegRunner``：测试注入（probe 返回预设元数据，transcode 记录命令供断言）。
- ``validate_specs``：五维校验，返回逐项可解释的 failures（对齐 P-007 出片后必须 ffprobe 校验）。
- ``build_transcode_cmd``：构造 ffmpeg 命令（scale/pad 打底 + -t 时长上限 + libx264/aac），
  参数全部取 config.video（由编排层 C2 传入 spec=config.video），禁止硬编码散落。

错误码：VideoToolError.error_code 限定 WorkflowJob 码表子集 TIMEOUT/UNEXPECTED/NO_MATCH
（其余归一 UNEXPECTED；对齐 09 文档错误码表与 M0 workflow_jobs，供 C2 编排层直接映射 job 失败）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import Any

# WorkflowJob 错误码表子集（本层可用；其余码归一 UNEXPECTED）
VIDEO_ERROR_CODES = frozenset({"TIMEOUT", "UNEXPECTED", "NO_MATCH"})

INSTALL_GUIDANCE = (
    "ffmpeg/ffprobe 未安装或不可用（detect_ffmpeg() 返回 None）。"
    "安装指引：Windows 可用 winget install ffmpeg 或从官网 https://ffmpeg.org/download.html 下载；"
    "macOS: brew install ffmpeg；Linux: apt install ffmpeg。"
    "也可通过环境变量 M3_FFMPEG_PATH / M3_FFPROBE_PATH（兼容 FFMPEG_PATH / FFPROBE_PATH）直接指定二进制路径。"
)

# 环境变量优先级：M3_* 优先，兼容 context/README 外部契约的裸名，再走 PATH
_ENV_FFMPEG = ("M3_FFMPEG_PATH", "FFMPEG_PATH")
_ENV_FFPROBE = ("M3_FFPROBE_PATH", "FFPROBE_PATH")

# 05 文档锁定 filter 模板（W/H 来自 config.video，见 build_transcode_cmd）
_SCALE_PAD_TEMPLATE = (
    "scale={w}:{h}:force_original_aspect_ratio=decrease,"
    "pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
)
# 视频编码器固定 libx264（config.VideoSpec 未设 video_codec，05 文档锁定示例）
VIDEO_CODEC = "libx264"

# config.VideoSpec 默认值兜底（spec 未传/缺字段时与 config.video 一致；正常由 C2 传 spec=config.video）
_DEF_MIN_WIDTH = 720
_DEF_MIN_HEIGHT = 1280
_DEF_ASPECT = "9:16"
_DEF_FORMATS: tuple[str, ...] = ("mov", "mp4")
_DEF_MAX_SIZE_MB = 500
_DEF_MIN_DURATION = 5
_DEF_MAX_DURATION = 300
_DEF_CRF = 23
_DEF_AUDIO_CODEC = "aac"


# ---------------------------------------------------------------- 工具函数


def _decode(data: bytes) -> str:
    """bytes → str：UTF-8 优先，Windows 工具输出 GBK 时回退，绝不抛异常。"""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("gbk")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")


def _excerpt(text: str, limit: int = 300) -> str:
    """截断文本（错误信息留证据，避免刷屏）。"""
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _spec_value(spec: Any, name: str, default: Any) -> Any:
    """从 VideoSpec（pydantic）或 dict 取值；None/缺字段回退 default（对齐 config.VideoSpec）。"""
    if spec is None:
        return default
    if isinstance(spec, dict):
        return spec.get(name, default)
    return getattr(spec, name, default)


def _aspect_to_float(aspect: str) -> float:
    """'9:16' → 9/16；解析失败回退 0.5625。"""
    try:
        w, h = str(aspect).split(":")
        return float(w) / float(h)
    except (ValueError, ZeroDivisionError):
        return 9.0 / 16.0


# ---------------------------------------------------------------- 二进制探测


def _resolve_binary(name: str, env_keys: tuple[str, ...]) -> str | None:
    """env 优先（M3_* 优先于裸名）→ PATH；找不到返回 None（不抛异常）。"""
    for key in env_keys:
        value = os.environ.get(key)
        if value:
            return value
    return shutil.which(name)


def _query_version(binary: str, args: list[str] | None = None) -> str | None:
    """运行 <binary> -version 取首行；任何失败返回 None（绝不抛异常）。"""
    try:
        proc = subprocess.run(
            [binary] + list(args or ["-version"]),
            capture_output=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = _decode(proc.stdout).strip() or _decode(proc.stderr).strip()
    return out.splitlines()[0] if out else None


def detect_ffmpeg() -> str | None:
    """探测 ffmpeg/ffprobe（env M3_FFMPEG_PATH/M3_FFPROBE_PATH 优先 → PATH）。

    两者都必须可用才返回 ffmpeg 版本字符串；缺任一 / 版本查询失败均返回 None。
    绝不抛异常（缺 ffmpeg 或缺 ffprobe 均返回 None）。
    """
    try:
        ffmpeg = _resolve_binary("ffmpeg", _ENV_FFMPEG)
        if not ffmpeg:
            return None
        version = _query_version(ffmpeg)
        if version is None:
            return None
        ffprobe = _resolve_binary("ffprobe", _ENV_FFPROBE)
        if not ffprobe:
            return None
        if _query_version(ffprobe) is None:
            return None
        return version
    except Exception:  # noqa: BLE001 —— 探测绝不抛异常
        return None


# ---------------------------------------------------------------- 异常


class VideoToolError(Exception):
    """ffmpeg/ffprobe 调用异常，error_code 限定 WorkflowJob 码表（TIMEOUT/UNEXPECTED/NO_MATCH）。"""

    def __init__(self, error_code: str, message: str = "", evidence: dict | None = None):
        if error_code not in VIDEO_ERROR_CODES:
            error_code = "UNEXPECTED"
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message
        self.evidence = evidence or {}


# ---------------------------------------------------------------- Runner


class FFmpegRunner(ABC):
    """视频工具抽象基类：probe（ffprobe 元数据探测）+ transcode（ffmpeg 转码）。

    子类：FFmpegProcessRunner（subprocess 真实执行）/ MockFFmpegRunner（测试注入）。
    """

    @abstractmethod
    def probe(self, path: str) -> dict:
        """返回 {width, height, duration, size_bytes, format}；失败抛 VideoToolError。"""

    @abstractmethod
    def transcode(self, cmd: list[str], timeout: float) -> None:
        """执行转码命令；失败抛 VideoToolError。"""


class FFmpegProcessRunner(FFmpegRunner):
    """subprocess 实现：ffprobe JSON 探测 + ffmpeg 转码；二进制缺失即 raise（不静默）。

    二进制解析顺序：构造参数 → env（M3_FFMPEG_PATH/M3_FFPROBE_PATH 优先，
    兼容 FFMPEG_PATH/FFPROBE_PATH）→ PATH；任一缺失或不可用 → VideoToolError（含安装指引）。
    """

    def __init__(
        self,
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
        timeout: float = 300.0,
    ):
        self.ffmpeg_path = ffmpeg_path or _resolve_binary("ffmpeg", _ENV_FFMPEG)
        self.ffprobe_path = ffprobe_path or _resolve_binary("ffprobe", _ENV_FFPROBE)
        self.timeout = float(timeout)
        if not self._binary_ok(self.ffmpeg_path) or not self._binary_ok(self.ffprobe_path):
            raise VideoToolError("UNEXPECTED", INSTALL_GUIDANCE)

    @staticmethod
    def _binary_ok(path: str | None) -> bool:
        return bool(path) and os.path.isfile(path)

    def probe(self, path: str) -> dict:
        """ffprobe -print_format json -show_format -show_streams 探测，返回五键元数据。"""
        if not self._binary_ok(self.ffprobe_path):
            raise VideoToolError("UNEXPECTED", INSTALL_GUIDANCE)
        cmd = [
            self.ffprobe_path, "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            raise VideoToolError(
                "TIMEOUT",
                f"ffprobe 探测超时（{self.timeout:g}s）：{path}",
                evidence={"path": str(path), "timeout_seconds": self.timeout},
            ) from e
        except OSError as e:
            raise VideoToolError(
                "UNEXPECTED",
                f"ffprobe 启动失败 {e.__class__.__name__}：{path}",
                evidence={"path": str(path)},
            ) from e
        if proc.returncode != 0:
            raise VideoToolError(
                "UNEXPECTED",
                f"ffprobe 执行失败 rc={proc.returncode}：{_excerpt(_decode(proc.stderr))}",
                evidence={"path": str(path), "returncode": proc.returncode},
            )
        try:
            data = json.loads(_decode(proc.stdout) or "{}")
        except ValueError as e:
            raise VideoToolError(
                "UNEXPECTED", f"ffprobe 输出解析失败：{e}", evidence={"path": str(path)}
            ) from e
        return _extract_probe(data, path)

    def transcode(self, cmd: list[str], timeout: float | None = None) -> None:
        """执行转码命令；argv[0]="ffmpeg"（build_transcode_cmd 占位）绑定真实二进制。

        超时 → VideoToolError(TIMEOUT)；启动失败/非零退出 → UNEXPECTED（留 stderr 摘要证据）。
        """
        if not cmd:
            raise VideoToolError("UNEXPECTED", "转码命令为空")
        argv = [str(a) for a in cmd]
        if argv[0] == "ffmpeg":
            argv[0] = self.ffmpeg_path
        else:
            argv = [self.ffmpeg_path] + argv
        t = float(timeout) if timeout is not None else self.timeout
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=t)
        except subprocess.TimeoutExpired as e:
            raise VideoToolError(
                "TIMEOUT",
                f"ffmpeg 转码超时（{t:g}s）",
                evidence={"cmd": argv, "timeout_seconds": t},
            ) from e
        except OSError as e:
            raise VideoToolError(
                "UNEXPECTED",
                f"ffmpeg 启动失败 {e.__class__.__name__}：{_excerpt(_decode(getattr(e, 'stderr', b'')))}",
                evidence={"cmd": argv},
            ) from e
        if proc.returncode != 0:
            raise VideoToolError(
                "UNEXPECTED",
                f"ffmpeg 转码失败 rc={proc.returncode}：{_excerpt(_decode(proc.stderr))}",
                evidence={"cmd": argv, "returncode": proc.returncode},
            )


def _extract_probe(data: dict, path: str = "") -> dict:
    """ffprobe JSON → {width, height, duration, size_bytes, format}；无视频流 → NO_MATCH。"""
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise VideoToolError(
            "NO_MATCH",
            "未找到视频流（NO_MATCH）",
            evidence={"path": str(path), "streams": len(streams)},
        )
    fmt = data.get("format") or {}
    width = int(video["width"]) if video.get("width") is not None else None
    height = int(video["height"]) if video.get("height") is not None else None
    return {
        "width": width,
        "height": height,
        "duration": _to_float(fmt.get("duration")),
        "size_bytes": _to_int(fmt.get("size")),
        "format": str(fmt.get("format_name") or ""),
    }


class MockFFmpegRunner(FFmpegRunner):
    """测试注入：probe 返回预设元数据；transcode 只记录 (cmd, timeout) 供断言，不真跑。"""

    def __init__(self, probe_result: dict | None = None):
        self.probe_result = dict(probe_result or {})
        self.transcode_calls: list[tuple[list[str], float]] = []

    def probe(self, path: str) -> dict:
        return dict(self.probe_result)

    def transcode(self, cmd: list[str], timeout: float) -> None:
        self.transcode_calls.append((list(cmd), float(timeout)))


# ---------------------------------------------------------------- 硬规格校验


def validate_specs(probe: dict, spec) -> dict:
    """五维硬规格校验（对齐 05/06 硬规格与 P-007）。

    probe 形如 {width, height, duration, size_bytes, format}（FFmpegRunner.probe 输出）。
    返回 {'passed': bool, 'failures': [{'field', 'reason', 'value'}]}，逐项可解释：
    resolution（≥min_width×min_height）/ aspect（9:16，容差 ±0.01）/ format（mov/mp4）/
    size（≤max_size_mb，bytes 换算）/ duration（min_duration ~ max_duration 秒）。
    """
    failures: list[dict[str, Any]] = []
    min_w = int(_spec_value(spec, "min_width", _DEF_MIN_WIDTH))
    min_h = int(_spec_value(spec, "min_height", _DEF_MIN_HEIGHT))
    aspect_spec = str(_spec_value(spec, "aspect", _DEF_ASPECT))
    formats = tuple(_spec_value(spec, "formats", _DEF_FORMATS))
    max_mb = int(_spec_value(spec, "max_size_mb", _DEF_MAX_SIZE_MB))
    min_dur = float(_spec_value(spec, "min_duration", _DEF_MIN_DURATION))
    max_dur = float(_spec_value(spec, "max_duration", _DEF_MAX_DURATION))

    # ① 分辨率
    width = probe.get("width")
    height = probe.get("height")
    if width is None or height is None:
        failures.append({
            "field": "resolution",
            "reason": "缺少分辨率字段（width/height）",
            "value": {"width": width, "height": height},
        })
    else:
        w, h = int(width), int(height)
        if w < min_w or h < min_h:
            failures.append({
                "field": "resolution",
                "reason": f"分辨率不足：需 ≥{min_w}×{min_h}（9:16 竖屏）",
                "value": f"{w}x{h}",
            })

    # ② 画面比例（9:16，容差 ±0.01）
    if width is not None and height is not None:
        hh = int(height)
        if hh <= 0:
            failures.append({
                "field": "aspect",
                "reason": "高度为 0，无法计算画面比例",
                "value": {"width": width, "height": height},
            })
        else:
            ratio = int(width) / hh
            expected = _aspect_to_float(aspect_spec)
            if abs(ratio - expected) > 0.01:
                failures.append({
                    "field": "aspect",
                    "reason": f"画面比例非 {aspect_spec}（容差 ±0.01）",
                    "value": round(ratio, 4),
                })
    else:
        failures.append({
            "field": "aspect",
            "reason": "缺少分辨率字段，无法计算画面比例",
            "value": {"width": width, "height": height},
        })

    # ③ 格式（MOV/MP4，大小写不敏感；ffprobe format_name 含多容器名，按 token 命中）
    fmt = probe.get("format")
    if fmt is None or not str(fmt).strip():
        failures.append({"field": "format", "reason": "缺少格式字段（format）", "value": fmt})
    else:
        low = str(fmt).lower()
        allowed = [str(f).lower() for f in formats]
        if not any(tok in low for tok in allowed):
            failures.append({
                "field": "format",
                "reason": f"格式不支持：仅支持 {'/'.join(formats)}",
                "value": fmt,
            })

    # ④ 大小（≤ max_size_mb，bytes 换算）
    size = probe.get("size_bytes")
    if size is None:
        failures.append({"field": "size", "reason": "缺少大小字段（size_bytes）", "value": None})
    else:
        try:
            size_int = int(size)
        except (TypeError, ValueError):
            failures.append({"field": "size", "reason": "大小字段无法解析为字节数", "value": size})
        else:
            if size_int > max_mb * 1024 * 1024:
                failures.append({
                    "field": "size",
                    "reason": f"文件过大：需 ≤{max_mb}MB",
                    "value": size_int,
                })

    # ⑤ 时长（min_duration ~ max_duration 秒）
    dur = probe.get("duration")
    if dur is None:
        failures.append({"field": "duration", "reason": "缺少时长字段（duration）", "value": None})
    else:
        try:
            d = float(dur)
        except (TypeError, ValueError):
            failures.append({"field": "duration", "reason": "时长字段无法解析为秒", "value": dur})
        else:
            if d < min_dur:
                failures.append({
                    "field": "duration",
                    "reason": f"时长过短：需 ≥{min_dur:g}s",
                    "value": d,
                })
            elif d > max_dur:
                failures.append({
                    "field": "duration",
                    "reason": f"时长过长：需 ≤{max_dur:g}s",
                    "value": d,
                })

    return {"passed": not failures, "failures": failures}


# ---------------------------------------------------------------- 命令构造


def build_transcode_cmd(input_path, output_path, spec, extra_filters: list[str] | None = None) -> list[str]:
    """构造 ffmpeg 出片命令（对齐 05 文档锁定示例）。

    - base filter：scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2
      （W/H 取 spec.min_width/min_height，即 config.video）；
    - -t 时长上限取 spec.max_duration（默认 300s）；
    - -c:v libx264 -crf spec.crf（默认 23）、-c:a spec.audio_codec（默认 aac）；
    - extra_filters（字幕 drawtext/subtitles、角标等，由编排层 C2 传入）按序拼接进 -vf 链；
    - 参数一律取 config.video（spec），禁止硬编码散落；argv[0] 为 "ffmpeg" 占位，
      由 FFmpegProcessRunner.transcode 绑定真实二进制路径。
    """
    w = int(_spec_value(spec, "min_width", _DEF_MIN_WIDTH))
    h = int(_spec_value(spec, "min_height", _DEF_MIN_HEIGHT))
    max_dur = int(_spec_value(spec, "max_duration", _DEF_MAX_DURATION))
    crf = int(_spec_value(spec, "crf", _DEF_CRF))
    audio_codec = str(_spec_value(spec, "audio_codec", _DEF_AUDIO_CODEC))

    filters = [_SCALE_PAD_TEMPLATE.format(w=w, h=h)]
    if extra_filters:
        filters.extend(str(f) for f in extra_filters)
    vf = ",".join(filters)

    return [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-t", str(max_dur),
        "-c:v", VIDEO_CODEC,
        "-crf", str(crf),
        "-c:a", audio_codec,
        str(output_path),
    ]
