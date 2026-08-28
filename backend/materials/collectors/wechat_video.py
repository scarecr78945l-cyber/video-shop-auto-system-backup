"""视频号采集器（自研：页面层 + 直链解析层，签名接口化，R-M2-03/R-M2-05）。

分层（context/README.md 2.2 外部契约）：
- 页面层：Playwright 共享 Chrome（CDP，登录态在共享 profile）拿作者/视频信息；
- 直链解析层：signer.py 的 SignatureProvider 注入请求头/查询参数后拿直链；
  签名算法变化只改 signer 一个文件（接口化可替换），不崩采集器。

模式：
- fixtures：离线样本（backend/fixtures/materials/wechat_video_hot.json），
  零浏览器零登录态零网络可跑通全链路（R-M2-17）；测试与 CLI 验收默认走此模式；
- auto：Playwright connect_over_cdp 连共享浏览器解析页面（选择器全配置化，
  P-003 改版只改配置；本任务不连真实浏览器验证，代码骨架 + 配置接口就绪）。

错误分类（对齐 downloader.py 码表 + P-002/P-003/R-M2-03）：
- 登录失效/登录门 → AUTH_REQUIRED（不自动重试，转人工登录，P-002）
- 签名器未实现/签名失效/页面结构变化 → PLATFORM_REJECT（改 signer/配置后重试）
- 无结果/找不到视频 → NO_MATCH
- 超时 → TIMEOUT
- 其余 → UNEXPECTED

输出字段口径（context/README.md 1.1 数据字典）：
{source_platform: "视频号", source_url, source_author, title, heat_score, video_id}
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..downloader import (
    AUTH_REQUIRED,
    NO_MATCH,
    PLATFORM_REJECT,
    TIMEOUT,
    UNEXPECTED,
    redact_url,
)
from .signer import SignatureProvider

log = logging.getLogger("materials.collectors.wechat_video")

# 数据字典唯一取值（context/README.md 1.1：视频号统一写作"视频号"）
SOURCE_PLATFORM = "视频号"

# fixtures 样本文件名（backend/fixtures/materials/ 下）
FIXTURE_FILENAME = "wechat_video_hot.json"

# auto 模式默认选择器/URL 模板（占位，待共享浏览器 + 抓包校准后修正；P-003 改版走配置覆盖）
DEFAULT_SELECTORS: dict[str, str] = {
    # 页面 URL（占位；校准后按实际页面修正）
    "board_url_hot": "https://channels.weixin.qq.com/feed",
    "board_url_author": "https://channels.weixin.qq.com/user/{author_id}",
    "video_url_template": "https://channels.weixin.qq.com/feed/{video_id}",
    # DOM 选择器（占位；改版只改配置不崩代码，P-003）
    "item": "[data-testid='feed-item'], .feed-item",
    "title": "h3, [class*='title']",
    "author": "[class*='author'], .nickname",
    "heat": "[class*='like'], .like-count",
    "video_link": "a[href*='video'], a[href*='sph']",
    # 登录/验证门禁（P-002 检测转人工；P-003 检测留证据）
    "login_gate": "[class*='login'], [class*='qrcode']",
    "verify_gate": "[class*='captcha'], [class*='verify']",
    # 直链提取注入点（占位；校准后按实际页面接口/JS 表达式修正）
    "direct_url_js": (
        "() => { const v = document.querySelector('video'); "
        "return v ? (v.currentSrc || v.src) : ''; }"
    ),
}


class WechatVideoError(Exception):
    """视频号采集失败（携带 downloader.py 同款错误码）。"""

    def __init__(
        self,
        error_code: str,
        message: str,
        evidence: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.evidence = evidence or {}


def _to_float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_heat(text: str) -> float | None:
    """热度文案 → 数值（'1.2万'→12000.0；'3.5亿'→350000000.0；纯数字原样；失败 None）。"""
    text = (text or "").strip().replace(",", "")
    if not text:
        return None
    mult = 1.0
    if text.endswith("亿"):
        mult, text = 100000000.0, text[:-1]
    elif text.endswith("万"):
        mult, text = 10000.0, text[:-1]
    try:
        return float(text) * mult
    except ValueError:
        return None


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError) or "timeout" in exc.__class__.__name__.lower()


def _wrap_open_error(exc: Exception) -> WechatVideoError:
    if _is_timeout(exc):
        return WechatVideoError(TIMEOUT, f"连接共享浏览器超时: {exc}")
    return WechatVideoError(UNEXPECTED, f"连接共享浏览器失败: {exc}")


class _AutoPageHandle:
    """auto 模式 playwright 资源包装：只释放本会话新建的页面与驱动连接。

    绝不调用 browser.close()（共享 Chrome 由外部启动，P-002 不污染登录态）；
    pw.stop() 仅断开 CDP 驱动，不杀浏览器进程。
    """

    def __init__(self, pw: Any, page: Any):
        self._pw = pw
        self._page = page

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def close(self) -> None:
        try:
            self._page.close()
        except Exception:
            pass
        try:
            self._pw.stop()
        except Exception:
            pass


class WechatVideoCollector:
    """视频号采集器：login_state / list_hot_videos / resolve_direct_url。

    :param config: materials.config.WechatVideoConfig（或兼容对象）
    :param page_factory: 可选注入页面工厂（测试用）；None 时 auto 模式内部用 playwright
    :param probe: 可选注入登录态探测函数（测试用）；None 时默认 CDP 轻量探测
    :param fixtures_dir: 可选 fixtures 目录覆盖；默认 config.fixtures_dir/materials
    """

    def __init__(
        self,
        config: Any,
        page_factory: Callable[[], Any] | None = None,
        probe: Callable[[], bool] | None = None,
        fixtures_dir: Path | str | None = None,
    ):
        self.config = config
        self.fixtures_mode = bool(getattr(config, "fixtures_mode", True))
        self.cdp_port = int(getattr(config, "cdp_port", 9223) or 9223)
        self.profile_dir = str(getattr(config, "profile_dir", "shared") or "shared")
        self.boards = list(getattr(config, "boards", None) or ["热门视频"])
        self.selectors = {**DEFAULT_SELECTORS, **dict(getattr(config, "selectors", None) or {})}
        base = Path(fixtures_dir) if fixtures_dir else Path(getattr(config, "fixtures_dir", "fixtures")) / "materials"
        self.fixtures_dir = base
        self._page_factory = page_factory
        self._probe = probe

    # ------------------------------------------------------------------ 登录态
    def login_state(self) -> dict:
        """探测共享浏览器登录态；无法连接浏览器时返回 {logged_in: False, error}，不抛异常。

        fixtures 模式：不连接浏览器（离线数据无需登录态），返回 logged_in=False + 说明；
        auto 模式：默认轻量探测 CDP 端口（短超时），异常 → logged_in=False。
        """
        if self.fixtures_mode:
            return {
                "logged_in": False,
                "mode": "fixtures",
                "error": "fixtures 模式未连接浏览器（离线样本，无需登录态）",
            }
        try:
            ok = self._probe() if self._probe else self._default_probe(self.cdp_port)
            return {
                "logged_in": bool(ok),
                "mode": "auto",
                "error": None if ok else f"共享浏览器 CDP 探测失败（127.0.0.1:{self.cdp_port}）",
            }
        except Exception as e:  # 不抛异常：调用方据此隔离该来源（R-M2-01）
            return {"logged_in": False, "mode": "auto", "error": str(e)[:200]}

    @staticmethod
    def _default_probe(cdp_port: int, timeout: float = 1.5) -> bool:
        """轻量探测：TCP 连接 CDP 端口 + 请求 /json/version 确认是 Chrome 调试端点。

        不打开页面不注入任何操作（避免污染共享浏览器，P-002）。
        """
        import socket

        with socket.create_connection(("127.0.0.1", cdp_port), timeout=timeout):
            pass
        import urllib.request

        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{cdp_port}/json/version", timeout=timeout
            ) as resp:
                body = resp.read(4096)
            return b'"Browser"' in body
        except Exception:
            return False

    # ------------------------------------------------------------- 热门/达人列表
    def list_hot_videos(self, board: str | None = None, limit: int = 10) -> list[dict]:
        """热门/达人视频列表（统一输出字段见模块 docstring）。

        fixtures 模式读本地 JSON；auto 模式 Playwright 共享 Chrome 解析（选择器从 config 读）。
        失败抛 WechatVideoError（错误分类见模块 docstring）。
        """
        limit = max(0, int(limit or 0))
        items = self._list_fixtures(board=board) if self.fixtures_mode else self._list_auto(board=board)
        # 统一热度降序（None 沉底）
        items.sort(
            key=lambda it: it.get("heat_score") if it.get("heat_score") is not None else -1.0,
            reverse=True,
        )
        return items[:limit] if limit else items

    # -- fixtures --------------------------------------------------------------
    def _fixture_path(self) -> Path:
        return self.fixtures_dir / FIXTURE_FILENAME

    def _load_fixture_items(self) -> list[dict]:
        path = self._fixture_path()
        if not path.exists():
            raise WechatVideoError(
                UNEXPECTED, f"fixtures 文件缺失: {path}（fixtures 离线模式不可用，R-M2-17）"
            )
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as e:
            raise WechatVideoError(UNEXPECTED, f"fixtures 文件解析失败: {path}") from e
        items = data.get("items", []) if isinstance(data, dict) else []
        return items if isinstance(items, list) else []

    def _list_fixtures(self, board: str | None) -> list[dict]:
        raw = self._load_fixture_items()
        if not raw:
            raise WechatVideoError(NO_MATCH, "fixtures 热门列表为空（NO_MATCH）")
        out: list[dict] = []
        for it in raw:
            if not isinstance(it, dict):
                continue
            video_id = str(it.get("video_id") or "").strip()
            title = str(it.get("title") or "").strip()
            if not video_id or not title:
                continue
            out.append(
                {
                    "source_platform": SOURCE_PLATFORM,
                    "source_url": str(it.get("source_url") or "").strip(),
                    "source_author": str(it.get("author") or "").strip(),
                    "title": title,
                    "heat_score": _to_float_or_none(it.get("heat_score")),
                    "video_id": video_id,
                }
            )
        if not out:
            raise WechatVideoError(NO_MATCH, "fixtures 热门列表无可解析条目（NO_MATCH）")
        return out

    # -- auto（Playwright 共享浏览器，骨架；选择器全配置化，P-003）------------
    def _open_page(self) -> Any:
        """打开共享浏览器页面：注入 page_factory 优先；否则 playwright connect_over_cdp。

        始终新建标签页（不复用既有页，避免污染登录态/页面串扰，P-002/R-M2-10）；
        只释放新建标签页与 CDP 驱动连接，不关闭共享 Chrome。
        """
        if self._page_factory is not None:
            return self._page_factory()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise WechatVideoError(
                UNEXPECTED, "auto 模式需要 playwright（未安装）；请先安装或改用 --mode fixtures"
            ) from e
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.cdp_port}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        return _AutoPageHandle(pw, page)

    @staticmethod
    def _close_page(page: Any) -> None:
        try:
            page.close()
        except Exception:
            pass

    @staticmethod
    def _detect_gate(page: Any, selector: str | None) -> bool:
        if not selector:
            return False
        try:
            loc = page.locator(selector)
            return bool(loc.count()) and bool(loc.first.is_visible())
        except Exception:
            return False

    @staticmethod
    def _cell_text(row: Any, selector: str) -> str:
        try:
            return (row.locator(selector).first.inner_text(timeout=1000) or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _cell_href(row: Any, selector: str) -> str:
        try:
            return (row.locator(selector).first.get_attribute("href") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _extract_video_id(text: str) -> str:
        """从链接/文本提取视频 id：优先 wxv_ 形态（待抓包校准），兜底 URL 末段。"""
        m = re.search(r"(wxv_[A-Za-z0-9_-]+)", text or "")
        if m:
            return m.group(1)
        tail = (text or "").split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        m = re.search(r"([A-Za-z0-9_-]{8,})", tail)
        return m.group(1) if m else ""

    def _list_auto(self, board: str | None) -> list[dict]:
        """auto 模式解析（骨架）：登录门→AUTH_REQUIRED；页面结构变化→PLATFORM_REJECT；
        有选择器但解析不出有效条目→NO_MATCH；连接/打开超时→TIMEOUT。"""
        try:
            page = self._open_page()
        except WechatVideoError:
            raise
        except Exception as e:
            raise _wrap_open_error(e) from e
        try:
            if self._detect_gate(page, self.selectors.get("login_gate")) or self._detect_gate(
                page, self.selectors.get("verify_gate")
            ):
                raise WechatVideoError(
                    AUTH_REQUIRED,
                    "视频号登录态失效（登录/验证门禁拦截），转人工登录后重试（P-002）",
                    evidence={"mode": "auto", "board": board},
                )
            loc = page.locator(self.selectors["item"])
            if loc.count() == 0:
                raise WechatVideoError(
                    PLATFORM_REJECT,
                    "视频号页面结构变化：未找到条目选择器（P-003，检查 config.wechat_video.selectors.item）",
                    evidence={"mode": "auto", "board": board},
                )
            out: list[dict] = []
            seen: set[str] = set()
            for row in loc.all():
                title = self._cell_text(row, self.selectors["title"])
                link_href = self._cell_href(row, self.selectors["video_link"])
                video_id = self._extract_video_id(link_href)
                if not title or not video_id or video_id in seen:
                    continue
                seen.add(video_id)
                out.append(
                    {
                        "source_platform": SOURCE_PLATFORM,
                        "source_url": link_href,
                        "source_author": self._cell_text(row, self.selectors["author"]),
                        "title": title,
                        "heat_score": _parse_heat(self._cell_text(row, self.selectors["heat"])),
                        "video_id": video_id,
                    }
                )
            if not out:
                raise WechatVideoError(
                    NO_MATCH, "视频号页面无有效条目（NO_MATCH）", evidence={"mode": "auto", "board": board}
                )
            return out
        except WechatVideoError:
            raise
        except Exception as e:
            raise WechatVideoError(UNEXPECTED, f"视频号页面解析失败: {e}") from e
        finally:
            self._close_page(page)

    # --------------------------------------------------------------- 直链解析
    def resolve_direct_url(
        self, video_id: str, signer: SignatureProvider | None = None
    ) -> str:
        """直链解析：signer.sign 注入后返回直链 URL（str）。

        fixtures 模式：从 fixture 条目取直链；若给了 signer，把 signer 的 query 参数
        注入 URL（headers 由调用方在下载时注入，见 downloader.fetch_file extra_headers）。
        auto 模式：页面接口提取直链（骨架，需登录态 + 抓包校准，R-M2-03）。
        错误分类：登录失效→AUTH_REQUIRED；签名器未实现/直链解析失败→PLATFORM_REJECT；
        视频不存在→NO_MATCH；超时→TIMEOUT。
        """
        video_id = str(video_id or "").strip()
        if not video_id:
            raise WechatVideoError(NO_MATCH, "video_id 为空（NO_MATCH）")
        if self.fixtures_mode:
            url = self._resolve_fixtures(video_id)
        else:
            url = self._resolve_auto(video_id, signer)
        if signer is not None:
            url = self._apply_signature(url, signer, video_id)
        return url

    def _resolve_fixtures(self, video_id: str) -> str:
        for it in self._load_fixture_items():
            if str(it.get("video_id") or "").strip() == video_id:
                url = str(it.get("direct_url") or "").strip()
                if not url:
                    raise WechatVideoError(
                        PLATFORM_REJECT, f"fixtures 条目 {video_id} 缺少 direct_url（PLATFORM_REJECT）"
                    )
                return url
        raise WechatVideoError(NO_MATCH, f"fixtures 中不存在视频 {video_id}（NO_MATCH）")

    def _apply_signature(self, url: str, signer: SignatureProvider, video_id: str) -> str:
        """把 signer.sign 返回的 query 参数注入 URL（headers 无法进 URL，下载时注入）。"""
        try:
            signed = signer.sign({"video_id": video_id}, url)
        except NotImplementedError as e:
            raise WechatVideoError(
                PLATFORM_REJECT, f"签名器未实现（PLATFORM_REJECT，R-M2-03）：{e}"
            ) from e
        query = dict((signed or {}).get("query") or {})
        if not query:
            return url
        parsed = urlsplit(url)
        existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
        existing.update(query)
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(existing), parsed.fragment)
        )

    def _resolve_auto(self, video_id: str, signer: SignatureProvider | None) -> str:
        """auto 模式直链解析（骨架：登录态 + 页面接口/抓包校准后完善，R-M2-03）。"""
        try:
            page = self._open_page()
        except WechatVideoError:
            raise
        except Exception as e:
            raise _wrap_open_error(e) from e
        try:
            if self._detect_gate(page, self.selectors.get("login_gate")) or self._detect_gate(
                page, self.selectors.get("verify_gate")
            ):
                raise WechatVideoError(AUTH_REQUIRED, "视频号登录态失效，转人工登录（P-002）")
            template = self.selectors.get("video_url_template") or DEFAULT_SELECTORS["video_url_template"]
            target = template.format(video_id=video_id)
            try:
                page.goto(target, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
            except Exception as e:
                if _is_timeout(e):
                    raise WechatVideoError(TIMEOUT, f"打开视频页超时: {redact_url(target)}") from e
                raise WechatVideoError(UNEXPECTED, f"打开视频页失败: {e}") from e
            try:
                direct = str(page.evaluate(self.selectors["direct_url_js"]) or "").strip()
            except Exception as e:
                raise WechatVideoError(
                    PLATFORM_REJECT, f"直链提取失败（页面结构/接口变化，P-003）：{e}"
                ) from e
            if not direct:
                raise WechatVideoError(
                    PLATFORM_REJECT, "直链解析为空（签名失效/页面接口变化，R-M2-03）"
                )
            return direct
        except WechatVideoError:
            raise
        except Exception as e:
            raise WechatVideoError(UNEXPECTED, f"直链解析异常: {e}") from e
        finally:
            self._close_page(page)
