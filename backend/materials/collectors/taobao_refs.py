"""淘宝商品视频与同款图采集器（子代理 B2'；context/README.md 2.3 + R-M2-08）。

定位（环境事实：共享 Chrome 登录态待确认）：
- fixtures 离线模式（默认，config.taobao_refs.fixtures_mode=True）：读
  backend/fixtures/materials/taobao_refs.json，零登录态零网络可跑通全链路（R-M2-17）；
- auto 模式（骨架）：Playwright 共享 Chrome（CDP，config.taobao_refs.cdp_port），
  选择器从 config.taobao_refs.selectors 读取；**真实浏览器链路未验证不实现细节**，
  方法抛 NotImplementedError（本任务只交付配置与接口骨架，不连真实浏览器）；
- 降级（R-M2-08）：视频抓取失败/缺失 → 同款图（images）照常 + videos=[] + note 说明；
- page_changed（P-003）：必需选择器未命中 → 记录 HTML 快照证据 + 返回 PLATFORM_REJECT
  结构化失败；错误分类对齐 downloader.py 码表（AUTH_REQUIRED / PLATFORM_REJECT /
  NO_MATCH / TIMEOUT / RATE_LIMIT / UNEXPECTED）；
- 脱敏（P-004）：结果/证据中的 URL 一律经 redact_url（敏感查询参数值→***），不落凭证。

返回契约：collect() 恒返回结构化 dict（业务失败不抛异常；auto 骨架抛 NotImplementedError）：
  {ok, source_platform, source_url, title,
   images: [{url, source_platform, media_type, ...元数据}],
   videos: [{url, source_platform, media_type, ...元数据}],
   note, evidence, error_code}
  source_platform 口径（context 1.1）：淘宝 → "淘宝"（AlibabaCollector → "1688"）。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..downloader import (
    AUTH_REQUIRED,
    NO_MATCH,
    PLATFORM_REJECT,
    RATE_LIMIT,
    TIMEOUT,
    UNEXPECTED,
    redact_url,
)

log = logging.getLogger("materials.collectors.taobao")

# 错误码（透传 downloader.py 码表，与下载中台口径一致）
ERROR_CODES = (RATE_LIMIT, TIMEOUT, NO_MATCH, PLATFORM_REJECT, AUTH_REQUIRED, UNEXPECTED)


def _truncate(text: Any, n: int = 300) -> str:
    s = str(text or "")
    return s if len(s) <= n else s[: n - 3] + "..."


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _extract_item_id(url_or_id: str) -> str | None:
    """从商品 URL/ID 提取商品数字 id（id=/itemId=/offer/ 段/裸长数字；无则 None）。

    例：https://item.taobao.com/item.htm?id=710000001 → "710000001"；
        https://detail.1688.com/offer/812345678901.html → "812345678901"。
    """
    t = (url_or_id or "").strip()
    for pat in (r"(?:id|itemId|item_id)[=/](\d+)", r"offer/(\d+)", r"(\d{8,})"):
        m = re.search(pat, t)
        if m:
            return m.group(1)
    return None


class _FixturesError(Exception):
    """fixtures 读取/解析失败（携带错误码；在 collect 内转为结构化失败）。"""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class _RefsCollectorBase:
    """淘宝/1688 商品视频与同款图采集器公共实现（fixtures 离线为主 + auto 骨架）。

    子类仅需声明四个类属性：
    - source_platform：来源平台口径（"淘宝" / "1688"，context 1.1）
    - platform_key：证据文件名/日志前缀（taobao / alibaba）
    - fixtures_filename：fixtures 文件名（taobao_refs.json / alibaba_1688.json）
    - config_attr：config 子配置名（taobao_refs / alibaba）
    """

    source_platform: str = ""
    platform_key: str = ""
    fixtures_filename: str = ""
    config_attr: str = ""

    # auto 模式文本错误分类特征（对齐 downloader.py 码表；顺序敏感：AUTH→RATE→PLATFORM）
    _AUTH_HINTS = ("登录失效", "登录已过期", "请先登录", "请登录", "扫码登录", "未登录", "需要登录")
    _RATE_HINTS = ("频控", "风控", "验证码", "请求过于频繁", "访问过于频繁", "访问太频繁", "限流")
    _REJECT_HINTS = ("签名", "参数错误", "非法请求", "请求被拒绝", "验证失败", "页面结构", "page_changed")

    def __init__(
        self,
        config: Any = None,
        fixtures_mode: bool | None = None,
        fixtures_path: str | Path | None = None,
    ):
        self.config = config or load_config()
        self._cfg = getattr(self.config, self.config_attr)
        self.fixtures_mode = bool(
            fixtures_mode if fixtures_mode is not None else self._cfg.fixtures_mode
        )
        self.fixtures_path = Path(fixtures_path) if fixtures_path is not None else (
            Path(self.config.fixtures_dir) / "materials" / self.fixtures_filename
        )

    # ------------------------------------------------------------------ 主入口
    def collect(self, product_url_or_id: str, limit: int = 5) -> dict[str, Any]:
        """采集入口：返回结构化结果（fixtures 离线 / auto 骨架）。

        - fixtures 模式：按商品 URL/ID 在 fixtures 中匹配样本；未命中→NO_MATCH 结构化失败；
          视频缺失/失败→降级（R-M2-08：images 照常 + videos=[] + note）；
          page_changed 模拟→PLATFORM_REJECT + HTML 快照证据（P-003）。
        - auto 模式：骨架，抛 NotImplementedError（真实浏览器链路未交付）。
        - 开关：config.{config_attr}.enabled=False → UNEXPECTED 结构化失败（R-M2-21 风控开关）。
        """
        limit = max(1, int(limit))
        if not self._cfg.enabled:
            return self._failure(
                UNEXPECTED,
                f"{self.source_platform} 采集已禁用（config.{self.config_attr}.enabled=False，R-M2-21 风控开关）",
            )
        if not self.fixtures_mode:
            return self._collect_auto(product_url_or_id, limit)  # 骨架：抛 NotImplementedError
        return self._collect_fixtures(product_url_or_id, limit)

    # ------------------------------------------------------------------ auto 骨架
    def _collect_auto(self, product_url_or_id: str, limit: int) -> dict[str, Any]:
        """auto 模式骨架（真实浏览器链路占位，未验证不实现细节）。

        环境事实：共享 Chrome 登录态待确认 → 本任务只交付 fixtures 离线模式。
        待接入点（后续批次）：
        1) playwright connect_over_cdp(f"http://127.0.0.1:{self._cfg.cdp_port}") 复用共享登录态（P-002）；
        2) 打开商品页 → 按 self._cfg.selectors 提取图片/视频直链（选择器/URL 全配置化，P-003）；
        3) 每次提取前跑 page_changed(html)：选择器未命中 → 记 HTML 快照 + PLATFORM_REJECT；
        4) 登录页特征 → classify_error → AUTH_REQUIRED（人工接管，P-002）。
        """
        raise NotImplementedError(
            f"{type(self).__name__} auto 模式尚未实现：需共享 Chrome 登录态确认后接入"
            f"（CDP 端口 {self._cfg.cdp_port}，选择器 {sorted((self._cfg.selectors or {}).keys())}）；"
            f"当前请使用 fixtures 离线模式（config.{self.config_attr}.fixtures_mode=True）或 --mode fixtures。"
        )

    # ------------------------------------------------------------------ fixtures
    def _load_fixtures(self) -> Any:
        try:
            with open(self.fixtures_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            raise _FixturesError(UNEXPECTED, f"fixtures 文件缺失：{self.fixtures_path}")
        except json.JSONDecodeError as e:
            raise _FixturesError(
                UNEXPECTED, f"fixtures 文件解析失败：{self.fixtures_path}（{e}）"
            )

    def _collect_fixtures(self, product_url_or_id: str, limit: int) -> dict[str, Any]:
        try:
            data = self._load_fixtures()
        except _FixturesError as exc:
            return self._failure(exc.error_code, exc.message)

        if isinstance(data, dict) and "items" in data:
            items = data["items"]
        elif isinstance(data, dict):
            # 兼容旧式 {id: {...}} 结构（如 backend/fixtures/taobao_references.json 风格）
            items = [{"id": str(k), **(dict(v or {}))} for k, v in data.items()]
        else:
            items = data
        if not isinstance(items, list):
            return self._failure(
                UNEXPECTED, f"fixtures 结构非法：{self.fixtures_path}（items 应为数组）"
            )

        key = str(product_url_or_id or "").strip()
        entry = self._lookup_item(items, key)
        if entry is None:
            return self._failure(
                NO_MATCH,
                f"fixtures 中无该商品样本（platform={self.source_platform}）：{redact_url(key)}",
                evidence={"input": redact_url(key), "fixtures_count": len(items)},
            )

        if entry.get("simulate_page_changed"):
            return self._page_changed_failure(entry, key)
        sim_error = entry.get("simulate_error")
        if sim_error:
            return self._failure(
                str(sim_error),
                f"fixtures 模拟采集失败：{sim_error}",
                evidence={"simulated": True, "input": redact_url(key)},
            )

        images = self._normalize_media(entry.get("images"), "image")[:limit]
        videos, note = self._extract_videos(entry, limit)
        evidence = {
            "mode": "fixtures",
            "source_file": str(self.fixtures_path),
            "matched_id": str(entry.get("id") or ""),
            "input": redact_url(key),
            "limit": limit,
            "fetched_at": _iso_now(),
            "note": note,
        }
        return {
            "ok": True,
            "source_platform": self.source_platform,
            "source_url": redact_url(str(entry.get("url") or product_url_or_id)),
            "title": entry.get("title"),
            "images": images,
            "videos": videos,
            "note": note,
            "evidence": evidence,
            "error_code": None,
        }

    def _lookup_item(self, items: list[Any], key: str) -> dict[str, Any] | None:
        """按商品 URL/ID 匹配 fixtures 条目：id 精确 → url 匹配 → 提取数字 id 二次匹配。"""
        if not key:
            return None
        by_id = {str(it.get("id") or ""): it for it in items if isinstance(it, dict)}
        if key in by_id:
            return by_id[key]
        for it in items:
            if not isinstance(it, dict):
                continue
            for u in (str(it.get("url") or ""), str(it.get("canonical_url") or "")):
                if u and (key == u or key in u or u.endswith(key)):
                    return it
        iid = _extract_item_id(key)
        if iid and iid in by_id:
            return by_id[iid]
        if iid:
            for it in items:
                if isinstance(it, dict) and re.search(
                    rf"[=/]{re.escape(iid)}(\b|[?&#])", str(it.get("url") or "")
                ):
                    return it
        return None

    def _normalize_media(self, raw: Any, media_type: str) -> list[dict[str, Any]]:
        """fixtures 媒体条目 → 统一 dict：兼容字符串 URL 与 dict（url + 可选元数据）。"""
        out: list[dict[str, Any]] = []
        for it in (raw or []):
            if isinstance(it, str):
                url, meta = it, {}
            elif isinstance(it, dict):
                url = it.get("url") or it.get("src")
                meta = {k: v for k, v in it.items() if k not in ("url", "src")}
            else:
                continue
            if not url or not str(url).strip():
                continue
            item: dict[str, Any] = {
                "url": redact_url(str(url)),
                "source_platform": self.source_platform,
                "media_type": media_type,
            }
            item.update(meta)
            out.append(item)
        return out

    def _extract_videos(self, entry: dict[str, Any], limit: int) -> tuple[list[dict[str, Any]], str | None]:
        """视频提取 + R-M2-08 降级：视频失败/缺失 → videos=[] + note（images 不受影响）。"""
        if entry.get("videos_error"):
            return [], (
                f"视频抓取失败降级（R-M2-08）：{entry.get('videos_error')}，"
                "仅返回同款图（images 照常）"
            )
        videos = entry.get("videos")
        if not videos:
            return [], "该商品无视频素材（fixtures 样本无视频），仅返回同款图（R-M2-08 降级）"
        return self._normalize_media(videos, "video")[:limit], None

    # ------------------------------------------------------------------ page_changed（P-003）
    def check_selectors(self, html: str, selectors: dict[str, str] | None = None) -> list[str]:
        """P-003 纯函数：返回 HTML 中未命中的必需选择器名列表（空=全部命中）。"""
        sels = selectors if selectors is not None else (self._cfg.selectors or {})
        return [name for name, pat in sels.items() if pat and not re.search(pat, str(html or ""))]

    def page_changed(self, html: str, selectors: dict[str, str] | None = None) -> bool:
        """P-003：必需选择器未命中 → True（页面结构变化，采集应中止并留证据）。"""
        return bool(self.check_selectors(html, selectors))

    def _page_changed_failure(self, entry: dict[str, Any], product_url_or_id: str) -> dict[str, Any]:
        """P-003 结构化失败：选择器未命中 → 记录 HTML 快照证据 + PLATFORM_REJECT。"""
        snapshot_html = str(
            entry.get("page_changed_snapshot")
            or "<html><body><!-- page_changed 模拟：必需选择器未命中（fixtures） --></body></html>"
        )
        missing = entry.get("missing_selectors")
        if not missing:
            missing = sorted((self._cfg.selectors or {}).keys()) or ["(未配置选择器)"]
        snapshot = self._record_html_snapshot(snapshot_html)
        evidence: dict[str, Any] = {
            "mode": "fixtures",
            "simulated": True,
            "input": redact_url(product_url_or_id),
            "missing_selectors": list(missing),
            "message": "页面结构变化（page_changed，P-003）：必需选择器未命中，采集中止并记录 HTML 快照证据",
        }
        evidence.update(snapshot)
        return self._failure(
            PLATFORM_REJECT,
            "页面结构变化（page_changed）：采集中止，已记录 HTML 快照证据",
            evidence=evidence,
        )

    def _record_html_snapshot(self, html: str) -> dict[str, Any]:
        """P-003 证据：HTML 快照落盘 data_dir/evidence/page_changed/<platform>_<ts>.html。

        返回 {html_snapshot_path, snapshot_excerpt}；落盘失败不阻断（evidence 仅留摘录+错误说明）。
        """
        try:
            d = Path(self.config.data_dir) / "evidence" / "page_changed"
            d.mkdir(parents=True, exist_ok=True)
            fname = f"{self.platform_key}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.html"
            path = d / fname
            path.write_text(str(html), encoding="utf-8")
            return {"html_snapshot_path": str(path), "snapshot_excerpt": _truncate(html, 300)}
        except OSError as e:
            return {
                "html_snapshot_path": None,
                "snapshot_excerpt": _truncate(html, 300),
                "snapshot_write_error": f"{e.__class__.__name__}: {e}",
            }

    # ------------------------------------------------------------------ 错误分类
    def classify_error(self, text: str) -> str | None:
        """文本特征 → 错误码（对齐 downloader.py 码表 + P-002）。

        顺序敏感：AUTH（登录）→ RATE（频控）→ PLATFORM（签名/参数/页面结构）；无特征返回 None。
        """
        t = text or ""
        if any(h in t for h in self._AUTH_HINTS):
            return AUTH_REQUIRED
        if any(h in t for h in self._RATE_HINTS):
            return RATE_LIMIT
        if any(h in t for h in self._REJECT_HINTS):
            return PLATFORM_REJECT
        return None

    # ------------------------------------------------------------------ 结构化失败
    def _failure(
        self, error_code: str, message: str, evidence: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """结构化失败（不抛异常；error_code 对齐 downloader.py 码表）。"""
        ev = dict(evidence or {})
        ev.setdefault("message", message)
        ev.setdefault("mode", "fixtures" if self.fixtures_mode else "auto")
        return {
            "ok": False,
            "source_platform": self.source_platform,
            "source_url": None,
            "title": None,
            "images": [],
            "videos": [],
            "note": None,
            "message": message,
            "evidence": ev,
            "error_code": error_code,
        }


class TaobaoReferencesCollector(_RefsCollectorBase):
    """淘宝商品视频与同款图采集器（context/README.md 2.3；source_platform="淘宝"）。"""

    source_platform = "淘宝"
    platform_key = "taobao"
    fixtures_filename = "taobao_refs.json"
    config_attr = "taobao_refs"


__all__ = ["TaobaoReferencesCollector", "ERROR_CODES"]
