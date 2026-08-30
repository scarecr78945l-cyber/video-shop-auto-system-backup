"""共享浏览器僵尸标签页清理（P-016 防复发，v1.1-③）。

背景
----
CDP 9223 共享浏览器长期挂机积累僵尸标签页（渲染进程无响应，如商机中心 home
``store.weixin.qq.com/shop/home``、罗盘核心数据页 ``compass.jinritemai.com/shop``），
playwright ``connect_over_cdp`` 初始化会对**每一个已打开 target 逐个
Page.enable/Network.enable**，遇到无响应僵尸页时整个初始化挂起（HTTP /json 正常但
ws 无响应）。经验证：通过 CDP HTTP ``GET /json/close/<targetId>`` 关闭**非采集目标**
页面后连接立即恢复；关闭页面**不影响登录态**（cookie 在 profile，非页面内）；
``/json/close`` 对 browser_ui（omnibox-popup）target 返回 404，此类 target 关闭不了
但不阻塞 playwright。详见 ``_management/logs/pitfall-log.md`` P-016。

能力
----
``clean_zombie_targets(port, keep_url_fragments=None)``：拉取 ``/json/list`` 并按保留
规则关闭僵尸页，返回统计 dict：

- **幂等**：无可清理页时无副作用，重复执行结果一致；
- **容错**：列表拉取/单个关闭/404 等任何失败都只计数并返回统计 dict，**绝不抛出**；
- **安全**：只关闭 http(s) 的**非采集目标** page target；browser_ui/devtools 等
  非页面 target 与 chrome:// about:blank devtools:// 等非 http(s) 页面一律跳过；
  **保留集为空（找不到任何采集目标页）时防御性不关闭任何页面**；
  全程只走 CDP HTTP（/json/list、/json/close），不触碰登录态/凭据/浏览器进程。

保留规则（默认，可按端口选择）：
- 9223 共享浏览器 → ``opprotunity``（商机中心机会品）、``rank-product``（罗盘商品榜）；
- 9555 有米云独立浏览器 → ``console.youshu.youcloud.com``。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# 采集目标页 URL 片段（默认保留）：视频号商机中心 opprotunity、抖店罗盘 rank-product
DEFAULT_KEEP_URL_FRAGMENTS: tuple[str, ...] = ("opprotunity", "rank-product")
# 有米云独立浏览器（9555）采集目标页保留片段
YOUMI_KEEP_URL_FRAGMENT: str = "console.youshu.youcloud.com"

# 只把 type == "page" 视为页面 target（browser_ui/devtools/background_page/… 全部跳过）
_PAGE_TYPE = "page"

# 仅对 http(s) 页面 target 执行关闭（chrome:// about:blank devtools:// 不碰）
_HTTP_PREFIXES = ("http://", "https://")

_DEFAULT_TIMEOUT = 4.0  # 短超时（3~5s）：僵尸渲染进程不响应时快速跳过，不挂起
_HOST = "127.0.0.1"  # 只连本机，绝不连远程
_ERR_LIMIT = 160


def default_keep_fragments(port: int) -> list[str]:
    """按端口返回默认保留的采集目标 URL 片段。

    - 9555（有米云独立浏览器）→ ``console.youshu.youcloud.com``；
    - 其余端口（含 9223 共享浏览器）→ ``opprotunity`` + ``rank-product``。
    """
    if int(port) == 9555:
        return [YOUMI_KEEP_URL_FRAGMENT]
    return list(DEFAULT_KEEP_URL_FRAGMENTS)


def _http_get_json(url: str, timeout: float) -> object:
    """GET 并解析 JSON（CDP /json/list）。非 2xx / 网络错误 / 解析失败抛异常。"""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        payload = resp.read()
    return json.loads(payload.decode("utf-8-sig"))


def _http_close(url: str, timeout: float) -> None:
    """GET /json/close/<targetId>。404/网络错误抛异常，由调用方计数容错。"""
    with urllib.request.urlopen(url, timeout=timeout):
        pass


def _truncate(msg: object, limit: int = _ERR_LIMIT) -> str:
    text = str(msg).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def clean_zombie_targets(
    port: int,
    keep_url_fragments: Optional[Iterable[str]] = None,
    timeout: float = _DEFAULT_TIMEOUT,
    host: str = _HOST,
) -> dict:
    """清理 CDP 端口的僵尸标签页（P-016 防复发），幂等/容错，绝不抛异常。

    参数
    ----
    port : CDP 调试端口（9223 共享浏览器 / 9555 有米云）。
    keep_url_fragments : 保留的采集目标页 URL 片段（大小写不敏感子串匹配）；
        None 时按端口取默认（9223→opprotunity/rank-product；9555→console.youshu.youcloud.com）。
    timeout : 单次 HTTP 请求超时（秒，默认 4.0）。
    host : CDP 主机，默认 127.0.0.1（绝不连远程）。

    返回统计 dict（永不抛异常）：
    ``{ok, port, targets_seen, pages_seen, kept, closed, close_failed, skipped,
    safe_aborted, closed_ids, errors, error}``
    - ``ok=False``：/json/list 拉取失败（浏览器未启动等），``error`` 含原因；
    - ``safe_aborted=True``：保留集为空，防御性未关闭任何页面。
    """
    port = int(port)
    keep = [
        f.lower()
        for f in (keep_url_fragments if keep_url_fragments is not None else default_keep_fragments(port))
        if f
    ]
    base = f"http://{host}:{port}"
    stats: dict = {
        "ok": False,
        "port": port,
        "targets_seen": 0,
        "pages_seen": 0,
        "kept": 0,
        "closed": 0,
        "close_failed": 0,
        "skipped": 0,
        "safe_aborted": False,
        "closed_ids": [],
        "errors": [],
        "error": None,
    }

    # 1) 拉取 target 列表（失败即返回统计，不抛）
    try:
        targets = _http_get_json(f"{base}/json/list", timeout)
    except Exception as e:  # noqa: BLE001 - 容错：任何失败返回统计不抛
        stats["error"] = _truncate(e)
        logger.warning("zombie-clean[%s] /json/list 拉取失败：%s", port, stats["error"])
        return stats
    if not isinstance(targets, list):
        stats["error"] = f"/json/list 返回非数组：{type(targets).__name__}"
        logger.warning("zombie-clean[%s] %s", port, stats["error"])
        return stats

    # 2) 分类：保留目标页 / 关闭僵尸页 / 跳过非页面与非 http(s)
    stats["targets_seen"] = len(targets)
    close_ids: list[str] = []
    for t in targets:
        if not isinstance(t, dict) or t.get("type") != _PAGE_TYPE:
            stats["skipped"] += 1  # browser_ui/devtools/background_page/… 跳过不报错
            continue
        stats["pages_seen"] += 1
        url = str(t.get("url") or "").lower()
        if not url.startswith(_HTTP_PREFIXES):
            stats["skipped"] += 1  # chrome:// about:blank devtools:// 等不碰
            continue
        if any(f in url for f in keep):
            stats["kept"] += 1  # 采集目标页，保留
            continue
        tid = str(t.get("id") or "")
        if tid:
            close_ids.append(tid)

    # 3) 防御：保留集为空（找不到任何采集目标页）→ 不关闭任何页面
    stats["ok"] = True  # 列表拉取与分类成功；之后只可能因关闭失败计数，不改变 ok
    if stats["kept"] == 0:
        stats["safe_aborted"] = True
        logger.warning(
            "zombie-clean[%s] 未找到保留的采集目标页（keep=%s），防御性不关闭任何页面",
            port,
            keep,
        )
        return stats

    # 4) 逐个关闭僵尸页：404/网络错误只计数，不中断
    for tid in close_ids:
        try:
            _http_close(f"{base}/json/close/{tid}", timeout)
        except urllib.error.HTTPError as e:
            stats["close_failed"] += 1
            if e.code == 404:
                stats["errors"].append(f"{tid}: 404（target 不可关闭，跳过）")
            else:
                stats["errors"].append(f"{tid}: HTTP {e.code}")
            logger.warning("zombie-clean[%s] 关闭 %s 失败: HTTP %s", port, tid, e.code)
        except Exception as e:  # noqa: BLE001 - 单个关闭失败不影响整体
            stats["close_failed"] += 1
            stats["errors"].append(f"{tid}: {_truncate(e)}")
            logger.warning("zombie-clean[%s] 关闭 %s 失败: %s", port, tid, _truncate(e))
        else:
            stats["closed"] += 1
            stats["closed_ids"].append(tid)
            logger.info("zombie-clean[%s] 已关闭僵尸页 target=%s", port, tid)

    return stats
