"""M2 自动收集素材 · ffmpeg 标准化器（子代理 C）。

职责：环境探测 → ffprobe 元数据提取 → 素材硬规格校验 → ffmpeg 转码 → 转码后复检
（入库预检 + 标准化后复检双校验，R-M2-12 / P-007 防复发）。

设计要点：
- 可插拔 Runner 抽象：`FFmpegRunner`（probe / transcode），真实实现
  `FFmpegProcessRunner` 走 subprocess，测试注入用 `MockFFmpegRunner` 零真实
  ffmpeg 依赖（R-M2-17）——本机 ffmpeg/ffprobe 未安装（环境事实已探测），
  全部功能与测试先以 mock 模式交付，环境就绪后无需改代码即切换。
- ffmpeg/ffprobe 缺失：raise `NormalizerError`（含缺失提示与安装指引，
  不静默，R-M2-15）。
- 转码参数对齐 05 文档第三节锁定示例
  `ffmpeg -i in.mp4 -vf scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2
   -t 300 -c:v libx264 -crf 23 -c:a aac output.mp4`，
  参数集中配置（config.normalize），按素材源微调只改配置。
- 硬规格常量引用 config.py（P-007 唯一口径）：≥720×1280、9:16（±ratio_tolerance）、
  MOV/MP4、≤500M、5~300s。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .config import (
    ALLOWED_FORMATS,
    MAX_DURATION,
    MAX_SIZE_BYTES,
    MIN_DURATION,
    MIN_HEIGHT,
    MIN_RATIO,
    MIN_WIDTH,
    load_config,
)

# 宽高比与 9/16 的默认容差（config.normalize.ratio_tolerance 默认同值；
# Normalizer 用配置值，独立调用 validate_specs 时用本常量）
RATIO_TOLERANCE: float = 0.01

# ffmpeg 缺失时的安装指引（R-M2-15 错误信息必须包含；只写通用安装方式，不含任何敏感信息）
INSTALL_GUIDANCE: str = (
    "安装指引：Windows 用 `winget install ffmpeg` 或从 https://ffmpeg.org/download.html 下载；"
    "macOS 用 `brew install ffmpeg`；Linux 用 `apt install ffmpeg`。"
    "或将 ffmpeg/ffprobe 所在目录加入 PATH，"
    "或设置环境变量 MATERIALS_FFMPEG_PATH / MATERIALS_FFPROBE_PATH 指向可执行文件后重试。"
)

# 转码 spec 默认值（runner 层兜底，与 config.normalize 默认值一致；
# Normalizer 构建 spec 时以 config.normalize 为准，对齐 05 文档第三节锁定示例）
SPEC_DEFAULTS: dict[str, Any] = {
    "video_filter": (
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2"
    ),
    "duration_limit": MAX_DURATION,  # -t 300
    "video_codec": "libx264",
    "crf": 23,
    "audio_codec": "aac",
    "output_format": "mp4",
}


class NormalizerError(Exception):
    """标准化器错误：ffmpeg/ffprobe 缺失、探测/转码失败、元数据解析失败。

    错误信息含缺失提示与安装指引（R-M2-15），由调用方决定记录/上抛，
    绝不静默吞掉（R-M2-15 防复发）。
    """


def detect_ffmpeg() -> str | None:
    """探测 ffmpeg 可执行（环境变量 MATERIALS_FFMPEG_PATH 优先，其次 PATH 的 ffmpeg）。

    返回版本字符串（`ffmpeg -version` 首行）或 None；绝不抛异常
    （R-M2-15 的"不静默"由调用方根据 None 显式报错）。
    """
    exe = os.environ.get("MATERIALS_FFMPEG_PATH") or shutil.which("ffmpeg")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-version"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    first = (proc.stdout or "").splitlines()[0].strip() if proc.stdout else ""
    return first or str(exe)


def _as_float(value: Any) -> float | None:
    """宽松转 float：None/非法值 → None（缺字段按失败项处理，不抛异常）。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_specs(meta: dict, *, ratio_tolerance: float | None = None) -> dict:
    """校验元数据是否满足素材硬规格（config.py 常量，P-007 唯一口径）。

    - 分辨率 ≥ MIN_WIDTH×MIN_HEIGHT（720×1280）
    - 宽高比 ≈ 9:16（容差 ratio_tolerance，默认 RATIO_TOLERANCE=0.01）
    - 格式 mp4/mov（大小写不敏感，ALLOWED_FORMATS）
    - 大小 ≤ MAX_SIZE_BYTES（500M）
    - 时长 MIN_DURATION ~ MAX_DURATION（5~300 秒）

    返回 {"passed": bool, "failures": [{"field", "reason", "value"}, ...]}，
    逐项解释可人工核对；缺字段/非法值记对应失败项，不抛异常。
    """
    tol = RATIO_TOLERANCE if ratio_tolerance is None else ratio_tolerance
    failures: list[dict[str, Any]] = []

    def _fail(field: str, reason: str, value: Any) -> None:
        failures.append({"field": field, "reason": reason, "value": value})

    width = _as_float(meta.get("width"))
    height = _as_float(meta.get("height"))
    if width is None or height is None:
        _fail(
            "resolution",
            f"缺少宽/高元数据（width={meta.get('width')!r}, height={meta.get('height')!r}）",
            meta.get("resolution"),
        )
    else:
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            _fail(
                "resolution",
                f"分辨率不足（硬规格 ≥{MIN_WIDTH}×{MIN_HEIGHT}）",
                f"{width:.0f}x{height:.0f}",
            )
        if height > 0:
            ratio = width / height
            if abs(ratio - MIN_RATIO) > tol + 1e-9:
                _fail(
                    "ratio",
                    f"宽高比偏离 9:16（容差 ±{tol} 内通过）",
                    f"{ratio:.4f}",
                )

    fmt = str(meta.get("format") or "").lower()
    if fmt not in ALLOWED_FORMATS:
        _fail("format", f"格式不允许（硬规格：{'/'.join(ALLOWED_FORMATS)}）", meta.get("format"))

    size = _as_float(meta.get("size"))
    if size is None:
        _fail("size", "缺少文件大小元数据", meta.get("size"))
    elif size > MAX_SIZE_BYTES:
        _fail("size", f"文件过大（硬规格 ≤{MAX_SIZE_BYTES} 字节）", meta.get("size"))

    duration = _as_float(meta.get("duration"))
    if duration is None:
        _fail("duration", "缺少时长元数据", meta.get("duration"))
    elif duration < MIN_DURATION or duration > MAX_DURATION:
        _fail(
            "duration",
            f"时长越界（硬规格 {MIN_DURATION}~{MAX_DURATION} 秒）",
            meta.get("duration"),
        )

    return {"passed": not failures, "failures": failures}


class FFmpegRunner(ABC):
    """ffmpeg/ffprobe 执行抽象（可插拔：真实子进程 vs 测试 mock）。

    - probe(path) -> dict：元数据 {duration, width, height, resolution, size, fps, bitrate, format, ...}
    - transcode(input_path, output_path, spec) -> dict：{success, output_path, elapsed_seconds}
    ffmpeg 缺失时实现方 raise NormalizerError（不静默，R-M2-15）。
    """

    @abstractmethod
    def probe(self, path: str | Path) -> dict:
        """提取素材元数据（ffprobe JSON 解析）。"""

    @abstractmethod
    def transcode(self, input_path: str | Path, output_path: str | Path, spec: dict | None = None) -> dict:
        """转码为硬规格输出；spec 为 None 时用 SPEC_DEFAULTS。"""


class FFmpegProcessRunner(FFmpegRunner):
    """真实实现：子进程调用 ffprobe/ffmpeg（subprocess.run，超时配置化）。

    ffmpeg/ffprobe 缺失 → raise NormalizerError（含缺失提示与安装指引，R-M2-15）；
    转码/探测超时 → NormalizerError（R-M2-16 资源占用保护）。
    """

    def __init__(
        self,
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.timeout_seconds = timeout_seconds

    # ------------------------------------------------------------- 可执行解析
    def _resolve_ffmpeg(self) -> str:
        if self.ffmpeg_path:
            p = Path(self.ffmpeg_path)
            if p.exists():
                return str(p)
            raise NormalizerError(
                f"ffmpeg 缺失：配置/环境变量指定路径不存在（{self.ffmpeg_path}）。{INSTALL_GUIDANCE}"
            )
        found = shutil.which("ffmpeg")
        if found:
            return found
        raise NormalizerError(
            f"ffmpeg 缺失：PATH 与 MATERIALS_FFMPEG_PATH 均未找到 ffmpeg。{INSTALL_GUIDANCE}"
        )

    def _resolve_ffprobe(self) -> str:
        if self.ffprobe_path:
            p = Path(self.ffprobe_path)
            if p.exists():
                return str(p)
            raise NormalizerError(
                f"ffprobe 缺失：配置/环境变量指定路径不存在（{self.ffprobe_path}）。{INSTALL_GUIDANCE}"
            )
        if self.ffmpeg_path:
            sibling = Path(self.ffmpeg_path).parent / "ffprobe"
            if sibling.exists():
                return str(sibling)
        found = shutil.which("ffprobe")
        if found:
            return found
        raise NormalizerError(
            f"ffprobe 缺失：PATH 未找到 ffprobe（ffmpeg 通常自带，请一并安装）。{INSTALL_GUIDANCE}"
        )

    # ------------------------------------------------------------- probe
    def probe(self, path: str | Path) -> dict:
        p = Path(path)
        if not p.exists():
            raise NormalizerError(f"输入文件不存在: {p}")
        ffprobe = self._resolve_ffprobe()  # 缺失 → NormalizerError（含指引）
        cmd = [
            ffprobe,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(p),
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout_seconds
            )
        except subprocess.TimeoutExpired:
            raise NormalizerError(
                f"ffprobe 探测超时（>{self.timeout_seconds}s）: {p}（R-M2-16 资源占用保护）"
            ) from None
        except OSError as exc:
            raise NormalizerError(f"ffprobe 执行失败: {exc}") from None
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()[:500]
            raise NormalizerError(f"ffprobe 解析失败（exit {proc.returncode}）: {stderr}")
        try:
            data = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise NormalizerError(f"ffprobe 输出非 JSON，无法解析: {exc}") from None
        return self._parse_probe_json(data, str(p))

    def _parse_probe_json(self, data: dict, path: str) -> dict:
        """ffprobe JSON → 本模块元数据口径（context 1.3 数据字典对齐）。"""
        fmt = data.get("format") or {}
        streams = data.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), None)

        width = height = None
        if video:
            width = _as_float(video.get("width"))
            height = _as_float(video.get("height"))
        resolution = (
            f"{width:.0f}x{height:.0f}" if width is not None and height is not None else None
        )

        duration = None
        for src in (fmt.get("duration"), (video or {}).get("duration")):
            if src not in (None, "", "N/A", "0"):
                duration = _as_float(src)
                if duration is not None:
                    break

        size = None
        if fmt.get("size") not in (None, "", "N/A", "0"):
            size = _as_float(fmt.get("size"))

        fps = None
        if video:
            fps = self._parse_fps(video.get("avg_frame_rate")) or self._parse_fps(
                video.get("r_frame_rate")
            )

        bitrate = None
        if fmt.get("bit_rate") not in (None, "", "N/A", "0"):
            bitrate = _as_float(fmt.get("bit_rate"))
        if bitrate is None and duration and size:
            bitrate = int(size * 8 / duration)  # 缺 bit_rate 时按 size/duration 折算

        # 容器名（ffprobe format_name 首段，如 mp4 常见 "mov,mp4,m4a,3gp,3g2,mj2"）
        container = (fmt.get("format_name") or "").split(",")[0].strip().lower() or "unknown"
        # 硬规格口径：格式以扩展名为准（format_name 无法可靠区分 mp4/mov）
        ext = Path(path).suffix.lower().lstrip(".") or "unknown"

        return {
            "path": path,
            "duration": duration,
            "width": int(width) if width is not None else None,
            "height": int(height) if height is not None else None,
            "resolution": resolution,
            "size": int(size) if size is not None else None,
            "fps": fps,
            "bitrate": int(bitrate) if bitrate is not None else None,
            "format": ext,
            "container": container,
        }

    @staticmethod
    def _parse_fps(value: Any) -> float | None:
        """解析 "30000/1001" / "30.0" / "N/A" 形式的帧率。"""
        if value in (None, "", "N/A"):
            return None
        s = str(value)
        try:
            if "/" in s:
                num, _, den = s.partition("/")
                n, d = float(num), float(den)
                return n / d if d else None
            return float(s)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------- transcode
    def transcode(self, input_path: str | Path, output_path: str | Path, spec: dict | None = None) -> dict:
        ffmpeg = self._resolve_ffmpeg()  # 缺失 → NormalizerError（含安装指引，R-M2-15）
        merged = {**SPEC_DEFAULTS, **(spec or {})}
        cmd = [
            ffmpeg,
            "-y",
            "-i", str(input_path),
            "-vf", merged["video_filter"],
            "-t", str(merged["duration_limit"]),
            "-c:v", merged["video_codec"],
            "-crf", str(merged["crf"]),
            "-c:a", merged["audio_codec"],
            str(output_path),
        ]
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout_seconds
            )
        except subprocess.TimeoutExpired:
            raise NormalizerError(
                f"ffmpeg 转码超时（>{self.timeout_seconds}s）: {input_path}（R-M2-16 资源占用保护）"
            ) from None
        except OSError as exc:
            raise NormalizerError(f"ffmpeg 执行失败: {exc}") from None
        elapsed = time.monotonic() - start
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()[-500:]
            raise NormalizerError(f"ffmpeg 转码失败（exit {proc.returncode}）: {stderr}")
        if not Path(output_path).exists():
            raise NormalizerError(f"ffmpeg 转码返回成功但输出文件不存在: {output_path}")
        return {
            "success": True,
            "output_path": str(output_path),
            "elapsed_seconds": round(elapsed, 3),
        }


class MockFFmpegRunner(FFmpegRunner):
    """测试注入用：不依赖真实 ffmpeg 二进制（R-M2-17 零真实 ffmpeg 依赖）。

    - metadata 为 dict：每次 probe 返回同一份副本；
    - metadata 为 list：按调用次序逐次弹出（配合"预检通过/复检失败"等场景）；
    - probe_raises：注入异常（如 NormalizerError），验证错误传播路径；
    - probe_calls / transcode_calls 记录调用，供测试断言。
    """

    def __init__(
        self,
        metadata: dict | list[dict] | None = None,
        transcode_result: dict | None = None,
        probe_raises: Exception | None = None,
    ) -> None:
        self.metadata: dict | list[dict] = metadata if metadata is not None else {}
        self.transcode_result: dict = transcode_result or {
            "success": True,
            "output_path": None,
            "elapsed_seconds": 0.0,
        }
        self.probe_raises: Exception | None = probe_raises
        self.probe_calls: list[str] = []
        self.transcode_calls: list[tuple] = []

    def probe(self, path: str | Path) -> dict:
        self.probe_calls.append(str(path))
        if self.probe_raises is not None:
            raise self.probe_raises
        if isinstance(self.metadata, list):
            if not self.metadata:
                raise AssertionError(
                    f"MockFFmpegRunner: probe 调用次数({len(self.probe_calls)})超出注入 metadata 数量"
                )
            meta = dict(self.metadata.pop(0))
        else:
            meta = dict(self.metadata)
        meta.setdefault("path", str(path))
        return meta

    def transcode(self, input_path: str | Path, output_path: str | Path, spec: dict | None = None) -> dict:
        self.transcode_calls.append((str(input_path), str(output_path), dict(spec or {})))
        return dict(self.transcode_result)


class Normalizer:
    """素材标准化器：probe 预检 → ffmpeg 转码 → 转码后复检硬规格（双校验，R-M2-12）。

    - probe(path)：透传 runner
    - validate(path)：probe + validate_specs（入库预检用）
    - normalize(input_path, output_path=None)：全链路，输出目录自动创建；
      ffmpeg 缺失时 probe/transcode 均 raise NormalizerError（R-M2-15）。
    """

    def __init__(self, runner: FFmpegRunner, config=None) -> None:
        self.runner = runner
        self.config = config if config is not None else load_config()

    def probe(self, path: str | Path) -> dict:
        """透传 runner.probe（元数据提取）。"""
        return self.runner.probe(path)

    def validate(self, path: str | Path) -> dict:
        """入库预检：probe + 硬规格校验。返回 {passed, failures, meta}。"""
        meta = self.runner.probe(path)
        result = validate_specs(meta, ratio_tolerance=self.config.normalize.ratio_tolerance)
        result["meta"] = meta
        return result

    def normalize(self, input_path: str | Path, output_path: str | Path | None = None) -> dict:
        """标准化全链路（双校验 R-M2-12）：

        ① probe 预检（元数据提取；ffmpeg 缺失时 runner 已 raise NormalizerError）
        ② ffmpeg 转码（命令对齐 05 文档第三节锁定示例，参数取 config.normalize）
        ③ 转码后 probe 复检硬规格
        返回 {output_path, meta_before, meta_after, transcode, passed, failures}；
        输出目录不存在时自动创建。
        """
        input_path = str(input_path)
        meta_before = self.runner.probe(input_path)  # ① 预检

        if output_path is None:
            src = Path(input_path)
            output_path = str(
                src.with_name(src.stem + ".normalized." + self.config.normalize.output_format)
            )
        out = Path(output_path)
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True, exist_ok=True)  # 输出目录自动建

        spec = self._build_spec()
        transcode = self.runner.transcode(input_path, str(out), spec)  # ② 转码

        meta_after = self.runner.probe(str(out))  # ③ 复检（双校验）
        check = validate_specs(meta_after, ratio_tolerance=self.config.normalize.ratio_tolerance)
        return {
            "output_path": str(out),
            "meta_before": meta_before,
            "meta_after": meta_after,
            "transcode": transcode,
            "passed": check["passed"],
            "failures": check["failures"],
        }

    def _build_spec(self) -> dict:
        """从 config.normalize 构建转码 spec（参数集中，按素材源可微调，宪法第 8 节配置化）。"""
        cfg = self.config.normalize
        return {
            "video_filter": cfg.video_filter,
            "duration_limit": cfg.duration_limit,
            "video_codec": "libx264",
            "crf": cfg.crf,
            "audio_codec": "aac",
            "output_format": cfg.output_format,
            "timeout_seconds": cfg.transcode_timeout_seconds,
        }
