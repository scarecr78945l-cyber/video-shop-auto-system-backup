"""pytest 插件：展开命令行中的 glob 路径参数（仅当参数含 `*?[` 通配符时生效）。

背景：Windows PowerShell/cmd 不展开 shell glob，pytest 也不自行展开位置参数，
导致任务书验收命令 `python -X utf8 -m pytest tests/test_api_*.py ...` 在
Windows 下报 "file or directory not found"。本插件在 `pytest_cmdline_main`
钩子中把含通配符且可匹配的参数展开为具体文件列表；不含通配符的参数原样透传
（对其它模块的既有测试命令零影响）。

注册：backend/pytest.ini `addopts = -p api._pytest_glob`（本文件属于 M6 API 层
交付物，非模块源码；仅作用于 pytest 命令行参数展开）。
"""

from __future__ import annotations

import glob


def _expand_args(args: list[str]) -> list[str]:
    out: list[str] = []
    for arg in args:
        if any(ch in arg for ch in "*?["):
            matches = sorted(glob.glob(arg))
            if matches:
                out.extend(matches)
                continue
        out.append(arg)
    return out


def pytest_cmdline_main(config):
    """展开 glob 参数（在收集发生前修改 config.args）。"""
    expanded = _expand_args(list(config.args))
    if expanded != list(config.args):
        config.args[:] = expanded
