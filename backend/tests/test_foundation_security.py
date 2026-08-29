"""M0 通用脱敏工具测试（P-004：密钥/Token/Cookie 绝不落日志与证据）。

对齐 M2 materials 脱敏语义（独立基座实现）。断言：敏感值绝不出现在脱敏输出中。
运行：python -m pytest tests -q --basetemp=".pytest-tmp-m0"（P-001/P-011）
"""

from __future__ import annotations

import pytest

from foundation.security import redact_path, redact_text, redact_url


# ---------------------------------------------------------------- redact_url

def test_redact_url_masks_sensitive_params() -> None:
    """URL 敏感查询参数值全部掩码，普通参数保留。"""
    u = "https://www.douyin.com/video/1?sec_uid=SECRETUID&a_bogus=SIG&token=TOK&foo=ok"
    r = redact_url(u)
    for marker in ("SECRETUID", "SIG", "TOK"):
        assert marker not in r
    assert "foo=ok" in r
    assert "***" in r


def test_redact_url_keeps_scheme_host_path() -> None:
    """URL 结构保留（scheme/netloc/path），仅参数值脱敏。"""
    u = "https://v.douyin.com/abc/?token=TOK1"
    r = redact_url(u)
    assert r.startswith("https://v.douyin.com/abc/")
    assert "TOK1" not in r


def test_redact_url_empty_and_garbage() -> None:
    """空 URL / 无法解析 URL 安全返回。"""
    assert redact_url("") == ""
    assert isinstance(redact_url("not a url at all"), str)


# ---------------------------------------------------------------- redact_text

def test_redact_text_masks_secrets_and_truncates() -> None:
    """自由文本：URL 参数掩码 + 疑似密钥键值掩码 + 超长截断。"""
    t = "作者说 token=ABC123 这是秘密 https://v.douyin.com/x/?sec_uid=UID99 结尾" + "x" * 500
    r = redact_text(t)
    assert "ABC123" not in r
    assert "UID99" not in r
    assert "***" in r
    assert r.endswith("...")


def test_redact_text_key_colon_value() -> None:
    """疑似密钥键值 `key: value` 形式掩码。"""
    r = redact_text("Authorization: Bearer SECRETTOK12345")
    assert "SECRETTOK12345" not in r
    assert "***" in r


def test_redact_text_bearer_token() -> None:
    """Bearer <token> 形式：Bearer 前缀保留，仅 token 脱敏（总控裁决）。"""
    r = redact_text("Authorization: Bearer SECRETTOK12345 rest-ok")
    assert "SECRETTOK12345" not in r  # token 绝不出现在输出
    assert "Bearer ***" in r  # Bearer 前缀字样保留（仅 token 掩码）
    assert "rest-ok" in r  # 非敏感文本保留


def test_redact_text_empty() -> None:
    assert redact_text("") == ""
    assert redact_text(None) == ""


# ---------------------------------------------------------------- redact_path

def test_redact_path_masks_at_account_segment() -> None:
    """路径中 @账号 段掩码。"""
    r = redact_path(r"C:\videos\@抖音达人\video.mp4")
    assert "@抖音达人" not in r
    assert "@***" in r


def test_redact_path_masks_key_value_and_truncates() -> None:
    """路径内疑似密钥键值掩码 + 截断。"""
    p = r"D:\data\report?token=SECRETTOK" + "\\" + "x" * 300
    r = redact_path(p)
    assert "SECRETTOK" not in r
    assert len(r) <= 200


def test_redact_path_empty() -> None:
    assert redact_path("") == ""
    assert redact_path(None) == ""


# ---------------------------------------------------------------- 卫生

def test_no_plaintext_secret_in_outputs() -> None:
    """脱敏输出中不得出现明文敏感值（P-004 审计）：URL 参数与键值形式必须掩码。"""
    samples = ["SECRETTOK123", "SECRETUID", "FAKESIGN"]
    for s in samples:
        # URL 查询参数形式
        assert s not in redact_url("https://v.douyin.com/x/?token=" + s)
        # 键值形式（redact_text 对无 key= 前缀的裸字符串不做臆测掩码）
        assert s not in redact_text("token=" + s + " 附 https://v.douyin.com/x/?sec_uid=" + s)
        # Bearer 形式
        assert s not in redact_text("Authorization: Bearer " + s)
