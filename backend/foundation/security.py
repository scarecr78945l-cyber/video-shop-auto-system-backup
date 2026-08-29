"""M0 基座通用脱敏工具（P-004：密钥/Token/Cookie 绝不落日志与证据）。

全系统统一入口（对齐 M2 `materials` 脱敏语义，独立实现不依赖业务模块）：
- `redact_url`：URL 敏感查询参数值 → ***（token/sec_uid/a_bogus/sign 等，键集见下）；
- `redact_text`：自由文本内 URL 脱敏 + 疑似密钥键值掩码 + 超长截断；
- `redact_path`：文件路径内 @账号 段掩码 + 疑似密钥键值 + 截断（证据/日志用；
  真实 file_path 落库不受影响）。
任何日志/证据/evidence 写入前必须经本模块处理（宪法第 8 节第 5 条）。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 敏感查询参数键（URL ?k=v 中 v 一律掩码；覆盖平台常见账号/签名参数）
SENSITIVE_QUERY_KEYS: set[str] = {
    "token", "access_token", "sign", "sig", "signature", "key", "cookie", "session",
    "ticket", "secret", "x-bogus", "a_bogus", "mstoken", "verify", "captcha", "auth",
    "sec_uid", "uid", "user_id", "share_token", "passport", "authorization", "apikey", "api_key",
}

# 疑似密钥键名（key=value / key: value 中 value 掩码）
_SECRET_KEY_NAMES: tuple[str, ...] = (
    "cookie", "token", "access_token", "session", "sign", "sig", "signature", "secret",
    "password", "passwd", "key", "authorization", "auth", "x-bogus", "a_bogus",
    "mstoken", "sec_uid", "apikey", "api_key",
)

_URL_RE = re.compile(r"https?://[^\s'\"，。]+")
_REDACT_VALUE_RE = re.compile(
    r"(?i)([A-Za-z0-9_.\-]*?(?:%s)[A-Za-z0-9_.\-]*?)\s*[:=]\s*([^\s;&,'\"<>]+)"
    % "|".join(re.escape(k) for k in _SECRET_KEY_NAMES)
)
# Bearer <token> 形式（token 前缀类型）：token 段整体掩码
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+")


def _truncate(text: Any, n: int = 300) -> str:
    s = str(text or "")
    return s if len(s) <= n else s[: n - 3] + "..."


def redact_url(url: str) -> str:
    """脱敏 URL：敏感查询参数值一律替换为 ***（不落日志/证据；P-004）。

    urlencode 会把 *** 编码为 %2A%2A%2A，这里还原为可读的 ***（证据可读性）。
    解析失败原样截断返回（不留详情）。
    """
    try:
        parsed = urlsplit(url or "")
        qs = [
            (k, "***" if k.lower() in SENSITIVE_QUERY_KEYS else v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        query = urlencode(qs).replace("%2A%2A%2A", "***")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))
    except Exception:  # pragma: no cover - 解析失败兜底
        return _truncate(url, 200)


def redact_text(text: Any, max_len: int = 300) -> str:
    """脱敏自由文本：URL 敏感查询参数→***、疑似密钥键值→***、Bearer token→***、超长截断。"""
    if not text:
        return ""
    s = str(text)
    s = _URL_RE.sub(lambda m: redact_url(m.group(0)), s)
    s = _BEARER_RE.sub("Bearer ***", s)  # 先 Bearer <token>（避免 key= 规则吃掉 "Bearer " 前缀）
    s = _REDACT_VALUE_RE.sub(lambda m: m.group(1) + "=***", s)
    return _truncate(s, max_len)


def redact_path(path: Any, max_len: int = 200) -> str:
    """脱敏文件路径（证据/日志用）：掩码 @账号 段与疑似密钥键值，超长截断。

    注意：返回结果中的 file_path 是真实路径（上层落库/入库需要），
    只有证据与日志中的路径走本函数。
    """
    if not path:
        return ""
    s = str(path)
    s = re.sub(r"@[^\s\\/]+", "@***", s)  # 文件名中的 @作者 段
    s = _REDACT_VALUE_RE.sub(lambda m: m.group(1) + "=***", s)
    return _truncate(s, max_len)


__all__ = ["SENSITIVE_QUERY_KEYS", "redact_url", "redact_text", "redact_path"]
