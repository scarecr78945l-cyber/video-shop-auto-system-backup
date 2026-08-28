"""TikTokDownloader 二次封装（抖音/快手/小红书批量下载 CLI 封装，子代理 A 交付）。

定位（context/README.md 2.1 + risks R-M2-04 / R-M2-05）：
- 仅用于**抖音/快手/小红书**；**视频号不在本封装范围**（R-M2-05，自研采集器在批次 3）；
- 外部 CLI 子进程 + 超时 + 输出解析 + 错误分类（对齐 downloader.py 错误码表）；
- 与下载中台解耦：本封装只产出下载文件清单（[{file_path,title,author,platform,source_url}]），
  任务账本由下载中台/上层管理（asset_download_jobs）；
- 版本锁定：requirements 固定版本，升级需回归（见 collectors/README.md）；
- 本机未安装 TikTokDownloader（环境事实）→ 开发/CI 全走 fake CLI fixtures（R-M2-17），
  真实二进制不安装不下载。

设计决策（decisions.md「子代理 A」行，2026-08-28）：
- 锁定 CLI 契约：`<binary> --mode search|author --target <关键词|达人URL> --count N --output DIR [extra_args]`
  （build_command 生成；真实版本对接时按所装版本的 CLI 语法核对 build_command，见 README「升级回归纪律」）；
- 错误分类映射（对齐 downloader.py 码表 + R-M2-06 退避 + P-002）：
  子进程超时→TIMEOUT；输出含登录失效/需要登录→AUTH_REQUIRED（**不自动重试，转人工**，P-002）；
  频控/风控/验证码→RATE_LIMIT；签名/参数错误→PLATFORM_REJECT；无输出/无命中→NO_MATCH；其他→UNEXPECTED；
- 脱敏（P-004）：日志/证据只留脱敏后文本（URL 敏感查询参数值→***、疑似密钥键值→***、超长截断），
  绝不落 Cookie/Token；返回结果的 source_url/title/author 亦脱敏；file_path 保留真实路径供上层使用，
  证据/日志中路径用 redact_path（@账号段掩码 + 截断）。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..config import load_config
from ..downloader import (
    AUTH_REQUIRED,
    NO_MATCH,
    PLATFORM_REJECT,
    RATE_LIMIT,
    TIMEOUT,
    UNEXPECTED,
)

log = logging.getLogger("materials.collectors.tiktok")

# ---------------------------------------------------------------------------
# 错误码（透传 downloader.py 码表，保证与下载中台口径一致）
# ---------------------------------------------------------------------------
ERROR_CODES = (RATE_LIMIT, TIMEOUT, NO_MATCH, PLATFORM_REJECT, AUTH_REQUIRED, UNEXPECTED)

# ---------------------------------------------------------------------------
# 输出解析：TikTokDownloader 文本输出关键字（含常见变体）
# ---------------------------------------------------------------------------
_VIDEO_EXTS = (".mp4", ".mov", ".flv", ".webm", ".m4v", ".mkv", ".avi")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

_FILE_RE = re.compile(r"(?:文件名|保存至|已保存到|文件路径|保存路径)\s*[:：]?\s*(\S+)")
_TITLE_RE = re.compile(r"(?:作品标题|视频标题|标题|作品描述)\s*[:：]?\s*(.+)")
_AUTHOR_RE = re.compile(r"(?:作者|发布者|达人|用户|昵称)\s*[:：]?\s*(.+)")
_URL_RE = re.compile(r"https?://[^\s'\"，。]+")
_BARE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")

# ---------------------------------------------------------------------------
# 错误分类关键字（对齐 downloader.py 码表 + P-002/P-003 + R-M2-04）
# 顺序敏感：先 AUTH（登录）→ RATE（频控）→ PLATFORM（签名/参数）
# ---------------------------------------------------------------------------
_AUTH_REQUIRED_HINTS = (
    "登录失效", "登录已失效", "登录已过期", "登录过期", "需要登录", "请先登录", "请登录",
    "未登录", "登录态失效", "登录状态失效", "登录状态", "cookie 失效", "cookie失效",
    "Cookie 失效", "session 过期", "会话过期", "账号已退出", "需要重新登录", "需重新登录",
)
_RATE_LIMIT_HINTS = (
    "频控", "风控", "验证码", "频率限制", "请求过于频繁", "访问过于频繁", "访问太频繁",
    "触发限流", "限流", "rate limit", "too many requests",
)
_PLATFORM_REJECT_HINTS = (
    "签名", "参数错误", "参数校验失败", "请求参数错误", "无效参数", "非法请求",
    "请求被拒绝", "签名校验失败", "签名过期", "invalid param", "params error",
)

# ---------------------------------------------------------------------------
# 脱敏（P-004）：敏感查询参数键 + 疑似密钥键名（含假 Cookie 也一律掩码）
# ---------------------------------------------------------------------------
_SENSITIVE_QUERY_KEYS = {
    "token", "access_token", "sign", "sig", "signature", "key", "cookie", "session",
    "ticket", "secret", "x-bogus", "a_bogus", "mstoken", "verify", "captcha", "auth",
    "sec_uid", "uid", "user_id", "share_token", "passport",
}

_SECRET_KEY_NAMES = (
    "cookie", "token", "access_token", "session", "sign", "sig", "signature", "secret",
    "password", "passwd", "key", "authorization", "auth", "x-bogus", "a_bogus",
    "mstoken", "sec_uid",
)
_REDACT_VALUE_RE = re.compile(
    r"(?i)([A-Za-z0-9_.\-]*?(?:%s)[A-Za-z0-9_.\-]*?)\s*[:=]\s*([^\s;&,'\"<>]+)"
    % "|".join(re.escape(k) for k in _SECRET_KEY_NAMES)
)


def _truncate(text: Any, n: int = 300) -> str:
    s = str(text or "")
    return s if len(s) <= n else s[: n - 3] + "..."


def redact_url(url: str) -> str:
    """脱敏 URL：敏感查询参数值一律替换为 ***（不落日志/证据；P-004）。

    键集在 downloader.redact_url 基础上补充 sec_uid/uid/user_id 等账号类参数；
    urlencode 会把 *** 编码为 %2A%2A%2A，这里再还原为可读的 ***（证据可读性）。
    """
    try:
        parsed = urlsplit(url or "")
        qs = [
            (k, "***" if k.lower() in _SENSITIVE_QUERY_KEYS else v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        query = urlencode(qs).replace("%2A%2A%2A", "***")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))
    except Exception:  # 解析失败原样截断返回（不留详情）
        return _truncate(url, 200)


def redact_text(text: Any, max_len: int = 300) -> str:
    """脱敏自由文本：URL 敏感查询参数→***、疑似密钥键值→***、超长截断。"""
    if not text:
        return ""
    s = str(text)
    s = _URL_RE.sub(lambda m: redact_url(m.group(0)), s)
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


def infer_platform(text: Any) -> str | None:
    """从 URL/文本推断平台（douyin / kuaishou / xiaohongshu；无命中 None）。"""
    t = (text or "").lower()
    if any(d in t for d in ("douyin.com", "v.douyin.com", "iesdouyin", "douyin", "抖音")):
        return "douyin"
    if any(d in t for d in ("kuaishou.com", "gifshow", "kuaishou", "快手")):
        return "kuaishou"
    if any(d in t for d in ("xiaohongshu.com", "xhslink.com", "xiaohongshu", "xhs", "小红书")):
        return "xiaohongshu"
    return None


def _pythonize_cmd(cmd: Sequence[str]) -> list[str]:
    """fixtures/开发态：binary 为 .py 脚本时用当前解释器启动。

    真实安装（pip 控制台脚本/exe）不受影响；本机未装 TikTokDownloader 时
    测试全走 fake CLI fixtures（R-M2-17）。
    """
    if cmd and str(cmd[0]).lower().endswith(".py"):
        return [sys.executable, *cmd]
    return list(cmd)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------
class TikTokDownloaderError(Exception):
    """TikTokDownloader 采集失败（携带错误码与脱敏证据，对齐 downloader.py 码表）。"""

    def __init__(self, error_code: str, message: str, evidence: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.evidence = dict(evidence or {})


# ---------------------------------------------------------------------------
# TikTokDownloaderCLI
# ---------------------------------------------------------------------------
class TikTokDownloaderCLI:
    """TikTokDownloader 二次封装：探测 / 关键词搜索下载 / 达人主页下载。

    参数均可配（默认从 config.tiktok 读取）：
    - binary_path: 可执行路径（env MATERIALS_TIKTOK_BINARY；None=走 PATH 探测）
    - timeout_seconds: 子进程超时（默认 300，env MATERIALS_TIKTOK_TIMEOUT_SECONDS）
    - output_dir: 输出目录（默认 config.tiktok.default_output_dir）
    - extra_args: 追加到锁定 CLI 契约尾部的额外参数（如代理/无头配置）
    - config: 注入 MaterialsConfig（测试/CLI 常用）
    """

    def __init__(
        self,
        binary_path: str | None = None,
        timeout_seconds: float | None = None,
        output_dir: str | Path | None = None,
        extra_args: Sequence[str] | None = None,
        config: Any = None,
    ):
        self.config = config or load_config()
        tcfg = self.config.tiktok
        self.binary_path = binary_path or tcfg.binary_path
        self.timeout_seconds = float(
            timeout_seconds if timeout_seconds is not None else tcfg.timeout_seconds
        )
        self.output_dir = Path(output_dir or tcfg.default_output_dir)
        self.extra_args = list(extra_args or [])

    # -- 二进制探测 ---------------------------------------------------------
    def _resolve_binary(self) -> str | None:
        if self.binary_path:
            if Path(self.binary_path).is_file():
                return str(self.binary_path)
            found = shutil.which(self.binary_path)
            if found:
                return found
            return None
        for name in ("TikTokDownloader", "tiktokdownloader", "tiktok-downloader"):
            found = shutil.which(name)
            if found:
                return found
        return None

    def check_available(self) -> dict[str, Any]:
        """探测 binary 是否可用。缺失时**不抛异常**，返回 {available, version, error}（供上层降级）。

        缺失时的 error 含安装指引（版本锁定见 collectors/README.md）与
        「视频号不在本封装范围」声明（R-M2-05）。
        """
        binary = self._resolve_binary()
        if binary is None:
            hint = self.binary_path or "PATH"
            return {
                "available": False,
                "version": None,
                "error": (
                    f"TikTokDownloader 未找到（binary_path={hint}）。"
                    "安装与版本锁定见 backend/materials/collectors/README.md；"
                    "本封装仅覆盖抖音/快手/小红书，视频号不在范围（R-M2-05）。"
                ),
            }
        try:
            proc = subprocess.run(
                _pythonize_cmd([binary, "--version"]), capture_output=True, timeout=10
            )
            text = self._decode(proc.stdout) + "\n" + self._decode(proc.stderr)
            version = next((ln.strip()[:80] for ln in text.splitlines() if ln.strip()), None)
            return {"available": True, "version": version or "unknown", "error": None}
        except subprocess.TimeoutExpired:
            return {"available": True, "version": None, "error": "版本探测超时（binary 存在）"}
        except Exception as e:  # 版本探测失败不阻断（binary 存在即可用）
            return {"available": True, "version": None, "error": f"版本探测失败 {e.__class__.__name__}"}

    def _require_binary(self) -> str:
        binary = self._resolve_binary()
        if binary is None:
            hint = self.binary_path or "PATH"
            raise TikTokDownloaderError(
                UNEXPECTED,
                f"TikTokDownloader 未安装或不可用（binary_path={hint}）。"
                "安装与版本锁定见 collectors/README.md；本机开发/CI 可用 fake CLI fixtures（R-M2-17）。",
                evidence={"available": False},
            )
        return binary

    # -- 命令构造（锁定 CLI 契约，见 README「CLI 契约」）--------------------
    def build_command(self, mode: str, target: str, count: int, output_dir: Path) -> list[str]:
        """构造锁定契约的 CLI 参数。

        契约：<binary> --mode search|author --target <关键词|达人URL> --count N
              --output DIR [extra_args...]
        真实版本对接时按所装版本的 CLI 语法核对本函数（升级回归纪律）。
        """
        binary = self._require_binary()
        cmd = [
            binary, "--mode", mode,
            "--target", str(target),
            "--count", str(int(count)),
            "--output", str(output_dir),
        ]
        cmd += list(self.extra_args or [])
        return cmd

    # -- 子进程执行 ---------------------------------------------------------
    @staticmethod
    def _decode(data: bytes) -> str:
        if not data:
            return ""
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("gbk")  # Windows 下工具可能输出 GBK
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")

    def _redact_cmd(self, cmd: Sequence[str]) -> list[str]:
        out: list[str] = []
        for a in cmd:
            if re.match(r"^https?://", str(a)):
                out.append(redact_url(str(a)))
            elif _REDACT_VALUE_RE.search(str(a)):
                out.append(_REDACT_VALUE_RE.sub(lambda m: m.group(1) + "=***", str(a)))
            else:
                out.append(_truncate(str(a), 120))
        return out

    def _run(self, cmd: Sequence[str]) -> tuple[str, str, int]:
        """执行子进程：返回 (stdout, stderr, returncode)；超时→TIMEOUT，启动失败→UNEXPECTED。"""
        run_cmd = _pythonize_cmd(cmd)
        log.info("执行 TikTokDownloader: %s", " ".join(self._redact_cmd(run_cmd)))
        try:
            proc = subprocess.run(run_cmd, capture_output=True, timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as e:
            raise TikTokDownloaderError(
                TIMEOUT,
                f"TikTokDownloader 执行超时（{self.timeout_seconds:g}s）",
                evidence={
                    "timeout_seconds": self.timeout_seconds,
                    "cmd": self._redact_cmd(run_cmd),
                },
            ) from e
        except OSError as e:
            raise TikTokDownloaderError(
                UNEXPECTED,
                f"TikTokDownloader 启动失败 {e.__class__.__name__}: {' '.join(self._redact_cmd(run_cmd))}",
                evidence={"cmd": self._redact_cmd(run_cmd)},
            ) from e
        return self._decode(proc.stdout), self._decode(proc.stderr), proc.returncode

    # -- 错误分类（对齐 downloader.py 码表）---------------------------------
    def classify_output(self, text: str) -> str | None:
        """输出文本 → 错误码；无已知特征返回 None。顺序：AUTH → RATE → PLATFORM。"""
        t = text or ""
        low = t.lower()
        if any(h in t for h in _AUTH_REQUIRED_HINTS) or any(h in low for h in ("cookie 失效", "session 过期")):
            return AUTH_REQUIRED
        if any(h in t for h in _RATE_LIMIT_HINTS) or any(h in low for h in ("rate limit", "too many requests")):
            return RATE_LIMIT
        if any(h in t for h in _PLATFORM_REJECT_HINTS) or any(h in low for h in ("invalid param", "params error")):
            return PLATFORM_REJECT
        return None

    def _failure(
        self, error_code: str, code: int, cmd: Sequence[str], stdout: str, stderr: str
    ) -> TikTokDownloaderError:
        combined = f"{stdout}\n{stderr}".strip()
        if error_code == NO_MATCH:
            msg = "TikTokDownloader 无命中结果（无输出或无可用条目）"
        else:
            excerpt = redact_text(combined, 300) or "（无输出）"
            msg = f"TikTokDownloader 采集失败 [{error_code}]：{excerpt}"
        return TikTokDownloaderError(
            error_code,
            msg,
            evidence={
                "exit_code": code,
                "cmd": self._redact_cmd(cmd),
                "stdout_excerpt": redact_text(stdout, 500),
                "stderr_excerpt": redact_text(stderr, 500),
            },
        )

    # -- 输出解析 -----------------------------------------------------------
    @staticmethod
    def _first(d: dict[str, Any], keys: Sequence[str]) -> Any:
        for k in keys:
            v = d.get(k)
            if v not in (None, ""):
                return v
        return None

    def _parse_json_output(self, text: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            # JSON 外观但解析失败 → UNEXPECTED（带脱敏原文摘要）
            raise TikTokDownloaderError(
                UNEXPECTED,
                "TikTokDownloader 输出解析失败（JSON 格式错误）",
                evidence={"stdout_excerpt": redact_text(text, 500), "error": str(e)},
            ) from e

        fp_keys = ("file_path", "path", "file", "local_path", "save_path", "video_path", "filename")
        title_keys = ("title", "desc", "caption", "text", "works_desc")
        author_keys = ("author", "nickname", "author_name", "user", "username")
        url_keys = ("source_url", "url", "share_url", "video_url", "web_url", "link")
        plat_keys = ("platform", "source_platform")

        if isinstance(data, dict):
            rows = data.get("data") or data.get("items") or data.get("list")
            if rows is None and self._first(data, fp_keys + url_keys):
                rows = [data]  # 单个条目 dict
        else:
            rows = data
        if not isinstance(rows, list):
            return []

        out: list[dict[str, Any]] = []
        for it in rows:
            if not isinstance(it, dict):
                continue
            out.append(
                {
                    "file_path": self._first(it, fp_keys),
                    "title": self._first(it, title_keys),
                    "author": self._first(it, author_keys),
                    "source_url": self._first(it, url_keys),
                    "platform": self._first(it, plat_keys),
                }
            )
        return out

    def _parse_text_output(self, text: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        cur: dict[str, Any] = {}
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            m = _FILE_RE.search(line)
            if m:
                if cur.get("file_path"):
                    entries.append(cur)
                    cur = {}
                # 无 file_path 时保留已收集的 title/author/source_url（字段顺序无关）
                cur["file_path"] = m.group(1).strip()
                continue
            t = _TITLE_RE.search(line)
            if t and not cur.get("title"):
                cur["title"] = t.group(1).strip()
                continue
            a = _AUTHOR_RE.search(line)
            if a and not cur.get("author"):
                cur["author"] = a.group(1).strip()
                continue
            u = _URL_RE.search(line)
            if u and not cur.get("source_url"):
                cur["source_url"] = u.group(0).strip()
                continue
            # 裸路径行兜底（如 Windows 完整路径输出）
            if _BARE_PATH_RE.match(line) or (
                line.lower().endswith(_VIDEO_EXTS + _IMAGE_EXTS)
                and ("/" in line or "\\" in line)
            ):
                if cur.get("file_path"):
                    entries.append(cur)
                    cur = {}
                cur["file_path"] = line
        if cur.get("file_path"):
            entries.append(cur)
        return entries

    def _absolutize(self, path: str, output_dir: Path | None) -> str:
        p = Path(str(path).strip().strip('"'))
        if p.is_absolute():
            return str(p)
        if output_dir:
            return str(Path(output_dir) / p)
        return str(p)

    def parse_output(self, text: str, output_dir: Path | None = None) -> list[dict[str, Any]]:
        """解析 TikTokDownloader 输出（JSON 优先，文本兜底），返回结果列表。

        每条 {file_path, title, author, platform, source_url}：
        - file_path：真实路径（相对名拼接 output_dir），供上层入库；
        - title/author/source_url：脱敏后（P-004）；platform 从 JSON 或 URL/文本推断；
        - 同一文件重复出现只保留首个。
        """
        text = text or ""
        stripped = text.strip()
        if not stripped:
            return []
        if stripped.startswith(("{", "[")):
            items = self._parse_json_output(stripped)
        else:
            items = self._parse_text_output(text)

        results: list[dict[str, Any]] = []
        for it in items:
            fp = it.get("file_path")
            url = it.get("source_url")
            if not fp and not url:
                continue
            plat = it.get("platform") or infer_platform(
                f"{url or ''} {it.get('title') or ''} {it.get('author') or ''}"
            )
            results.append(
                {
                    "file_path": self._absolutize(fp, output_dir) if fp else None,
                    "title": redact_text(it.get("title") or "", 300),
                    "author": redact_text(it.get("author") or "", 120),
                    "platform": plat,
                    "source_url": redact_url(url or ""),
                }
            )
        seen: set[str] = set()
        dedup: list[dict[str, Any]] = []
        for r in results:
            key = r["file_path"] or r["source_url"]
            if key in seen:
                continue
            seen.add(key)
            dedup.append(r)
        return dedup

    # -- 平台开关（R-M2-21 风控开关）---------------------------------------
    def _platform_enabled(self, platform: str | None) -> bool:
        if not platform:
            return True
        enabled = getattr(self.config.tiktok, "enabled", None)
        if enabled is None:
            return True
        return bool(enabled.get(platform, True))

    # -- 主入口 -------------------------------------------------------------
    def _ensure_output_dir(self, output_dir: str | Path | None) -> Path:
        d = Path(output_dir) if output_dir else self.output_dir
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _run_and_parse(
        self, cmd: list[str], out_dir: Path, mode: str, target: Any
    ) -> list[dict[str, Any]]:
        stdout, stderr, code = self._run(cmd)
        combined = f"{stdout}\n{stderr}".strip()
        # 1) 完全无输出 → NO_MATCH（任务书：无输出→NO_MATCH）
        if not combined:
            raise self._failure(NO_MATCH, code, cmd, stdout, stderr)
        # 2) 输出含已知失败特征（即使退出码 0）→ 按码表分类（P-002 登录失效不自动重试）
        err_code = self.classify_output(combined)
        if err_code is not None:
            raise self._failure(err_code, code, cmd, stdout, stderr)
        # 3) 退出码非 0 且无已知特征 → UNEXPECTED
        if code != 0:
            raise self._failure(UNEXPECTED, code, cmd, stdout, stderr)
        # 4) 解析输出
        results = self.parse_output(stdout, output_dir=out_dir)
        if not results:
            raise self._failure(NO_MATCH, code, cmd, stdout, stderr)
        log.info(
            "TikTokDownloader 采集完成 mode=%s target=%s results=%d out=%s",
            mode, redact_text(target, 120), len(results), str(out_dir),
        )
        return results

    def search_download(
        self, keyword: str, count: int = 10, output_dir: str | Path | None = None
    ) -> list[dict[str, Any]]:
        """批量关键词搜索下载。

        返回 [{file_path, title, author, platform, source_url}]；
        失败抛 TikTokDownloaderError（错误码对齐 downloader.py 码表）。
        """
        count = int(count)
        if count < 1:
            raise ValueError(f"count 必须 ≥1，收到 {count}")
        out = self._ensure_output_dir(output_dir)
        cmd = self.build_command("search", keyword, count, out)
        return self._run_and_parse(cmd, out, mode="search", target=keyword)

    def author_download(
        self,
        author_url_or_id: str,
        count: int = 10,
        output_dir: str | Path | None = None,
        platform: str | None = None,
    ) -> list[dict[str, Any]]:
        """达人主页批量下载（author_url_or_id：主页 URL 或达人 ID）。

        platform 可显式指定（如 "kuaishou"）；缺省从 URL 推断；
        推断/指定的平台在 config.tiktok.enabled 中禁用 → 直接报错不采集（R-M2-21）。
        """
        count = int(count)
        if count < 1:
            raise ValueError(f"count 必须 ≥1，收到 {count}")
        plat = platform or infer_platform(author_url_or_id)
        if not self._platform_enabled(plat):
            raise TikTokDownloaderError(
                UNEXPECTED,
                f"平台 {plat} 已在 config.tiktok.enabled 中禁用，跳过采集（R-M2-21 风控开关）",
                evidence={"platform": plat},
            )
        out = self._ensure_output_dir(output_dir)
        cmd = self.build_command("author", author_url_or_id, count, out)
        return self._run_and_parse(cmd, out, mode="author", target=author_url_or_id)
