"""M3 视频二创流水线 · ffmpeg 层（子代理-C1 · v0.3）测试。

覆盖（Mock 优先，本机 ffmpeg/ffprobe 未安装已探测确认）：
1. detect_ffmpeg：无 ffmpeg 环境返回 None（本机即验证，绝不抛异常）；env 优先 / 缺 ffprobe 也 None；
2. VideoToolError：error_code 限定 WorkflowJob 码表 TIMEOUT/UNEXPECTED/NO_MATCH，非法码归一 UNEXPECTED；
3. FFmpegProcessRunner：二进制缺失路径 → VideoToolError（含安装指引关键词
   winget/ffmpeg.org 官网/brew/apt/M3_FFMPEG_PATH）；probe（成功解析/超时 TIMEOUT/
   无视频流 NO_MATCH/非零退出/坏 JSON → UNEXPECTED）；transcode（绑定二进制/超时/非零退出/前置补齐）；
4. MockFFmpegRunner：probe 返回注入元数据；transcode 记录 (cmd, timeout) 供断言；
5. validate_specs：五维边界（分辨率不足/横屏/超大小/超时长/短时长/格式不支持各拒绝且
   failures 可解释；合规通过/边界值通过/缺字段逐项报）；
6. build_transcode_cmd：命令锁定（scale/pad/-t 300/libx264 -crf 23/aac/extra_filters 拼接/
   自定义 spec 覆盖/dict spec）；
7. 真实转码 smoke：skipif(not detect_ffmpeg()) 保护 —— 环境就绪后自动启用（先实现+Mock 模式）。

运行：python -m pytest tests/test_optimization_video_ffmpeg.py -q --basetemp=".pytest-tmp-m3"
（P-011：独立 basetemp，禁止共用 .pytest-tmp）
"""

from __future__ import annotations

import json
import subprocess

import pytest

from optimization.config import VideoSpec
from optimization.video import (
    FFmpegProcessRunner,
    FFmpegRunner,
    MockFFmpegRunner,
    VideoToolError,
    build_transcode_cmd,
    detect_ffmpeg,
    validate_specs,
)
from optimization.video import ffmpeg as ffmod

BASE_FILTER = (
    "scale=720:1280:force_original_aspect_ratio=decrease,"
    "pad=720:1280:(ow-iw)/2:(oh-ih)/2"
)


def _probe(**overrides) -> dict:
    """合规基线元数据（720x1280 / 9:16 / mp4 / 100MB / 30s），可按维度覆盖。"""
    base = {
        "width": 720,
        "height": 1280,
        "duration": 30.0,
        "size_bytes": 100 * 1024 * 1024,
        "format": "mp4",
    }
    base.update(overrides)
    return base


def _fake_binary(tmp_path, name="fake-ffmpeg.exe") -> str:
    """构造一个真实存在的假二进制文件（绕过构造器 isfile 校验；subprocess 已打桩）。"""
    p = tmp_path / name
    p.write_text("", encoding="utf-8")
    return str(p)


@pytest.fixture
def spec() -> VideoSpec:
    return VideoSpec()


# ---------------------------------------------------------------- detect_ffmpeg


def test_detect_ffmpeg_no_env_returns_none(monkeypatch):
    """本机即验证：无 ffmpeg/ffprobe 环境 → None（绝不抛异常）。"""
    for key in ("M3_FFMPEG_PATH", "M3_FFPROBE_PATH", "FFMPEG_PATH", "FFPROBE_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(ffmod.shutil, "which", lambda name: None)
    assert detect_ffmpeg() is None


def test_detect_ffmpeg_env_priority(monkeypatch):
    """env M3_FFMPEG_PATH/M3_FFPROBE_PATH 优先于 PATH，返回版本字符串。"""
    monkeypatch.setenv("M3_FFMPEG_PATH", "C:/tools/ffmpeg.exe")
    monkeypatch.setenv("M3_FFPROBE_PATH", "C:/tools/ffprobe.exe")
    monkeypatch.setattr(
        ffmod, "_query_version",
        lambda binary, args=None: "ffmpeg version 6.1.1-full_build",
    )

    def boom(name):
        raise AssertionError("M3_* 已命中，不应查询 PATH")

    monkeypatch.setattr(ffmod.shutil, "which", boom)
    assert detect_ffmpeg() == "ffmpeg version 6.1.1-full_build"


def test_detect_ffmpeg_missing_ffprobe_returns_none(monkeypatch):
    """有 ffmpeg 无 ffprobe → None。"""
    monkeypatch.setenv("M3_FFMPEG_PATH", "C:/tools/ffmpeg.exe")
    monkeypatch.delenv("M3_FFPROBE_PATH", raising=False)
    monkeypatch.setattr(ffmod, "_query_version", lambda binary, args=None: "ffmpeg version 7.0")
    monkeypatch.setattr(ffmod.shutil, "which", lambda name: None)
    assert detect_ffmpeg() is None


def test_detect_ffmpeg_path_fallback(monkeypatch):
    """env 缺省时走 PATH（shutil.which）。"""
    for key in ("M3_FFMPEG_PATH", "M3_FFPROBE_PATH", "FFMPEG_PATH", "FFPROBE_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        ffmod.shutil, "which",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(ffmod, "_query_version", lambda binary, args=None: "ffmpeg version 6.1")
    assert detect_ffmpeg() == "ffmpeg version 6.1"


def test_detect_ffmpeg_version_failure_returns_none(monkeypatch):
    """二进制存在但版本查询异常 → None，绝不抛异常。"""
    monkeypatch.setenv("M3_FFMPEG_PATH", "C:/tools/ffmpeg.exe")
    monkeypatch.setenv("M3_FFPROBE_PATH", "C:/tools/ffprobe.exe")

    def boom(binary, args=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(ffmod, "_query_version", boom)
    assert detect_ffmpeg() is None


def test_detect_ffmpeg_plain_call_never_raises():
    """直接调用：返回 None 或非空版本串，绝不抛异常（本机即 None）。"""
    result = detect_ffmpeg()
    assert result is None or (isinstance(result, str) and result)


# ---------------------------------------------------------------- VideoToolError


def test_video_tool_error_codes():
    for code in ("TIMEOUT", "UNEXPECTED", "NO_MATCH"):
        err = VideoToolError(code, "msg", {"k": 1})
        assert err.error_code == code
        assert err.message == "msg"
        assert err.evidence == {"k": 1}
    err_bad = VideoToolError("BOGUS", "x")
    assert err_bad.error_code == "UNEXPECTED"  # 非法码归一 UNEXPECTED


# ---------------------------------------------------------------- FFmpegProcessRunner


def test_process_runner_missing_binary_raises_with_guidance(tmp_path):
    """缺失二进制路径 → VideoToolError 含安装指引关键词。"""
    with pytest.raises(VideoToolError) as ei:
        FFmpegProcessRunner(
            ffmpeg_path=str(tmp_path / "no-ffmpeg.exe"),
            ffprobe_path=str(tmp_path / "no-ffprobe.exe"),
        )
    assert ei.value.error_code == "UNEXPECTED"
    msg = str(ei.value)
    for kw in ("winget", "ffmpeg.org", "brew", "apt", "M3_FFMPEG_PATH"):
        assert kw in msg, f"安装指引缺少关键词: {kw}"


def test_process_runner_env_missing_raises(monkeypatch):
    """env 与 PATH 均无 → 构造即 raise（不静默）。"""
    for key in ("M3_FFMPEG_PATH", "M3_FFPROBE_PATH", "FFMPEG_PATH", "FFPROBE_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(ffmod.shutil, "which", lambda name: None)
    with pytest.raises(VideoToolError) as ei:
        FFmpegProcessRunner()
    assert ei.value.error_code == "UNEXPECTED"


def test_probe_parses_ffprobe_json(tmp_path, monkeypatch):
    fake = _fake_binary(tmp_path)
    runner = FFmpegProcessRunner(ffmpeg_path=fake, ffprobe_path=fake, timeout=30.0)
    payload = {
        "streams": [
            {"codec_type": "audio", "codec_name": "aac"},
            {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
        ],
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "12.5",
            "size": "123456",
        },
    }
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(payload).encode("utf-8"), stderr=b""
        )

    monkeypatch.setattr(ffmod.subprocess, "run", fake_run)
    info = runner.probe("in.mp4")
    assert info == {
        "width": 1080,
        "height": 1920,
        "duration": 12.5,
        "size_bytes": 123456,
        "format": "mov,mp4,m4a,3gp,3g2,mj2",
    }
    assert captured["cmd"][0] == fake  # 绑定真实 ffprobe 路径
    assert "-print_format" in captured["cmd"] and "json" in captured["cmd"]


def test_probe_timeout(tmp_path, monkeypatch):
    fake = _fake_binary(tmp_path)
    runner = FFmpegProcessRunner(ffmpeg_path=fake, ffprobe_path=fake, timeout=5.0)

    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout", 5.0))

    monkeypatch.setattr(ffmod.subprocess, "run", fake_run)
    with pytest.raises(VideoToolError) as ei:
        runner.probe("in.mp4")
    assert ei.value.error_code == "TIMEOUT"


def test_probe_no_video_stream_no_match(tmp_path, monkeypatch):
    fake = _fake_binary(tmp_path)
    runner = FFmpegProcessRunner(ffmpeg_path=fake, ffprobe_path=fake)

    def fake_run(cmd, **kw):
        payload = {"streams": [{"codec_type": "audio"}], "format": {"format_name": "mp4"}}
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(payload).encode("utf-8"), stderr=b""
        )

    monkeypatch.setattr(ffmod.subprocess, "run", fake_run)
    with pytest.raises(VideoToolError) as ei:
        runner.probe("in.mp4")
    assert ei.value.error_code == "NO_MATCH"


def test_probe_nonzero_exit_unexpected(tmp_path, monkeypatch):
    fake = _fake_binary(tmp_path)
    runner = FFmpegProcessRunner(ffmpeg_path=fake, ffprobe_path=fake)

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"file not found")

    monkeypatch.setattr(ffmod.subprocess, "run", fake_run)
    with pytest.raises(VideoToolError) as ei:
        runner.probe("missing.mp4")
    assert ei.value.error_code == "UNEXPECTED"
    assert "file not found" in str(ei.value)


def test_probe_bad_json_unexpected(tmp_path, monkeypatch):
    fake = _fake_binary(tmp_path)
    runner = FFmpegProcessRunner(ffmpeg_path=fake, ffprobe_path=fake)

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=b"not-json", stderr=b"")

    monkeypatch.setattr(ffmod.subprocess, "run", fake_run)
    with pytest.raises(VideoToolError) as ei:
        runner.probe("in.mp4")
    assert ei.value.error_code == "UNEXPECTED"


def test_transcode_success_binds_binary(tmp_path, monkeypatch, spec):
    fake = _fake_binary(tmp_path)
    runner = FFmpegProcessRunner(ffmpeg_path=fake, ffprobe_path=fake, timeout=30.0)
    cmd = build_transcode_cmd("in.mp4", "out.mp4", spec)
    assert cmd[0] == "ffmpeg"
    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        captured["timeout"] = kw.get("timeout")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(ffmod.subprocess, "run", fake_run)
    assert runner.transcode(cmd, timeout=60.0) is None
    assert captured["argv"][0] == fake            # "ffmpeg" 占位绑定真实二进制
    assert captured["argv"] == [fake] + cmd[1:]   # 其余参数原样透传
    assert captured["timeout"] == 60.0


def test_transcode_timeout(tmp_path, monkeypatch, spec):
    fake = _fake_binary(tmp_path)
    runner = FFmpegProcessRunner(ffmpeg_path=fake, ffprobe_path=fake, timeout=30.0)

    def fake_run(argv, **kw):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kw.get("timeout", 30.0))

    monkeypatch.setattr(ffmod.subprocess, "run", fake_run)
    with pytest.raises(VideoToolError) as ei:
        runner.transcode(build_transcode_cmd("in.mp4", "out.mp4", spec), timeout=10.0)
    assert ei.value.error_code == "TIMEOUT"


def test_transcode_nonzero_exit(tmp_path, monkeypatch, spec):
    fake = _fake_binary(tmp_path)
    runner = FFmpegProcessRunner(ffmpeg_path=fake, ffprobe_path=fake)

    def fake_run(argv, **kw):
        return subprocess.CompletedProcess(argv, 2, stdout=b"", stderr=b"Invalid argument")

    monkeypatch.setattr(ffmod.subprocess, "run", fake_run)
    with pytest.raises(VideoToolError) as ei:
        runner.transcode(build_transcode_cmd("in.mp4", "out.mp4", spec), timeout=30.0)
    assert ei.value.error_code == "UNEXPECTED"
    assert "Invalid argument" in str(ei.value)


def test_transcode_prepends_binary_when_not_placeholder(tmp_path, monkeypatch):
    fake = _fake_binary(tmp_path)
    runner = FFmpegProcessRunner(ffmpeg_path=fake, ffprobe_path=fake)
    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(ffmod.subprocess, "run", fake_run)
    runner.transcode(["-i", "in.mp4", "out.mp4"], timeout=30.0)
    assert captured["argv"] == [fake, "-i", "in.mp4", "out.mp4"]


# ---------------------------------------------------------------- MockFFmpegRunner


def test_mock_probe_returns_injected():
    meta = _probe(width=1080, height=1920, duration=15.5, size_bytes=999, format="mov")
    runner = MockFFmpegRunner(meta)
    assert runner.probe("whatever.mp4") == meta
    assert runner.probe("other.mp4") == meta          # 幂等
    assert MockFFmpegRunner().probe("x.mp4") == {}    # 无注入 → 空 dict
    assert isinstance(runner, FFmpegRunner)           # 满足抽象基类


def test_mock_transcode_records_calls():
    runner = MockFFmpegRunner()
    cmd = ["ffmpeg", "-y", "-i", "in.mp4", "out.mp4"]
    runner.transcode(cmd, timeout=30.0)
    runner.transcode(["-t", "10", "x.mp4"], timeout=5.0)
    assert runner.transcode_calls == [(cmd, 30.0), (["-t", "10", "x.mp4"], 5.0)]


# ---------------------------------------------------------------- validate_specs


def test_validate_ok(spec):
    result = validate_specs(_probe(), spec)
    assert result["passed"] is True
    assert result["failures"] == []


def test_validate_mov_format_ok(spec):
    """ffprobe format_name 多容器名按 token 命中 mov/mp4。"""
    result = validate_specs(_probe(format="mov,mp4,m4a,3gp,3g2,mj2"), spec)
    assert result["passed"] is True


def test_validate_resolution_insufficient(spec):
    result = validate_specs(_probe(width=640, height=1280), spec)
    assert result["passed"] is False
    f = result["failures"][0]
    assert f["field"] == "resolution"
    assert "720" in f["reason"] and "1280" in f["reason"]
    assert f["value"] == "640x1280"


def test_validate_landscape_rejected(spec):
    """方形/横屏画面：分辨率达标但比例非 9:16 → aspect 拒绝。"""
    result = validate_specs(_probe(width=1280, height=1280), spec)
    assert result["passed"] is False
    f = next(f for f in result["failures"] if f["field"] == "aspect")
    assert "9:16" in f["reason"]
    assert f["value"] == pytest.approx(1.0)


def test_validate_oversize_rejected(spec):
    result = validate_specs(_probe(size_bytes=600 * 1024 * 1024), spec)
    f = next(f for f in result["failures"] if f["field"] == "size")
    assert "500" in f["reason"]
    assert f["value"] == 600 * 1024 * 1024


def test_validate_over_duration_rejected(spec):
    result = validate_specs(_probe(duration=301.0), spec)
    f = next(f for f in result["failures"] if f["field"] == "duration")
    assert "300" in f["reason"]
    assert f["value"] == pytest.approx(301.0)


def test_validate_short_duration_rejected(spec):
    result = validate_specs(_probe(duration=4.0), spec)
    f = next(f for f in result["failures"] if f["field"] == "duration")
    assert "5" in f["reason"]
    assert f["value"] == pytest.approx(4.0)


def test_validate_duration_boundaries_pass(spec):
    assert validate_specs(_probe(duration=5.0), spec)["passed"] is True
    assert validate_specs(_probe(duration=300.0), spec)["passed"] is True


def test_validate_size_boundary_pass(spec):
    assert validate_specs(_probe(size_bytes=500 * 1024 * 1024), spec)["passed"] is True


def test_validate_aspect_tolerance(spec):
    """9:16 容差 ±0.01：720x1288（ratio≈0.559，且分辨率达标）通过，720x1320（ratio≈0.545）拒绝。"""
    assert validate_specs(_probe(width=720, height=1288), spec)["passed"] is True
    result = validate_specs(_probe(width=720, height=1320), spec)
    assert result["passed"] is False
    f = next(f for f in result["failures"] if f["field"] == "aspect")
    assert f["value"] == pytest.approx(720 / 1320, abs=1e-4)  # value 为 round(ratio, 4)


def test_validate_format_unsupported(spec):
    result = validate_specs(_probe(format="webm"), spec)
    f = next(f for f in result["failures"] if f["field"] == "format")
    assert "mov" in f["reason"] and "mp4" in f["reason"]
    assert f["value"] == "webm"


def test_validate_missing_fields(spec):
    result = validate_specs({}, spec)
    assert result["passed"] is False
    fields = {f["field"] for f in result["failures"]}
    assert fields == {"resolution", "aspect", "format", "size", "duration"}
    for f in result["failures"]:
        assert f["reason"]  # 逐项可解释


def test_validate_all_failures_reported(spec):
    result = validate_specs(
        _probe(width=480, height=640, duration=400.0, size_bytes=700 * 1024 * 1024, format="avi"),
        spec,
    )
    assert result["passed"] is False
    fields = {f["field"] for f in result["failures"]}
    assert fields == {"resolution", "aspect", "format", "size", "duration"}
    assert len(result["failures"]) == 5


# ---------------------------------------------------------------- build_transcode_cmd


def test_build_cmd_default(spec):
    cmd = build_transcode_cmd("in.mp4", "out.mp4", spec)
    assert cmd == [
        "ffmpeg", "-y",
        "-i", "in.mp4",
        "-vf", BASE_FILTER,
        "-t", "300",
        "-c:v", "libx264",
        "-crf", "23",
        "-c:a", "aac",
        "out.mp4",
    ]


def test_build_cmd_extra_filters(spec):
    cmd = build_transcode_cmd(
        "in.mp4", "out.mp4", spec,
        extra_filters=["drawtext=text='促销'", "subtitles=sub.srt"],
    )
    assert cmd[5] == BASE_FILTER + ",drawtext=text='促销',subtitles=sub.srt"


def test_build_cmd_spec_values():
    """参数全部取 config.video（spec 覆盖生效），禁止硬编码。"""
    s = VideoSpec(crf=28, audio_codec="mp3", max_duration=120, min_width=1080, min_height=1920)
    cmd = build_transcode_cmd("in.mp4", "out.mov", s)
    assert cmd[5] == (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    )
    assert cmd[7] == "120"
    assert cmd[11] == "28"
    assert cmd[13] == "mp3"


def test_build_cmd_dict_spec():
    cmd = build_transcode_cmd("in.mp4", "out.mp4", {"crf": 26, "audio_codec": "mp3"})
    assert cmd[11] == "26"
    assert cmd[13] == "mp3"
    assert cmd[7] == "300"  # 缺省回退 config.video 默认


def test_build_cmd_extra_filters_none_is_default(spec):
    assert build_transcode_cmd("a.mp4", "b.mp4", spec, extra_filters=None)[5] == BASE_FILTER
    assert build_transcode_cmd("a.mp4", "b.mp4", spec, extra_filters=[])[5] == BASE_FILTER


# ---------------------------------------------------------------- 包级重导出


def test_package_reexports():
    import optimization.video as video_pkg

    for name in (
        "detect_ffmpeg",
        "VideoToolError",
        "FFmpegRunner",
        "FFmpegProcessRunner",
        "MockFFmpegRunner",
        "validate_specs",
        "build_transcode_cmd",
    ):
        assert hasattr(video_pkg, name), f"包级缺少重导出: {name}"
    assert video_pkg.detect_ffmpeg is detect_ffmpeg


# ---------------------------------------------------------------- 真实转码（环境就绪后自动启用）


@pytest.mark.skipif(
    not detect_ffmpeg(),
    reason="本机未安装 ffmpeg/ffprobe：环境就绪后自动启用（先实现+Mock 模式）",
)
def test_real_transcode_and_probe(tmp_path):
    """真实出片冒烟：lavfi 生成 720x1280 6s 源 → build_transcode_cmd 转码 → ffprobe 五维校验全过。"""
    spec = VideoSpec()
    runner = FFmpegProcessRunner()
    src = tmp_path / "src.mp4"
    gen = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc2=duration=6:size=720x1280:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(src),
    ]
    runner.transcode(gen, timeout=120.0)
    out = tmp_path / "out.mp4"
    runner.transcode(build_transcode_cmd(src, out, spec), timeout=120.0)
    info = runner.probe(out)
    assert info["width"] == 720 and info["height"] == 1280
    assert info["duration"] >= 5.0
    result = validate_specs(info, spec)
    assert result["passed"] is True, result["failures"]
