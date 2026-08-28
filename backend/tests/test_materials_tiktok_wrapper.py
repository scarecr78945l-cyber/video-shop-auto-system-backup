"""materials.collectors.tiktok_wrapper 单元测试：fake TikTokDownloader CLI fixtures 全场景。

场景（任务书验收 ①~⑤）：
  ① search_download 正常解析（fake 文本输出 N 条 + JSON 输出模式）
  ② author_download 参数构造正确（--mode author --target --count --output）
  ③ 错误分类映射各分支：TIMEOUT（sleep 脚本超时）/ NO_MATCH（空输出）/
     RATE_LIMIT（频控/风控/验证码）/ AUTH_REQUIRED（登录失效，P-002 不自动重试）/
     PLATFORM_REJECT（签名/参数错误）/ UNEXPECTED（非 0 退出且无已知特征）
  ④ binary 缺失：check_available 返回 available=False 且 search 抛清晰错误（含安装指引）
  ⑤ 输出脱敏：fake 输出含敏感参数值（sec_uid/a_bogus/token），断言返回结果与日志
     均不含明文（P-004）；redact_url/redact_text/redact_path 直接单测
  另：JSON 解析（data 包裹/单条目/非法 JSON）、去重、平台开关（R-M2-21）、
     config.tiktok 环境变量映射（MATERIALS_TIKTOK_BINARY 等）、CLI 子命令
     （binary 缺失非 0 退出 / 注入 fake binary 跑通解析）。

纪律：pytest 一律带 --basetemp=".pytest-tmp"（P-001）；临时文件只放 tmp_path；
全程零真实 TikTokDownloader 依赖、零外网（R-M2-17）；fake 输出中的假 Cookie/Token
同样视为敏感值，断言不得出现在返回与日志中（宪法第 5 节）。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from materials.config import load_config
from materials.downloader import (
    AUTH_REQUIRED,
    NO_MATCH,
    PLATFORM_REJECT,
    RATE_LIMIT,
    TIMEOUT,
    UNEXPECTED,
)
from materials.collectors.tiktok_wrapper import (
    TikTokDownloaderCLI,
    TikTokDownloaderError,
    infer_platform,
    redact_path,
    redact_text,
    redact_url,
)

BACKEND = Path(__file__).resolve().parents[1]

# ===========================================================================
# fake TikTokDownloader CLI 脚本（fixtures 模式，R-M2-17）
# 行为由环境变量控制：FAKE_TTD_MODE(text|json|files) / FAKE_TTD_TEXT /
# FAKE_TTD_JSON_PAYLOAD / FAKE_TTD_COUNT / FAKE_TTD_EXIT_CODE /
# FAKE_TTD_SLEEP_SECONDS / FAKE_TTD_VERSION
# ===========================================================================
FAKE_TTD_SCRIPT = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fake TikTokDownloader CLI（fixtures 模式）：按环境变量输出模拟输出/退出码/超时。"""
import json
import os
import sys
import time


def _text_lines():
    return os.environ.get("FAKE_TTD_TEXT", "").splitlines()


def main():
    argv = sys.argv[1:]
    if "--version" in argv:
        print(os.environ.get("FAKE_TTD_VERSION", "TikTokDownloader 4.1.0 (fake)"))
        return 0
    mode = os.environ.get("FAKE_TTD_MODE", "text")
    exit_code = int(os.environ.get("FAKE_TTD_EXIT_CODE", "0") or "0")
    sleep_seconds = float(os.environ.get("FAKE_TTD_SLEEP_SECONDS", "0") or "0")
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    out_dir = None
    if "--output" in argv:
        idx = argv.index("--output")
        if idx + 1 < len(argv):
            out_dir = argv[idx + 1]
    if mode == "json":
        payload = os.environ.get("FAKE_TTD_JSON_PAYLOAD", "[]")
        print(json.dumps(json.loads(payload), ensure_ascii=False, indent=2))
    elif mode == "files":
        n = int(os.environ.get("FAKE_TTD_COUNT", "3"))
        for i in range(1, n + 1):
            fn = "douyin_%04d.mp4" % i
            if out_dir:
                with open(os.path.join(out_dir, fn), "wb") as fh:
                    fh.write(b"fake-video-" + str(i).encode())
            print("文件名: " + fn)
            print("作品标题: 测试作品%d" % i)
            print("作者: 达人%d" % i)
            print("作品链接: https://www.douyin.com/video/71%d?sec_uid=FAKESECRETUID%d&a_bogus=FAKESIGN%d&token=FAKETOKEN%d" % (i, i, i, i))
    else:
        for line in _text_lines():
            print(line)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
'''


def _write_fake(tmp_path: Path) -> Path:
    fake = tmp_path / "fake_ttd.py"
    fake.write_text(FAKE_TTD_SCRIPT, encoding="utf-8")
    return fake


def _cli(binary_path: Path, **kwargs) -> TikTokDownloaderCLI:
    return TikTokDownloaderCLI(binary_path=str(binary_path), config=load_config(), **kwargs)


def _decode_cli(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gbk", errors="replace")


def _run_cli(env_extra: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_extra}
    return subprocess.run(
        [sys.executable, "-m", "materials", "tiktok-download", *args],
        cwd=str(BACKEND), env=env, capture_output=True, timeout=60,
    )


# ===========================================================================
# ① search_download 正常解析（文本 files 模式 + JSON 模式）
# ===========================================================================
class TestSearchDownload:
    def test_normal_parse_text_mode(self, tmp_path, monkeypatch, caplog):
        fake = _write_fake(tmp_path)
        out = tmp_path / "out"
        monkeypatch.setenv("FAKE_TTD_MODE", "files")
        monkeypatch.setenv("FAKE_TTD_COUNT", "3")
        cli = _cli(fake, output_dir=str(out))
        with caplog.at_level(logging.INFO, logger="materials.collectors.tiktok"):
            results = cli.search_download("测试", count=3)

        assert len(results) == 3
        r0 = results[0]
        assert r0["file_path"] == str(out / "douyin_0001.mp4")
        assert Path(r0["file_path"]).is_file()
        assert r0["title"] == "测试作品1"
        assert r0["author"] == "达人1"
        assert r0["platform"] == "douyin"
        assert "***" in r0["source_url"]
        assert r0["source_url"].startswith("https://www.douyin.com/video/")

        # ⑤ 返回结果与日志均不含 fake 敏感参数明文（P-004）
        blob = json.dumps(results, ensure_ascii=False)
        for marker in ("FAKESECRETUID", "FAKESIGN", "FAKETOKEN"):
            assert marker not in blob
            assert marker not in caplog.text

    def test_json_mode(self, tmp_path, monkeypatch):
        fake = _write_fake(tmp_path)
        out = tmp_path / "out"
        payload = [
            {
                "file_path": str(out / "j1.mp4"), "title": "JSON一", "author": "甲",
                "source_url": "https://www.douyin.com/video/1?token=JTOK1", "platform": "douyin",
            },
            {
                "file_path": str(out / "j2.mp4"), "title": "JSON二", "author": "乙",
                "source_url": "https://www.kuaishou.com/video/2", "platform": "kuaishou",
            },
        ]
        monkeypatch.setenv("FAKE_TTD_MODE", "json")
        monkeypatch.setenv("FAKE_TTD_JSON_PAYLOAD", json.dumps(payload, ensure_ascii=False))
        cli = _cli(fake, output_dir=str(out))
        results = cli.search_download("测试", count=2)

        assert len(results) == 2
        assert results[0]["platform"] == "douyin"
        assert results[1]["platform"] == "kuaishou"
        assert "JTOK1" not in results[0]["source_url"]
        assert "***" in results[0]["source_url"]


# ===========================================================================
# ② author_download 参数构造正确
# ===========================================================================
class TestAuthorDownload:
    def test_constructs_correct_args(self, tmp_path, monkeypatch):
        fake = _write_fake(tmp_path)
        out = tmp_path / "out"
        cli = _cli(fake, output_dir=str(out))
        captured: dict[str, list[str]] = {}

        def fake_run(cmd):
            captured["cmd"] = list(cmd)
            return (
                "文件名: a.mp4\n作品标题: 标题A\n作者: 达人A\n"
                "作品链接: https://www.kuaishou.com/video/1\n",
                "", 0,
            )

        monkeypatch.setattr(cli, "_run", fake_run)
        results = cli.author_download("https://www.kuaishou.com/profile/123", count=5)

        cmd = captured["cmd"]
        assert cmd[0] == str(fake)
        assert cmd[cmd.index("--mode") + 1] == "author"
        assert cmd[cmd.index("--target") + 1] == "https://www.kuaishou.com/profile/123"
        assert cmd[cmd.index("--count") + 1] == "5"
        assert cmd[cmd.index("--output") + 1] == str(out)
        assert results[0]["platform"] == "kuaishou"
        assert results[0]["file_path"].endswith("a.mp4")

    def test_build_command_contract(self, tmp_path):
        fake = _write_fake(tmp_path)
        cli = _cli(fake)
        out = tmp_path / "d"
        search = cli.build_command("search", "美妆", 10, out)
        assert search == [str(fake), "--mode", "search", "--target", "美妆", "--count", "10", "--output", str(out)]
        author = cli.build_command("author", "https://www.kuaishou.com/u/1", 3, out)
        assert author[author.index("--mode") + 1] == "author"
        assert author[author.index("--target") + 1] == "https://www.kuaishou.com/u/1"
        assert author[-2:] == ["--output", str(out)]

    def test_disabled_platform_guard(self, tmp_path):
        fake = _write_fake(tmp_path)
        cfg = load_config(tiktok={"enabled": {"douyin": True, "kuaishou": False, "xiaohongshu": True}})
        cli = TikTokDownloaderCLI(binary_path=str(fake), config=cfg, output_dir=str(tmp_path / "out"))
        with pytest.raises(TikTokDownloaderError) as ei:
            cli.author_download("https://www.kuaishou.com/profile/123", count=3)
        assert ei.value.error_code == UNEXPECTED
        assert "kuaishou" in ei.value.message
        assert "禁用" in ei.value.message

    def test_count_must_be_positive(self, tmp_path):
        fake = _write_fake(tmp_path)
        cli = _cli(fake)
        with pytest.raises(ValueError):
            cli.search_download("测试", count=0)


# ===========================================================================
# ③ 错误分类映射各分支
# ===========================================================================
class TestErrorClassification:
    @pytest.mark.parametrize(
        "hint_text,expected",
        [
            ("请求过于频繁，触发频控，请稍后再试", RATE_LIMIT),
            ("风控校验未通过，需要验证码", RATE_LIMIT),
            ("登录已失效，请重新登录", AUTH_REQUIRED),
            ("需要登录后使用", AUTH_REQUIRED),
            ("X-Bogus 签名校验失败", PLATFORM_REJECT),
            ("请求参数错误：msToken 无效", PLATFORM_REJECT),
        ],
    )
    def test_hint_classification(self, tmp_path, monkeypatch, hint_text, expected):
        fake = _write_fake(tmp_path)
        monkeypatch.setenv("FAKE_TTD_TEXT", hint_text)
        monkeypatch.setenv("FAKE_TTD_EXIT_CODE", "1")  # 即便非 0 退出，也按特征分类
        cli = _cli(fake, timeout_seconds=10)
        with pytest.raises(TikTokDownloaderError) as ei:
            cli.search_download("测试关键词", count=3)
        assert ei.value.error_code == expected

    def test_timeout(self, tmp_path, monkeypatch):
        fake = _write_fake(tmp_path)
        monkeypatch.setenv("FAKE_TTD_SLEEP_SECONDS", "30")
        cli = _cli(fake, timeout_seconds=1)
        with pytest.raises(TikTokDownloaderError) as ei:
            cli.search_download("测试", count=1)
        assert ei.value.error_code == TIMEOUT
        assert "超时" in ei.value.message
        assert ei.value.evidence["timeout_seconds"] == 1

    def test_no_match_empty_output(self, tmp_path, monkeypatch):
        fake = _write_fake(tmp_path)
        monkeypatch.setenv("FAKE_TTD_TEXT", "")
        monkeypatch.setenv("FAKE_TTD_EXIT_CODE", "0")
        cli = _cli(fake, timeout_seconds=10)
        with pytest.raises(TikTokDownloaderError) as ei:
            cli.search_download("不存在的关键词", count=5)
        assert ei.value.error_code == NO_MATCH

    def test_unexpected_nonzero_no_hints(self, tmp_path, monkeypatch):
        fake = _write_fake(tmp_path)
        monkeypatch.setenv("FAKE_TTD_TEXT", "无法识别的输出内容")
        monkeypatch.setenv("FAKE_TTD_EXIT_CODE", "3")
        cli = _cli(fake, timeout_seconds=10)
        with pytest.raises(TikTokDownloaderError) as ei:
            cli.search_download("测试", count=1)
        assert ei.value.error_code == UNEXPECTED

    def test_error_evidence_redacted(self, tmp_path, monkeypatch):
        fake = _write_fake(tmp_path)
        monkeypatch.setenv("FAKE_TTD_TEXT", "请求过于频繁 https://v.douyin.com/abc/?token=SECRETTOK123")
        monkeypatch.setenv("FAKE_TTD_EXIT_CODE", "1")
        cli = _cli(fake, timeout_seconds=10)
        with pytest.raises(TikTokDownloaderError) as ei:
            cli.search_download("测试", count=1)
        assert ei.value.error_code == RATE_LIMIT
        blob = json.dumps(ei.value.evidence, ensure_ascii=False)
        assert "SECRETTOK123" not in blob
        assert "***" in blob


# ===========================================================================
# ④ binary 缺失：check_available 不抛异常 + search 抛清晰错误
# ===========================================================================
class TestBinaryMissing:
    def test_check_available_false(self, tmp_path):
        cli = TikTokDownloaderCLI(binary_path=str(tmp_path / "no-ttd.exe"), timeout_seconds=5)
        info = cli.check_available()
        assert info["available"] is False
        assert info["version"] is None
        assert "未找到" in info["error"]
        assert "README" in info["error"]
        assert "视频号不在范围" in info["error"]  # R-M2-05 声明

    def test_search_raises_clear_error(self, tmp_path):
        cli = TikTokDownloaderCLI(binary_path=str(tmp_path / "no-ttd.exe"), timeout_seconds=5)
        with pytest.raises(TikTokDownloaderError) as ei:
            cli.search_download("测试", count=1)
        assert ei.value.error_code == UNEXPECTED
        assert ("未安装" in ei.value.message) or ("未找到" in ei.value.message)
        assert "README" in ei.value.message

    def test_check_available_fake_binary(self, tmp_path):
        fake = _write_fake(tmp_path)
        info = _cli(fake).check_available()
        assert info["available"] is True
        assert "fake" in (info["version"] or "").lower()


# ===========================================================================
# ⑤ 脱敏直接单测（P-004）
# ===========================================================================
class TestRedaction:
    def test_redact_url_masks_sensitive_params(self):
        u = "https://www.douyin.com/video/1?sec_uid=SECRETUID&a_bogus=SIG&token=TOK&foo=ok"
        r = redact_url(u)
        for marker in ("SECRETUID", "SIG", "TOK"):
            assert marker not in r
        assert "foo=ok" in r
        assert "***" in r

    def test_redact_text_masks_secrets_and_truncates(self):
        t = "作者说 token=ABC123 这是秘密 https://v.douyin.com/x/?sec_uid=UID99 结尾" + "x" * 500
        r = redact_text(t)
        assert "ABC123" not in r
        assert "UID99" not in r
        assert "***" in r
        assert r.endswith("...")

    def test_redact_path_masks_at_account(self):
        r = redact_path("C:/data/@测试达人_标题.mp4")
        assert "@测试达人" not in r
        assert "@***" in r

    def test_infer_platform(self):
        assert infer_platform("https://v.douyin.com/x/") == "douyin"
        assert infer_platform("https://www.kuaishou.com/profile/1") == "kuaishou"
        assert infer_platform("https://www.xiaohongshu.com/explore/1") == "xiaohongshu"
        assert infer_platform("https://example.com/x") is None


# ===========================================================================
# 输出解析单测（文本顺序无关 / JSON data 包裹 / 去重 / 非法 JSON）
# ===========================================================================
class TestParseOutput:
    def test_text_order_independent(self, tmp_path):
        cli = TikTokDownloaderCLI(binary_path="unused", config=load_config())
        text = (
            "作品标题: 标题一\n作者: 作者一\n作品链接: https://v.douyin.com/ab/?sec_uid=SEC1\n"
            "文件名: C:/abs/douyin_1.mp4\n"
            "文件名: rel_douyin_2.mp4\n作品标题: 标题二\n"
        )
        items = cli.parse_output(text, output_dir=tmp_path)
        assert len(items) == 2
        assert items[0]["file_path"] == str(Path("C:/abs/douyin_1.mp4"))
        assert items[0]["title"] == "标题一"
        assert items[0]["author"] == "作者一"
        assert items[0]["platform"] == "douyin"
        assert "SEC1" not in items[0]["source_url"]
        assert items[1]["file_path"] == str(tmp_path / "rel_douyin_2.mp4")
        assert items[1]["title"] == "标题二"

    def test_json_dict_with_data_and_dedup(self, tmp_path):
        cli = TikTokDownloaderCLI(binary_path="unused", config=load_config())
        payload = json.dumps(
            {
                "data": [
                    {"file_path": str(tmp_path / "a.mp4"), "title": "t1", "author": "u1",
                     "source_url": "https://www.douyin.com/video/1?sec_uid=S1"},
                    {"file_path": str(tmp_path / "a.mp4"), "title": "t1-dup", "author": "u1",
                     "source_url": "https://www.douyin.com/video/1"},
                ]
            },
            ensure_ascii=False,
        )
        items = cli.parse_output(payload, output_dir=tmp_path)
        assert len(items) == 1  # 同文件去重，保留首个
        assert items[0]["title"] == "t1"
        assert "S1" not in items[0]["source_url"]

    def test_json_empty_list(self):
        cli = TikTokDownloaderCLI(binary_path="unused", config=load_config())
        assert cli.parse_output("[]") == []
        assert cli.parse_output("") == []

    def test_json_invalid_raises_unexpected(self):
        cli = TikTokDownloaderCLI(binary_path="unused", config=load_config())
        with pytest.raises(TikTokDownloaderError) as ei:
            cli.parse_output("{not json}")
        assert ei.value.error_code == UNEXPECTED


# ===========================================================================
# config.tiktok：环境变量映射 + 默认值/覆盖
# ===========================================================================
class TestConfigTiktok:
    def test_env_mapping(self, monkeypatch):
        monkeypatch.setenv("MATERIALS_TIKTOK_BINARY", "C:/tools/ttd.exe")
        monkeypatch.setenv("MATERIALS_TIKTOK_TIMEOUT_SECONDS", "123")
        monkeypatch.setenv("MATERIALS_TIKTOK_OUTPUT_DIR", "C:/out/ttd")
        cfg = load_config()
        assert cfg.tiktok.binary_path == "C:/tools/ttd.exe"
        assert cfg.tiktok.timeout_seconds == 123
        assert cfg.tiktok.default_output_dir == "C:/out/ttd"
        assert cfg.tiktok.enabled == {"douyin": True, "kuaishou": True, "xiaohongshu": True}
        assert cfg.tiktok.version_pin  # 非空（推荐锁定版本线）

    def test_defaults_and_override(self):
        cfg = load_config(tiktok={"timeout_seconds": 99, "enabled": {"douyin": False}})
        assert cfg.tiktok.binary_path is None
        assert cfg.tiktok.timeout_seconds == 99
        assert cfg.tiktok.default_output_dir == "data/tiktok_downloads"
        assert cfg.tiktok.enabled == {"douyin": False}

    def test_cli_reads_config_defaults(self, tmp_path):
        fake = _write_fake(tmp_path)
        cli = TikTokDownloaderCLI(binary_path=str(fake), config=load_config())
        assert cli.timeout_seconds == 300
        assert cli.binary_path == str(fake)


# ===========================================================================
# CLI 子命令（python -m materials tiktok-download ...）
# ===========================================================================
class TestCliTiktokDownload:
    def test_missing_binary_exits_nonzero(self, tmp_path):
        r = _run_cli(
            {"MATERIALS_TIKTOK_BINARY": str(tmp_path / "no-ttd.exe")},
            "--keyword", "测试", "--count", "1",
        )
        assert r.returncode != 0
        combined = _decode_cli(r.stdout) + _decode_cli(r.stderr)
        assert "TikTokDownloader" in combined
        assert "README" in combined

    def test_requires_keyword_or_author_url(self):
        r = _run_cli({}, "--count", "1")
        assert r.returncode != 0
        combined = _decode_cli(r.stdout) + _decode_cli(r.stderr)
        assert "二选一" in combined

    def test_fake_binary_runs_and_parses(self, tmp_path):
        fake = _write_fake(tmp_path)
        out = tmp_path / "cli-out"
        r = _run_cli(
            {"MATERIALS_TIKTOK_BINARY": str(fake), "FAKE_TTD_MODE": "files", "FAKE_TTD_COUNT": "2"},
            "--keyword", "测试", "--count", "2", "--output-dir", str(out),
        )
        assert r.returncode == 0, _decode_cli(r.stderr)
        stdout = _decode_cli(r.stdout)
        assert "共 2 个作品" in stdout
        assert "douyin" in stdout
        assert (out / "douyin_0001.mp4").is_file()

    def test_fake_binary_failure_exits_nonzero(self, tmp_path):
        fake = _write_fake(tmp_path)
        r = _run_cli(
            {"MATERIALS_TIKTOK_BINARY": str(fake), "FAKE_TTD_TEXT": "请求过于频繁，触发频控"},
            "--keyword", "测试", "--count", "1",
        )
        assert r.returncode != 0
        combined = _decode_cli(r.stdout) + _decode_cli(r.stderr)
        assert "RATE_LIMIT" in combined
