"""materials.normalizer 单元测试：ffmpeg 标准化器（mock 模式全覆盖，零真实 ffmpeg 依赖）。

场景（任务书验收）：
  ① validate_specs 边界用例全覆盖（分辨率 719×1279 拒 / 720×1280 过、比例 0.5 拒 / 9:16 过、
     时长 4s 拒 / 5s 过 / 301s 拒 / 300s 过、大小 524288001 拒 / 524288000 过、
     格式 avi 拒 / mp4·MOV 过）
  ② probe 解析：MockFFmpegRunner 注入 dict 透传正确
  ③ normalize 全链路（mock）：预检→转码→复检→passed/failures 正确
  ④ detect_ffmpeg：返回 None 或版本字符串（仅断言类型）
  ⑤ FFmpegProcessRunner 在 ffmpeg 缺失时 raise NormalizerError（错误信息含「ffmpeg」与
     安装指引；不依赖真实 ffmpeg：用不存在的路径构造 runner）
  ⑥ 真实转码用例 pytest.mark.skipif(not detect_ffmpeg()) 保护：本机自动跳过，
     环境就绪后无需改代码即启用
  另：ffprobe JSON 解析、转码命令锁定（对齐 05 文档第三节示例）、超时错误、
     config.normalize 环境变量映射（MATERIALS_FFMPEG_PATH）。

纪律：pytest 一律带 --basetemp=".pytest-tmp"（P-001）；临时文件只放 tmp_path；
全程零真实 ffmpeg 依赖（R-M2-17）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from materials.config import (
    ALLOWED_FORMATS,
    MAX_DURATION,
    MAX_SIZE_BYTES,
    MIN_DURATION,
    MIN_HEIGHT,
    MIN_WIDTH,
    load_config,
)
from materials.normalizer import (
    FFmpegProcessRunner,
    FFmpegRunner,
    MockFFmpegRunner,
    Normalizer,
    NormalizerError,
    RATIO_TOLERANCE,
    detect_ffmpeg,
    validate_specs,
)

# 一份满足全部硬规格的元数据（720×1280、9:16、mp4、≤500M、5~300s）
VALID_META = {
    "duration": 30.0,
    "width": 720,
    "height": 1280,
    "resolution": "720x1280",
    "size": 1024 * 1024,
    "fps": 30.0,
    "bitrate": 1_000_000,
    "format": "mp4",
    "container": "mp4",
}


def _meta(**overrides) -> dict:
    m = dict(VALID_META)
    m.update(overrides)
    return m


# ===========================================================================
# ① validate_specs 边界用例
# ===========================================================================
class TestValidateSpecs:
    def test_resolution_boundaries(self):
        # 719×1279 拒（分辨率不足）；720×1280 过
        low = validate_specs(_meta(width=MIN_WIDTH - 1, height=MIN_HEIGHT - 1))
        assert low["passed"] is False
        assert any(f["field"] == "resolution" for f in low["failures"])

        ok = validate_specs(_meta(width=MIN_WIDTH, height=MIN_HEIGHT))
        assert ok["passed"] is True
        assert ok["failures"] == []

    def test_resolution_individual_axis(self):
        # 单轴不足同样拒
        for m in (_meta(width=719, height=1280), _meta(width=720, height=1279)):
            r = validate_specs(m)
            assert r["passed"] is False
            assert any(f["field"] == "resolution" for f in r["failures"])

    def test_ratio_9_16_passes(self):
        # 720×1280 = 0.5625 = 9/16 精确通过
        r = validate_specs(_meta(width=720, height=1280))
        assert r["passed"] is True

    def test_ratio_0_5_rejected(self):
        # 640×1280 = 0.5，偏离 9/16 0.0625 > 容差 0.01 → 拒
        r = validate_specs(_meta(width=640, height=1280))
        assert r["passed"] is False
        assert any(f["field"] == "ratio" for f in r["failures"])

    def test_ratio_within_tolerance_passes(self):
        # 730/1280 ≈ 0.5703，偏离 0.0078 < 0.01 → 过
        r = validate_specs(_meta(width=730, height=1280))
        assert r["passed"] is True

    def test_ratio_beyond_tolerance_rejected(self):
        # 768/1280 = 0.6，偏离 0.0375 > 0.01 → 拒
        r = validate_specs(_meta(width=768, height=1280))
        assert r["passed"] is False
        assert any(f["field"] == "ratio" for f in r["failures"])

    def test_ratio_tolerance_override(self):
        # 显式放宽容差后，0.6 的比例可过
        r = validate_specs(_meta(width=768, height=1280), ratio_tolerance=0.1)
        assert r["passed"] is True

    def test_duration_boundaries(self):
        assert validate_specs(_meta(duration=MIN_DURATION - 1))["passed"] is False  # 4s 拒
        assert validate_specs(_meta(duration=MIN_DURATION))["passed"] is True       # 5s 过
        assert validate_specs(_meta(duration=MAX_DURATION + 1))["passed"] is False  # 301s 拒
        assert validate_specs(_meta(duration=MAX_DURATION))["passed"] is True       # 300s 过

    def test_size_boundaries(self):
        assert validate_specs(_meta(size=MAX_SIZE_BYTES + 1))["passed"] is False  # 524288001 拒
        assert validate_specs(_meta(size=MAX_SIZE_BYTES))["passed"] is True       # 524288000 过

    def test_format_case_insensitive(self):
        for fmt in ("mp4", "MOV", "mov", "MP4"):
            assert validate_specs(_meta(format=fmt))["passed"] is True
        r = validate_specs(_meta(format="avi"))
        assert r["passed"] is False
        assert any(f["field"] == "format" for f in r["failures"])

    def test_allowed_formats_alignment(self):
        assert "mp4" in ALLOWED_FORMATS and "mov" in ALLOWED_FORMATS

    def test_missing_fields_recorded_not_raised(self):
        r = validate_specs({})
        assert r["passed"] is False
        fields = {f["field"] for f in r["failures"]}
        assert fields == {"resolution", "format", "size", "duration"}
        for f in r["failures"]:
            assert f["reason"] and "value" in f  # 逐项可解释

    def test_failures_are_explainable(self):
        r = validate_specs(_meta(width=640, height=1280, duration=301, size=MAX_SIZE_BYTES + 1, format="avi"))
        assert r["passed"] is False
        fields = {f["field"] for f in r["failures"]}
        assert fields == {"resolution", "ratio", "duration", "size", "format"}
        for f in r["failures"]:
            assert set(f) == {"field", "reason", "value"}


# ===========================================================================
# ② probe 透传 + MockFFmpegRunner 注入
# ===========================================================================
class TestProbePassthrough:
    def test_runner_probe_returns_injected_meta(self):
        runner = MockFFmpegRunner(metadata=_meta())
        meta = runner.probe("some/where/in.mp4")
        assert meta["width"] == 720
        assert meta["duration"] == 30.0
        assert meta["format"] == "mp4"
        assert meta["path"] == "some/where/in.mp4"  # setdefault 补 path
        assert len(runner.probe_calls) == 1

    def test_normalizer_probe_passthrough(self):
        runner = MockFFmpegRunner(metadata=_meta())
        normalizer = Normalizer(runner)
        meta = normalizer.probe("x.mp4")
        assert meta["width"] == 720
        assert meta["path"] == "x.mp4"

    def test_normalizer_validate_precheck(self):
        ok = Normalizer(MockFFmpegRunner(metadata=_meta())).validate("in.mp4")
        assert ok["passed"] is True
        assert ok["meta"]["resolution"] == "720x1280"

        bad = Normalizer(MockFFmpegRunner(metadata=_meta(format="avi"))).validate("in.mp4")
        assert bad["passed"] is False
        assert any(f["field"] == "format" for f in bad["failures"])

    def test_mock_is_ffmpeg_runner_abc(self):
        assert issubclass(MockFFmpegRunner, FFmpegRunner)
        assert issubclass(FFmpegProcessRunner, FFmpegRunner)
        with pytest.raises(TypeError):
            FFmpegRunner()  # type: ignore[abstract]


# ===========================================================================
# ③ normalize 全链路（mock）：预检→转码→复检
# ===========================================================================
class TestNormalizeFlow:
    def test_normalize_success_full_chain(self, tmp_path):
        inp = tmp_path / "in.mp4"
        out = tmp_path / "out" / "norm.mp4"
        runner = MockFFmpegRunner(
            metadata=_meta(),
            transcode_result={"success": True, "output_path": str(out), "elapsed_seconds": 1.25},
        )
        normalizer = Normalizer(runner)
        result = normalizer.normalize(str(inp), str(out))

        assert result["passed"] is True
        assert result["failures"] == []
        assert result["output_path"] == str(out)
        assert result["meta_before"]["path"] == str(inp)
        assert result["meta_after"]["path"] == str(out)
        assert result["meta_before"]["resolution"] == "720x1280"
        assert result["transcode"]["success"] is True
        # 双校验：probe 恰好 2 次（预检 + 复检），转码 1 次
        assert len(runner.probe_calls) == 2
        assert runner.probe_calls[0] == str(inp)
        assert runner.probe_calls[1] == str(out)
        assert len(runner.transcode_calls) == 1
        # 转码 spec 由 config.normalize 构建（对齐 05 示例参数）
        spec = runner.transcode_calls[0][2]
        assert spec["video_filter"].startswith("scale=720:1280")
        assert spec["crf"] == 23
        assert spec["duration_limit"] == 300

    def test_normalize_postcheck_failure(self, tmp_path):
        # 预检通过、复检失败：metadata 用 list 逐次弹出
        inp = tmp_path / "in.mp4"
        out = tmp_path / "out.mp4"
        runner = MockFFmpegRunner(metadata=[_meta(), _meta(duration=4.0)])
        result = Normalizer(runner).normalize(str(inp), str(out))
        assert result["passed"] is False
        assert any(f["field"] == "duration" for f in result["failures"])
        assert result["meta_before"]["duration"] == 30.0
        assert result["meta_after"]["duration"] == 4.0

    def test_normalize_creates_output_dir(self, tmp_path):
        out = tmp_path / "nested" / "deep" / "out.mp4"
        result = Normalizer(MockFFmpegRunner(metadata=_meta())).normalize(
            str(tmp_path / "in.mp4"), str(out)
        )
        assert result["passed"] is True
        assert out.parent.is_dir()

    def test_normalize_default_output_path(self, tmp_path):
        inp = tmp_path / "clip.mov"
        result = Normalizer(MockFFmpegRunner(metadata=_meta(format="mov"))).normalize(str(inp))
        assert result["output_path"] == str(tmp_path / "clip.normalized.mp4")  # 默认 output_format=mp4

    def test_normalize_propagates_runner_error(self, tmp_path):
        runner = MockFFmpegRunner(
            metadata=_meta(), probe_raises=NormalizerError("ffmpeg 缺失：PATH 未找到 ffmpeg。安装指引：...")
        )
        with pytest.raises(NormalizerError):
            Normalizer(runner).normalize(str(tmp_path / "in.mp4"), str(tmp_path / "out.mp4"))


# ===========================================================================
# ④ detect_ffmpeg：仅断言类型（本机 None，环境就绪后返回版本字符串）
# ===========================================================================
def test_detect_ffmpeg_returns_none_or_version_string():
    ver = detect_ffmpeg()
    assert ver is None or isinstance(ver, str)
    if ver is not None:
        assert ver.strip() != ""


def test_detect_ffmpeg_env_path_missing_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv("MATERIALS_FFMPEG_PATH", str(tmp_path / "no-such-ffmpeg.exe"))
    assert detect_ffmpeg() is None  # 路径不存在 → None，不抛异常


# ===========================================================================
# ⑤ FFmpegProcessRunner 缺失路径 → NormalizerError（含「ffmpeg」与安装指引）
# ===========================================================================
class TestProcessRunnerMissingBinary:
    def test_transcode_raises_on_missing_ffmpeg(self, tmp_path):
        runner = FFmpegProcessRunner(
            ffmpeg_path=str(tmp_path / "no-ffmpeg.exe"),
            ffprobe_path=str(tmp_path / "no-ffprobe.exe"),
        )
        inp = tmp_path / "in.mp4"
        inp.write_bytes(b"x")
        with pytest.raises(NormalizerError) as ei:
            runner.transcode(str(inp), str(tmp_path / "out.mp4"))
        msg = str(ei.value)
        assert "ffmpeg" in msg
        assert "安装" in msg  # 安装指引（R-M2-15 不静默）

    def test_probe_raises_on_missing_ffprobe(self, tmp_path):
        runner = FFmpegProcessRunner(
            ffmpeg_path=str(tmp_path / "no-ffmpeg.exe"),
            ffprobe_path=str(tmp_path / "no-ffprobe.exe"),
        )
        inp = tmp_path / "in.mp4"
        inp.write_bytes(b"x")
        with pytest.raises(NormalizerError) as ei:
            runner.probe(str(inp))
        msg = str(ei.value)
        assert "ffprobe" in msg
        assert "安装" in msg

    def test_probe_raises_on_missing_input(self, tmp_path):
        runner = FFmpegProcessRunner(ffprobe_path=str(tmp_path / "no-ffprobe.exe"))
        with pytest.raises(NormalizerError) as ei:
            runner.probe(str(tmp_path / "missing.mp4"))
        assert "输入文件不存在" in str(ei.value)


# ===========================================================================
# FFmpegProcessRunner 行为：ffprobe JSON 解析 / 命令锁定 / 超时（不执行真实二进制）
# ===========================================================================
class TestProcessRunnerBehavior:
    def _fake_binaries(self, tmp_path):
        ffmpeg = tmp_path / "ffmpeg.exe"
        ffprobe = tmp_path / "ffprobe.exe"
        ffmpeg.write_text("fake", encoding="utf-8")
        ffprobe.write_text("fake", encoding="utf-8")
        return ffmpeg, ffprobe

    def test_probe_parses_ffprobe_json(self, tmp_path, monkeypatch):
        ffmpeg, ffprobe = self._fake_binaries(tmp_path)
        sample = {
            "format": {
                "duration": "30.5",
                "size": "1048576",
                "bit_rate": "262144",
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "width": 720,
                    "height": 1280,
                    "avg_frame_rate": "30000/1001",
                    "r_frame_rate": "30000/1001",
                }
            ],
        }

        def fake_run(cmd, **kwargs):
            return SimpleNamespace(returncode=0, stdout=json.dumps(sample), stderr="")

        monkeypatch.setattr("materials.normalizer.subprocess.run", fake_run)
        inp = tmp_path / "clip.mp4"
        inp.write_bytes(b"x")
        runner = FFmpegProcessRunner(ffmpeg_path=str(ffmpeg), ffprobe_path=str(ffprobe), timeout_seconds=5)
        meta = runner.probe(str(inp))

        assert meta["duration"] == 30.5
        assert meta["width"] == 720 and meta["height"] == 1280
        assert meta["resolution"] == "720x1280"
        assert meta["size"] == 1048576
        assert meta["bitrate"] == 262144
        assert meta["fps"] == pytest.approx(30000 / 1001)
        assert meta["format"] == "mp4"        # 扩展名口径
        assert meta["container"] == "mov"     # format_name 首段

    def test_transcode_command_locked_to_05_example(self, tmp_path, monkeypatch):
        ffmpeg, _ = self._fake_binaries(tmp_path)
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            Path(cmd[-1]).write_bytes(b"fake-out")  # 模拟 ffmpeg 产出输出文件
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("materials.normalizer.subprocess.run", fake_run)
        inp = tmp_path / "in.mp4"
        inp.write_bytes(b"x")
        out = tmp_path / "out.mp4"
        runner = FFmpegProcessRunner(ffmpeg_path=str(ffmpeg), timeout_seconds=5)
        res = runner.transcode(str(inp), str(out))

        assert res["success"] is True
        assert res["output_path"] == str(out)
        assert res["elapsed_seconds"] >= 0

        cmd = captured["cmd"]
        assert cmd[0] == str(ffmpeg)
        assert "-y" in cmd
        assert cmd[cmd.index("-i") + 1] == str(inp)
        assert cmd[cmd.index("-vf") + 1] == (
            "scale=720:1280:force_original_aspect_ratio=decrease,"
            "pad=720:1280:(ow-iw)/2:(oh-ih)/2"
        )
        assert cmd[cmd.index("-t") + 1] == "300"
        assert cmd[cmd.index("-c:v") + 1] == "libx264"
        assert cmd[cmd.index("-crf") + 1] == "23"
        assert cmd[cmd.index("-c:a") + 1] == "aac"
        assert cmd[-1] == str(out)

    def test_transcode_timeout_raises(self, tmp_path, monkeypatch):
        ffmpeg, _ = self._fake_binaries(tmp_path)

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

        monkeypatch.setattr("materials.normalizer.subprocess.run", fake_run)
        inp = tmp_path / "in.mp4"
        inp.write_bytes(b"x")
        runner = FFmpegProcessRunner(ffmpeg_path=str(ffmpeg), timeout_seconds=5)
        with pytest.raises(NormalizerError) as ei:
            runner.transcode(str(inp), str(tmp_path / "out.mp4"))
        assert "超时" in str(ei.value)  # R-M2-16 资源占用保护

    def test_transcode_failure_exit_code_raises(self, tmp_path, monkeypatch):
        ffmpeg, _ = self._fake_binaries(tmp_path)

        def fake_run(cmd, **kwargs):
            return SimpleNamespace(returncode=1, stdout="", stderr="Invalid data found")

        monkeypatch.setattr("materials.normalizer.subprocess.run", fake_run)
        inp = tmp_path / "in.mp4"
        inp.write_bytes(b"x")
        runner = FFmpegProcessRunner(ffmpeg_path=str(ffmpeg), timeout_seconds=5)
        with pytest.raises(NormalizerError) as ei:
            runner.transcode(str(inp), str(tmp_path / "out.mp4"))
        assert "转码失败" in str(ei.value)


# ===========================================================================
# config.normalize：环境变量映射（MATERIALS_FFMPEG_PATH → normalize.ffmpeg_path）
# ===========================================================================
def test_config_normalize_env_mapping(monkeypatch):
    monkeypatch.setenv("MATERIALS_FFMPEG_PATH", "C:/tools/ffmpeg.exe")
    monkeypatch.setenv("MATERIALS_FFPROBE_PATH", "C:/tools/ffprobe.exe")
    cfg = load_config()
    assert cfg.normalize.ffmpeg_path == "C:/tools/ffmpeg.exe"
    assert cfg.normalize.ffprobe_path == "C:/tools/ffprobe.exe"


def test_config_normalize_defaults_and_override():
    cfg = load_config(normalize={"crf": 28, "output_format": "mov"})
    assert cfg.normalize.crf == 28
    assert cfg.normalize.output_format == "mov"
    assert cfg.normalize.transcode_timeout_seconds == 300
    assert cfg.normalize.ratio_tolerance == pytest.approx(RATIO_TOLERANCE)


# ===========================================================================
# ⑥ 真实转码：skipif 保护（本机自动跳过；环境就绪后无需改代码即启用）
# ===========================================================================
@pytest.mark.skipif(
    not detect_ffmpeg(),
    reason="本机未安装 ffmpeg/ffprobe（环境就绪后本用例自动启用）",
)
def test_real_transcode_normalize(tmp_path):
    """真实 ffmpeg 全链路冒烟：testsrc 造源 → 标准化 → 复检通过。"""
    import shutil

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg and ffprobe

    # 造一个 6 秒 480x640 的源（非 9:16、分辨率不足 → 标准化应修成 720x1280）
    src = tmp_path / "src.mp4"
    proc = subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=480x640:rate=10",
         "-pix_fmt", "yuv420p", str(src)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr

    cfg = load_config(normalize={"ffmpeg_path": ffmpeg, "ffprobe_path": ffprobe})
    runner = FFmpegProcessRunner(ffmpeg_path=ffmpeg, ffprobe_path=ffprobe, timeout_seconds=60)
    out = tmp_path / "out.mp4"
    result = Normalizer(runner, config=cfg).normalize(str(src), str(out))

    assert result["passed"] is True, result["failures"]
    assert result["failures"] == []
    assert Path(result["output_path"]).is_file()
    assert result["meta_after"]["resolution"] == "720x1280"
    assert result["meta_after"]["width"] == 720 and result["meta_after"]["height"] == 1280
    assert 5 <= result["meta_after"]["duration"] <= 300
