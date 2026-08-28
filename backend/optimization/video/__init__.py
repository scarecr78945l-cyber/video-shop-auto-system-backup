"""M3 视频二创流水线 · ffmpeg 层（子代理-C1 · v0.3）。

视频二创出片/校验公共接口（编排层 C2 按此调用，接口签名严格一致）：

- ``detect_ffmpeg()``：ffmpeg/ffprobe 探测（env M3_FFMPEG_PATH/M3_FFPROBE_PATH 优先 → PATH）；
  两者齐备返回版本字符串，否则 None（绝不抛异常）。
- ``VideoToolError``：视频工具异常，error_code 限定 WorkflowJob 码表 TIMEOUT/UNEXPECTED/NO_MATCH。
- ``FFmpegRunner``（抽象基类）：probe(path) -> {width,height,duration,size_bytes,format}；
  transcode(cmd, timeout)。
- ``FFmpegProcessRunner``：subprocess 实现；二进制缺失 raise VideoToolError（含安装指引，不静默）。
- ``MockFFmpegRunner``：测试注入（probe 返回预设元数据，transcode 记录命令供断言）。
- ``validate_specs(probe, spec)``：五维硬规格校验（分辨率/比例/格式/大小/时长），
  返回 {'passed','failures'} 逐项可解释（对齐 05/06 硬规格与 P-007）。
- ``build_transcode_cmd(input, output, spec, extra_filters=None)``：出片命令构造
  （scale/pad + -t 时长上限 + libx264 -crf + aac，参数全取 config.video）。

本机 ffmpeg/ffprobe 未安装：先实现 + Mock 测试；环境就绪（detect_ffmpeg() 返回版本）后
自动切换 FFmpegProcessRunner（真实转码用例 skipif 保护）。
"""

from __future__ import annotations

from .ffmpeg import (
    FFmpegProcessRunner,
    FFmpegRunner,
    MockFFmpegRunner,
    VideoToolError,
    build_transcode_cmd,
    detect_ffmpeg,
    validate_specs,
)

__all__ = [
    "detect_ffmpeg",
    "VideoToolError",
    "FFmpegRunner",
    "FFmpegProcessRunner",
    "MockFFmpegRunner",
    "validate_specs",
    "build_transcode_cmd",
]
