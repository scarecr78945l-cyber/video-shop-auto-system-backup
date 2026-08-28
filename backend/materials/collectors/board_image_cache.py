"""有米云/考古加榜单图缓存（BoardImageCache，R-M2-09 / context 2.4）。

- 缓存键 = 榜单 id + 商品 id：`board_cache/{source}/{board_id}/{item_id}.jpg`
  （组件做安全消毒；LocalStorage._resolve 路径穿越防护为第二道防线）
- 幂等：已缓存（storage.exists）直接返回 {cached: True, hit: True}，不重复下载
- 批量缓存单条失败隔离：失败记日志 + 收集 {item_id, error_code}，不影响其他条（R-M2-09）
- 失败分类对齐 downloader.py 码表（复用 classify_http_status）：
  图片 404/410→NO_MATCH、请求超时→TIMEOUT、429/403→RATE_LIMIT、401→AUTH_REQUIRED、
  其他 4xx→PLATFORM_REJECT、网络/存储/其余→UNEXPECTED；
  **本类任何异常都不抛出**（缓存失败不影响选品主流程，R-M2-09）
- 多源接口化：sources 白名单（默认 ["youmi"]）+ register_source(name) 动态注册；
  "kaogujia"（考古加）为预留源——考古加采集器尚未开发（M1 REC-006 降级为可选第四源），
  落地后由上层 register_source("kaogujia") 注册，本模块零硬编码依赖
- 真实下载仅留接口：本机零外网环境走 fixtures / 本地 http.server 验证（R-M2-17）
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..config import load_config
from ..downloader import (
    AUTH_REQUIRED,
    NO_MATCH,
    PLATFORM_REJECT,
    RATE_LIMIT,
    TIMEOUT,
    UNEXPECTED,
    classify_http_status,
    redact_url,
)
from ..storage import LocalStorage, Storage

log = logging.getLogger("materials.board_image_cache")

# 缓存键前缀（目录分层：来源/榜单/商品；键语义与素材存储键一致，均为存储键）
KEY_PREFIX = "board_cache"
KEY_SUFFIX = ".jpg"

# 缓存键组件安全字符（防路径穿越/特殊字符）
_SAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]")

# 预留来源说明（多源接口化）：有米云已打通；考古加待采集器落地。
# 白名单默认只含 youmi；kaogujia 由上层在考古加采集器落地后 register_source 注册。
DEFAULT_SOURCES = ["youmi"]
RESERVED_SOURCES: dict[str, str] = {
    "youmi": "有米云（已打通）",
    "kaogujia": "考古加（预留，待考古加采集器落地后注册）",
}


def _safe_component(value: Any) -> str:
    """缓存键组件消毒：非安全字符替换为 _、去掉前导点；None/空回退 unknown（防路径穿越）。"""
    if value is None:
        return "unknown"
    s = _SAFE_COMPONENT_RE.sub("_", str(value))
    s = s.lstrip(".")  # 组件不以 . 开头：杜绝 . / .. / 隐藏文件类键（LocalStorage._resolve 为第二道防线）
    return s or "unknown"


class BoardImageCache:
    """榜单图缓存：下载（requests 流式）→ 存 storage → 返回结果；幂等 + 失败隔离。

    构造参数：
    - config：MaterialsConfig（读 config.board_cache：cache_dir/enabled/sources/timeout_seconds/max_bytes）；
    - storage：Storage 抽象（默认 LocalStorage(config.board_cache.cache_dir)；可注入 MockStorage/其他实现）；
    - sources：来源白名单（默认取 config.board_cache.sources，即 ["youmi"]；"kaogujia" 预留）。
    """

    def __init__(
        self,
        config: Any = None,
        storage: Storage | None = None,
        sources: list[str] | None = None,
    ):
        self.config = config or load_config()
        bc = self.config.board_cache
        self.cache_dir = bc.cache_dir
        self.enabled = bool(bc.enabled)
        self.timeout_seconds = float(bc.timeout_seconds)
        self.max_bytes = int(getattr(bc, "max_bytes", 10 * 1024 * 1024))
        self.storage = storage or LocalStorage(self.cache_dir)
        default_sources = list(getattr(bc, "sources", None) or DEFAULT_SOURCES)
        self.sources: set[str] = set(sources if sources is not None else default_sources)

    # ------------------------------------------------------------------ 多源
    def register_source(self, source_name: str) -> None:
        """注册数据源（多源接口化）：默认白名单 ["youmi"]；考古加 kaogujia 待采集器落地后注册。"""
        self.sources.add(str(source_name))

    def _check_source(self, source: str) -> str | None:
        """来源白名单校验：未注册返回错误码（不抛出，仅记录）。"""
        if source not in self.sources:
            return UNEXPECTED
        return None

    # ---------------------------------------------------------------- 缓存键
    def key_for(self, source: str, board_id: str, item_id: str) -> str:
        """缓存键：board_cache/{source}/{board_id}/{item_id}.jpg（R-M2-09：榜单 id+商品 id）。"""
        return "/".join(
            [
                KEY_PREFIX,
                _safe_component(source),
                _safe_component(board_id),
                f"{_safe_component(item_id)}{KEY_SUFFIX}",
            ]
        )

    # ---------------------------------------------------------------- 单条
    def cache_image(
        self,
        source: str,
        board_id: str,
        item_id: str,
        image_url: str,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """缓存单张榜单图；已缓存直接命中（幂等，不重复下载）。

        返回：
        - 首次缓存成功：{cached: True, hit: False, path, size}
        - 已缓存命中：{cached: True, hit: True, path, size}
        - 失败：{cached: False, hit: False, path: None, error_code, message, ...}
        任何异常都不抛出（R-M2-09：缓存失败不影响选品主流程）。
        """
        key = self.key_for(source, board_id, item_id)
        bad = self._check_source(source)
        if bad is not None:
            return self._fail(
                key,
                bad,
                f"未注册来源: {source!r}（白名单 {sorted(self.sources)}；"
                "考古加 kaogujia 预留，待考古加采集器落地后 register_source 注册）",
            )
        if not self.enabled:
            return self._fail(key, UNEXPECTED, "榜单图缓存已禁用（config.board_cache.enabled=False）")
        try:
            if self.storage.exists(key):
                size = self._stat_size(key)
                log.info("榜单图缓存命中（不重复下载）key=%s", key)
                return {"cached": True, "hit": True, "path": key, "size": size}
        except Exception as e:  # exists 异常按未缓存继续下载，不阻断
            log.warning("缓存探测异常（按未缓存继续下载）key=%s err=%s", key, e)
        return self._download(key, source, board_id, item_id, image_url, headers)

    def _download(
        self,
        key: str,
        source: str,
        board_id: str,
        item_id: str,
        image_url: str,
        headers: dict[str, str] | None,
    ) -> dict[str, Any]:
        """requests 流式下载 → 大小上限保护 → 存 storage；失败分类对齐 downloader.py 码表。"""
        import requests

        safe_url = redact_url(image_url)
        try:
            resp = requests.get(
                image_url, stream=True, timeout=self.timeout_seconds, headers=dict(headers or {})
            )
        except requests.Timeout as e:
            return self._fail(
                key, TIMEOUT, f"下载超时({self.timeout_seconds}s): {safe_url}",
                evidence={"url": safe_url},
            )
        except requests.RequestException as e:
            return self._fail(
                key, UNEXPECTED, f"网络错误 {e.__class__.__name__}: {safe_url}",
                evidence={"url": safe_url},
            )
        try:
            if resp.status_code != 200:
                code = classify_http_status(resp.status_code)
                return self._fail(
                    key, code, f"HTTP {resp.status_code} 下载被拒: {safe_url}",
                    http_status=resp.status_code,
                    evidence={"url": safe_url, "http_status": resp.status_code},
                )
            cl = resp.headers.get("Content-Length")
            if cl:
                try:
                    if int(cl) > self.max_bytes:
                        return self._fail(
                            key, UNEXPECTED, f"图片超过大小上限 {self.max_bytes} 字节: {safe_url}",
                            evidence={"url": safe_url},
                        )
                except ValueError:
                    pass
            chunks = bytearray()
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                chunks.extend(chunk)
                if len(chunks) > self.max_bytes:
                    return self._fail(
                        key, UNEXPECTED, f"图片超过大小上限 {self.max_bytes} 字节: {safe_url}",
                        evidence={"url": safe_url},
                    )
            if not chunks:
                return self._fail(key, NO_MATCH, f"空响应体（无图片内容）: {safe_url}", evidence={"url": safe_url})
            try:
                self.storage.put(key, bytes(chunks))
            except Exception as e:
                return self._fail(
                    key, UNEXPECTED, f"存储失败 {e.__class__.__name__}: {e}",
                    evidence={"url": safe_url},
                )
            size = len(chunks)
            log.info(
                "榜单图缓存成功 source=%s board=%s item=%s key=%s size=%d url=%s",
                source, board_id, item_id, key, size, safe_url,
            )
            return {"cached": True, "hit": False, "path": key, "size": size}
        except requests.Timeout as e:
            return self._fail(
                key, TIMEOUT, f"下载超时({self.timeout_seconds}s): {safe_url}",
                evidence={"url": safe_url},
            )
        except requests.RequestException as e:
            return self._fail(
                key, UNEXPECTED, f"下载中断 {e.__class__.__name__}: {safe_url}",
                evidence={"url": safe_url},
            )
        except Exception as e:
            return self._fail(
                key, UNEXPECTED, f"未分类异常 {e.__class__.__name__}: {e}",
                evidence={"url": safe_url},
            )
        finally:
            resp.close()

    # ---------------------------------------------------------------- 批量
    def cache_board_images(self, source: str, board_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """批量缓存：items=[{item_id, image_url}]；单条失败隔离（R-M2-09），不影响其他条。

        返回 {ok: 成功条数, total: 总条数, failed: [{item_id, error_code, message}]}。
        缺 item_id/image_url 的条目计为 UNEXPECTED 失败；本方法也不抛出异常。
        """
        ok = 0
        failed: list[dict[str, Any]] = []
        for it in items or []:
            item_id = it.get("item_id")
            image_url = it.get("image_url")
            if not item_id or not image_url:
                failed.append(
                    {
                        "item_id": item_id,
                        "error_code": UNEXPECTED,
                        "message": "条目缺少 item_id 或 image_url",
                    }
                )
                continue
            try:
                result = self.cache_image(source, board_id, str(item_id), image_url)
            except Exception as e:  # 兜底：任何异常都不影响其他条（R-M2-09）
                failed.append(
                    {
                        "item_id": item_id,
                        "error_code": UNEXPECTED,
                        "message": f"{e.__class__.__name__}: {e}",
                    }
                )
                continue
            if result.get("cached"):
                ok += 1
            else:
                failed.append(
                    {
                        "item_id": item_id,
                        "error_code": result.get("error_code", UNEXPECTED),
                        "message": result.get("message"),
                    }
                )
        return {"ok": ok, "total": len(items or []), "failed": failed}

    # ---------------------------------------------------------------- 辅助
    def _stat_size(self, key: str) -> int | None:
        """取缓存文件大小；storage 无 stat 或读取失败返回 None（不影响命中判定）。"""
        try:
            info = self.storage.stat(key)
            return int(info.get("size") or 0)
        except Exception:
            return None

    @staticmethod
    def _fail(
        key: str,
        error_code: str,
        message: str,
        http_status: int | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """统一失败返回（不抛出；日志脱敏——evidence 只含 redact_url 后的 URL）。"""
        log.warning("榜单图缓存失败 key=%s code=%s msg=%s", key, error_code, message)
        result: dict[str, Any] = {
            "cached": False,
            "hit": False,
            "path": None,
            "error_code": error_code,
            "message": message,
        }
        if http_status is not None:
            result["http_status"] = http_status
        if evidence:
            result["evidence"] = evidence
        return result
