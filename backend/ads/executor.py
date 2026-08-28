"""M5 自动小店投放（商品托管）· 托管执行器（v0.3 执行层第一步：①添加商品）。

覆盖 08 文档四①/执行层全部编排能力：
  1. ShopAdsSession：托管投放浏览器会话抽象（CDP URL/端口/Profile/登录态/UTC 创建时间）；
  2. check_login：按 page_signature 特征选择器判断登录态（特征缺失 → "expired"，AUTH_REQUIRED 语义）；
  3. BrowserConnector 抽象 + MockBrowserConnector（fixtures）/ PlaywrightBrowserConnector（骨架占位，
     禁止安装/调用真实 playwright，实机后用 connect_over_cdp 实现，接口不变）；
  4. MockPageOps：实现 PageOps Protocol 的内存假页面（脚本化行为字典 + 操作历史/时间戳）；
  5. verify_page_signature：page_changed 检测（特征锚点逐一 exists，缺失截图留证后抛
     PageChangedError，evidence={page_key, missing, current_url, screenshot_path}）；
  6. ShopAdsExecutor：add_product（①进入添加商品页 → 逐个勾选 ≤batch_size → 下一步）+
     run_batch（编排 add_product → 延迟 import settings.SettingsForm → 目标/ROI/素材/提交，
     settings 模块或方法缺失 → {ok: False, error: "settings_unavailable"}，不抛 import 错误）。

全部基于 PageOps 抽象接口 + ShopAdsUiConfig 配置驱动（选择器 key 化，P-003：改版只改配置
不崩代码）；fixtures 阶段全 Mock 驱动，无真实浏览器/登录态依赖。

口径（data-audit DA-001）：金额一律「分」（int）；时间 UTC 带时区；枚举英文；
错误码复用 09 码表（VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/TIMEOUT/NO_MATCH/
PLATFORM_REJECT/UNEXPECTED/page_changed）。
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .interfaces import PageChangedError, PageOps
from .ui_config import ShopAdsUiConfig

# ---------------------------------------------------------------- 常量

# 登录态英文枚举（D-M5-02：枚举英文存储，中文仅注释/展示）
_LOGIN_STATES: tuple[str, ...] = ("unknown", "logged_in", "expired")

# 托管两步之② settings 表单必需方法（缺失 → settings_unavailable）
_SETTINGS_REQUIRED_METHODS: tuple[str, ...] = ("choose_target", "fill_roi", "bind_materials", "submit")


# ---------------------------------------------------------------- 会话抽象
@dataclass
class ShopAdsSession:
    """托管投放浏览器会话（抽象数据，fixtures 阶段无真实浏览器）。

    login_state 英文枚举：unknown（未探测）/ logged_in（已登录）/ expired（已过期）。
    created_at 强制 UTC 带时区（naive 输入自动补 timezone.utc，DA-001）。
    """

    cdp_url: str = "ws://127.0.0.1:9222/devtools/browser"  # Chrome DevTools Protocol 地址
    port: int = 9222                                       # 共享 Chrome CDP 端口（对齐 AdsConfig.cdp_port）
    profile: str = "default"                               # 浏览器 Profile 标识（fixtures 占位）
    login_state: str = "unknown"                           # unknown / logged_in / expired
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.login_state not in _LOGIN_STATES:
            raise ValueError(
                f"非法登录态: {self.login_state!r}（可选 unknown/logged_in/expired）"
            )
        if self.created_at.tzinfo is None:
            # naive 时间按 UTC 补时区（本模块时间一律 UTC 带时区，DA-001）
            self.created_at = self.created_at.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- 登录态检查
def check_login(page: PageOps, ui_config: ShopAdsUiConfig) -> str:
    """按 page_signature 特征选择器判断登录态（返回 "logged_in" / "expired" / "unknown"）。

    - 优先取 page_signature["home"] 锚点；home 未配置时取任意已配置锚点；
    - 锚点全部 exists → "logged_in"；
    - 锚点已配置但任一缺失（特征选择器缺失）→ "expired"（上层映射 error_code=AUTH_REQUIRED 人工接管）；
    - 未配置任何锚点（fixtures 阶段默认）→ "unknown"（无法探测，不阻断流程）。
    """
    signature = ui_config.page_signature or {}
    anchor = signature.get("home") or next(iter(signature.values()), "")
    anchors = _split_anchors(anchor)
    if not anchors:
        return "unknown"  # 未配置特征锚点：无法确认登录态（保守不阻断，由选择器/page_changed 兜底）
    return "logged_in" if all(page.exists(a) for a in anchors) else "expired"


# ---------------------------------------------------------------- 浏览器连接抽象
class BrowserConnector(ABC):
    """浏览器连接抽象：connect() 返回 PageOps。

    真实 Playwright 适配器（connect_over_cdp 共享浏览器）在实机/登录态就绪后接入，
    本接口不变；fixtures 阶段由 MockBrowserConnector 承载。
    """

    @abstractmethod
    def connect(self) -> PageOps:
        """建立浏览器连接并返回可操作的页面对象（PageOps 抽象接口）。"""


class MockBrowserConnector(BrowserConnector):
    """fixtures 连接器：返回 MockPageOps（可注入预设脚本/页面）。"""

    def __init__(self, page: PageOps | None = None):
        self._page: PageOps | None = page

    def connect(self) -> PageOps:
        return self._page if self._page is not None else MockPageOps()


class PlaywrightBrowserConnector(BrowserConnector):
    """实机 Playwright 适配器骨架（占位，未接入，禁止安装/调用真实 playwright）。

    实机后使用 connect_over_cdp 实现：
        playwright.chromium.connect_over_cdp(session.cdp_url) → 取共享浏览器页面
        包装为 PageOps（接口不变，本骨架仅占位，不 import playwright）。
    """

    def __init__(self, session: ShopAdsSession | None = None):
        self.session: ShopAdsSession | None = session

    def connect(self) -> PageOps:
        raise NotImplementedError(
            "Playwright 真实适配器待实机/登录态就绪后实现（connect_over_cdp，接口不变）"
        )


# ---------------------------------------------------------------- Mock 页面（fixtures）
class MockPageOps:
    """实现 PageOps Protocol 的内存假页面（fixtures 阶段，无真实浏览器）。

    脚本化行为 script: {selector: {"action": ..., "value": ..., "count": ..., "exists": ...}}
      action 支持（扩展键 "count"/"exists" 可叠加）：
        - "click" / "fill" / "select"：正常动作（fill 写入 value，select 记录选项）；
        - "text"：read_text 返回 value（未配置则返回 ""）；
        - "error"：任何操作该选择器抛 RuntimeError（模拟元素不可用/显式等待超时）；
        - "missing"：exists()→False、count()→0、操作抛 RuntimeError（模拟元素缺失/页面未加载）。

    记录操作历史 self.history: list[str]（"op:selector"）与 self.ops: list[dict]
    （含 ts=perf_counter 时间戳与参数，供防风控间隔断言）。
    screenshot(path) 实际写临时文件（父目录自动创建）并返回路径；
    查询方法（exists/read_text/read_attr/count）不写操作历史。
    """

    def __init__(self, script: dict | None = None):
        self.script: dict[str, dict[str, Any]] = dict(script or {})
        self.history: list[str] = []            # 操作历史（文本："op:selector"）
        self.ops: list[dict[str, Any]] = []     # 操作历史（结构化，含 ts 时间戳）
        self.current_url: str = ""              # goto 记录当前地址
        self.closed: bool = False

        self._clicks: dict[str, int] = {}
        self._fills: dict[str, str] = {}
        self._options: dict[str, str] = {}
        self._texts: dict[str, str] = {}
        self._attrs: dict[tuple, Any] = {}
        self._counts: dict[str, int] = {}
        self._screenshots: list[str] = []
        self._missing: set[str] = set()

    # ------------------------------------------------------------ 测试辅助
    def set_script(self, selector: str, **spec: Any) -> "MockPageOps":
        """按选择器设置/合并脚本行为（如 set_script("#x", action="error")）。"""
        self.script.setdefault(selector, {}).update(spec)
        return self

    def set_text(self, selector: str, text: str) -> "MockPageOps":
        self._texts[selector] = text
        return self

    def set_attr(self, selector: str, attr: str, value: Any) -> "MockPageOps":
        self._attrs[(selector, attr)] = value
        return self

    def set_count(self, selector: str, n: int) -> "MockPageOps":
        self._counts[selector] = n
        return self

    def set_missing(self, *selectors: str) -> "MockPageOps":
        """标记选择器缺失（exists→False、count→0、操作抛 RuntimeError）。"""
        self._missing.update(selectors)
        return self

    def click_count(self, selector: str) -> int:
        return self._clicks.get(selector, 0)

    def fill_value(self, selector: str) -> str | None:
        return self._fills.get(selector)

    def option_value(self, selector: str) -> str | None:
        return self._options.get(selector)

    # ------------------------------------------------------------ 内部工具
    def _spec(self, selector: str) -> dict[str, Any]:
        return self.script.get(selector, {})

    def _raise_if_error(self, selector: str) -> None:
        action = self._spec(selector).get("action")
        if action in ("error", "missing") or selector in self._missing:
            raise RuntimeError(
                f"[MockPageOps] 元素不可用/缺失（模拟超时/page_changed）: {selector!r}"
            )

    def _record(self, op: str, selector: str, **extra: Any) -> None:
        ts = time.perf_counter()
        self.history.append(f"{op}:{selector}")
        self.ops.append({"op": op, "selector": selector, "ts": ts, **extra})

    # ------------------------------------------------------------ PageOps 实现
    def goto(self, url: str) -> None:
        self.current_url = url
        self._record("goto", url)

    def wait_for(self, selector: str, timeout_ms: int = 15000) -> None:
        self._raise_if_error(selector)
        self._record("wait_for", selector, timeout_ms=timeout_ms)

    def click(self, selector: str) -> None:
        self._raise_if_error(selector)
        self._clicks[selector] = self._clicks.get(selector, 0) + 1
        self._record("click", selector)

    def fill(self, selector: str, value: str) -> None:
        self._raise_if_error(selector)
        self._fills[selector] = value
        self._record("fill", selector, value=value)

    def select_option(self, selector: str, value: str) -> None:
        self._raise_if_error(selector)
        self._options[selector] = value
        self._record("select_option", selector, value=value)

    def read_text(self, selector: str) -> str:
        self._raise_if_error(selector)
        spec = self._spec(selector)
        if "text" in spec:
            return str(spec["text"])
        if spec.get("action") == "text" and "value" in spec:
            return str(spec["value"])
        return self._texts.get(selector, "")

    def read_attr(self, selector: str, attr: str) -> str | None:
        self._raise_if_error(selector)
        value = self._attrs.get((selector, attr))
        return str(value) if value is not None else None

    def exists(self, selector: str) -> bool:
        if selector in self._missing or self._spec(selector).get("action") == "missing":
            return False
        return bool(self._spec(selector).get("exists", True))

    def count(self, selector: str) -> int:
        if not self.exists(selector):
            return 0  # 真实 DOM 语义：元素缺失 count=0
        spec = self._spec(selector)
        if "count" in spec:
            return int(spec["count"])
        return self._counts.get(selector, 0)

    def screenshot(self, path: str) -> str:
        shot = Path(path)
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"mock-png")
        self._screenshots.append(str(shot))
        self._record("screenshot", str(shot))
        return str(shot)

    def close(self) -> None:
        self.closed = True
        self._record("close", "")


# ---------------------------------------------------------------- page_changed 检测
def verify_page_signature(page: PageOps, ui_config: ShopAdsUiConfig, page_key: str) -> dict:
    """校验页面特征锚点逐一 exists（P-003/R3 page_changed 检测）。

    - page_signature[page_key] 期望选择器（支持多锚点：换行/逗号/竖线分隔，或列表）；
    - 任一缺失 → 截图到 screenshot_dir（不存在自动创建）后抛 PageChangedError，
      evidence={page_key, missing, current_url, screenshot_path}；
    - 未配置锚点（fixtures 默认）→ 返回 {"ok": True, "note": "signature_not_configured"}（不阻塞）。

    返回 {"ok", "page_key", "checked", "missing", "current_url", "screenshot_path", ...}
    """
    anchors = _split_anchors(ui_config.page_signature.get(page_key, ""))
    current_url = _page_url(page)
    if not anchors:
        return {
            "ok": True, "page_key": page_key, "checked": [], "missing": [],
            "current_url": current_url, "screenshot_path": None,
            "note": "signature_not_configured",
        }
    missing = [a for a in anchors if not page.exists(a)]
    if missing:
        shot = _capture_screenshot(page, ui_config, page_key)
        raise PageChangedError(
            f"页面结构变更（page_changed，{page_key}）：特征锚点缺失 {missing}",
            evidence={
                "page_key": page_key,
                "missing": missing,
                "current_url": current_url,
                "screenshot_path": shot,
            },
        )
    return {
        "ok": True, "page_key": page_key, "checked": anchors, "missing": [],
        "current_url": current_url, "screenshot_path": None,
    }


def _capture_screenshot(page: PageOps, ui_config: ShopAdsUiConfig, page_key: str) -> str:
    """截图到 screenshot_dir（不存在自动创建目录）；失败不阻断 evidence 返回。"""
    shot_dir = Path(ui_config.screenshot_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = shot_dir / f"page_changed_{page_key}_{ts}.png"
    try:
        shot_dir.mkdir(parents=True, exist_ok=True)
        return page.screenshot(str(path))
    except Exception:  # noqa: BLE001 —— 截图失败仍须抛 PageChangedError（证据路径尽力而为）
        return str(path)


# ---------------------------------------------------------------- 托管执行器
class ShopAdsExecutor:
    """托管执行器：①添加商品 → ②投放设置 的两步编排（全 Mock 驱动，无真实浏览器）。

    错误分类映射（09 码表）：PageChangedError → "page_changed"；页面操作/显式等待失败
    （RuntimeError/TimeoutError）→ "TIMEOUT"；登录态过期 → "AUTH_REQUIRED"；
    其余异常 → "UNEXPECTED"。
    """

    def __init__(self, page: PageOps, ui_config: ShopAdsUiConfig):
        self.page: PageOps = page
        self.ui: ShopAdsUiConfig = ui_config

    # ------------------------------------------------------------ 内部工具
    def _record(self, op: str, selector: str, start: float, **extra: Any) -> dict:
        """留痕：{op, selector, ms(单步耗时), url(当前页), ts(UTC ISO8601), ...}。"""
        entry: dict[str, Any] = {
            "op": op,
            "selector": selector,
            "ms": round((time.perf_counter() - start) * 1000, 2),
            "url": _page_url(self.page),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        entry.update(extra)
        return entry

    def _fail_result(
        self,
        error_code: str,
        error: str,
        evidence: list[dict],
        selected_count: int = 0,
        truncated: bool = False,
        **extra: Any,
    ) -> dict:
        return {
            "ok": False,
            "error_code": error_code,
            "error": error,
            "selected_count": selected_count,
            "truncated": truncated,
            "evidence": evidence,
            **extra,
        }

    # ------------------------------------------------------------ ① 添加商品
    def add_product(self, product_ids: list[int]) -> dict:
        """托管两步之①：进入添加商品页 → 逐个勾选（>batch_size 截断并标记 truncated；
        item_interval_s 防风控间隔）→ 点下一步。

        返回 {ok, error_code, error, selected_count, truncated, evidence, page_changed?}
        evidence 每步含 op/selector/ms/url/ts；异常统一映射（page_changed/AUTH_REQUIRED/TIMEOUT/...）。
        """
        evidence: list[dict] = []

        # ① 登录态检查：特征选择器缺失 → expired → AUTH_REQUIRED（人工接管）
        if check_login(self.page, self.ui) == "expired":
            return self._fail_result(
                "AUTH_REQUIRED",
                "登录态已过期/未登录（check_login=expired，page_signature 特征选择器缺失）",
                evidence,
            )

        # ② 空商品列表 → NO_MATCH（无可添加托管商品）
        ids = list(product_ids or [])
        if not ids:
            return self._fail_result(
                "NO_MATCH", "商品列表为空（无可添加托管商品）", evidence
            )

        try:
            # ③ 进入添加商品页
            url = self.ui.pages.add_product or "about:blank"
            start = time.perf_counter()
            self.page.goto(url)
            evidence.append(self._record("goto", url, start, url=url))

            # ④ page_changed 检测（特征锚点逐一 exists；缺失 → PageChangedError 映射）
            start = time.perf_counter()
            sig = verify_page_signature(self.page, self.ui, "add_product")
            evidence.append(
                self._record("verify_signature", "add_product", start, checked=sig.get("checked", []))
            )

            # ⑤ 截断（平台硬限 ≤ batch_size/批）
            batch_size = int(self.ui.batch_size or 50)
            truncated = len(ids) > batch_size
            selected = ids[:batch_size]

            # ⑥ 逐个勾选 + 防风控间隔（item_interval_s）
            checkbox_tpl = self.ui.selectors.add_product_checkbox
            if not checkbox_tpl:
                raise RuntimeError(
                    "UI 选择器未配置: add_product_checkbox（fixtures 阶段测试需注入选择器值）"
                )
            for idx, pid in enumerate(selected):
                selector = checkbox_tpl.format(pid=pid)
                start = time.perf_counter()
                self.page.click(selector)
                evidence.append(self._record("click", selector, start, pid=pid, index=idx))
                if idx < len(selected) - 1:
                    sleep_start = time.perf_counter()
                    time.sleep(self.ui.item_interval_s)
                    evidence.append(
                        self._record(
                            "interval", "<sleep>", sleep_start,
                            interval_s=self.ui.item_interval_s, index=idx,
                        )
                    )

            # ⑦ 下一步
            next_sel = self.ui.selectors.add_product_next
            if not next_sel:
                raise RuntimeError(
                    "UI 选择器未配置: add_product_next（fixtures 阶段测试需注入选择器值）"
                )
            start = time.perf_counter()
            self.page.click(next_sel)
            evidence.append(self._record("click", next_sel, start, step="next"))

            return {
                "ok": True,
                "error_code": "",
                "error": "",
                "selected_count": len(selected),
                "truncated": truncated,
                "evidence": evidence,
            }

        except PageChangedError as exc:
            evidence.append(
                self._record("page_changed", "add_product", time.perf_counter(), evidence=exc.evidence)
            )
            return self._fail_result(
                "page_changed", str(exc), evidence, page_changed=exc.evidence
            )
        except Exception as exc:  # noqa: BLE001 —— 统一错误分类映射（09 码表）
            code = _classify_error(exc)
            evidence.append(
                self._record("error", type(exc).__name__, time.perf_counter(), error=str(exc))
            )
            return self._fail_result(code, str(exc), evidence)

    # ------------------------------------------------------------ ② 编排全链
    def run_batch(self, product_ids: list[int], settings_kwargs: dict | None = None) -> dict:
        """编排：add_product → 延迟 import settings.SettingsForm → 投放设置全链 → 提交。

        settings_kwargs 约定键（其余键透传 SettingsForm 构造，如 target_roi_override）：
          target_type        → choose_target（默认 "roi"）
          roi                → fill_roi（None 时走系统推荐/覆盖策略 read+resolve）
          use_recommended_roi→ True 强制走推荐策略（默认 False）
          material_ids       → bind_materials（默认 []）
        settings 模块缺失 / SettingsForm 不存在 / 必需方法缺失 → {ok: False, error: "settings_unavailable"}
        （不得抛 import 错误崩掉；getattr 兜底）。

        返回 {ok, batch_id, selected, truncated, submit_result, evidence, error, error_code}
        submit_result 为 {passed, blocked_reason, error_code} dict（SubmitResult 序列化）。
        """
        sk = dict(settings_kwargs or {})
        target_type = str(sk.pop("target_type", "roi"))
        roi = sk.pop("roi", None)
        use_recommended = bool(sk.pop("use_recommended_roi", False))
        material_ids = list(sk.pop("material_ids", []) or [])
        batch_id = _new_batch_id()

        # ① 添加商品（失败 → 原样传播错误分类，batch_id=None 无意义）
        step1 = self.add_product(product_ids)
        evidence: list[dict] = list(step1.get("evidence", []) or [])
        if not step1.get("ok", False):
            return {
                "ok": False,
                "batch_id": None,
                "selected": step1.get("selected_count", 0),
                "truncated": bool(step1.get("truncated", False)),
                "submit_result": None,
                "evidence": evidence,
                "error": step1.get("error", ""),
                "error_code": step1.get("error_code", "UNEXPECTED"),
            }

        # ② 延迟加载 settings.SettingsForm（getattr 兜底）：模块缺失/类不存在 → settings_unavailable
        settings_form_cls = _load_settings_form()
        if settings_form_cls is None:
            evidence.append(
                self._record(
                    "settings_import", "ads.settings.SettingsForm",
                    time.perf_counter(), error="settings 模块缺失或 SettingsForm 不存在",
                )
            )
            return {
                "ok": False, "batch_id": batch_id,
                "selected": step1["selected_count"], "truncated": step1["truncated"],
                "submit_result": None, "evidence": evidence,
                "error": "settings_unavailable", "error_code": "UNEXPECTED",
            }

        # ③ 投放设置全链（方法缺失 → settings_unavailable；异常统一映射）
        form = None
        try:
            form = settings_form_cls(self.page, self.ui, **sk)
            form_evidence: list = list(getattr(form, "evidence", []) or [])

            for method in _SETTINGS_REQUIRED_METHODS:
                if not callable(getattr(form, method, None)):
                    return {
                        "ok": False, "batch_id": batch_id,
                        "selected": step1["selected_count"], "truncated": step1["truncated"],
                        "submit_result": None, "evidence": evidence + form_evidence,
                        "error": "settings_unavailable", "error_code": "UNEXPECTED",
                    }

            form.choose_target(target_type)
            if roi is not None and not use_recommended:
                form.fill_roi(float(roi))
            else:
                # 系统推荐优先 / 可配置覆盖（settings.py 扩展方法，缺失 → settings_unavailable）
                read_fn = getattr(form, "read_recommended_roi", None)
                resolve_fn = getattr(form, "resolve_roi", None)
                if not callable(read_fn) or not callable(resolve_fn):
                    return {
                        "ok": False, "batch_id": batch_id,
                        "selected": step1["selected_count"], "truncated": step1["truncated"],
                        "submit_result": None, "evidence": evidence + form_evidence,
                        "error": "settings_unavailable", "error_code": "UNEXPECTED",
                    }
                form.fill_roi(resolve_fn(read_fn()))
            form.bind_materials(material_ids)
            submit_result = form.submit()
        except PageChangedError as exc:
            evidence.append(
                self._record("page_changed", "run_batch", time.perf_counter(), evidence=exc.evidence)
            )
            return {
                "ok": False, "batch_id": batch_id,
                "selected": step1["selected_count"], "truncated": step1["truncated"],
                "submit_result": None,
                "evidence": evidence + _form_evidence(form),
                "error": str(exc), "error_code": "page_changed", "page_changed": exc.evidence,
            }
        except Exception as exc:  # noqa: BLE001 —— 统一错误分类映射（09 码表）
            code = _classify_error(exc)
            evidence.append(
                self._record("error", type(exc).__name__, time.perf_counter(), error=str(exc))
            )
            return {
                "ok": False, "batch_id": batch_id,
                "selected": step1["selected_count"], "truncated": step1["truncated"],
                "submit_result": None,
                "evidence": evidence + _form_evidence(form),
                "error": str(exc), "error_code": code,
            }

        # ④ 成功路径：合并 settings 表单 evidence，序列化提交结果
        sr = _submit_result_to_dict(submit_result)
        passed = bool(sr.get("passed", True))
        return {
            "ok": passed,
            "batch_id": batch_id,
            "selected": step1["selected_count"],
            "truncated": step1["truncated"],
            "submit_result": sr,
            "evidence": evidence + _form_evidence(form),
            "error": sr.get("blocked_reason", "") if not passed else "",
            "error_code": sr.get("error_code", "") if not passed else "",
        }


# ---------------------------------------------------------------- 纯工具
def _load_settings_form() -> Any:
    """延迟加载 settings.SettingsForm（函数内 import + getattr 兜底）；失败 → None。

    满足「延迟 import（函数内 import，用 getattr 兜底）」：settings 模块缺失或
    SettingsForm 不存在一律返回 None，调用方映射 {ok: False, error: "settings_unavailable"}，
    不抛 import 错误崩掉（并行子代理产物尚未就绪时本模块照常可 import/可测）。
    """
    try:
        from . import settings as _mod
    except Exception:  # noqa: BLE001 —— settings 缺失不得崩（调用方兜底）
        return None
    return getattr(_mod, "SettingsForm", None)


def _classify_error(exc: BaseException) -> str:
    """错误分类映射（09 码表）：page_changed / TIMEOUT / UNEXPECTED。"""
    if isinstance(exc, PageChangedError):
        return "page_changed"
    if isinstance(exc, TimeoutError):
        return "TIMEOUT"
    if isinstance(exc, RuntimeError):
        # 页面操作/显式等待失败（元素不可用）按超时处理，人工接管
        return "TIMEOUT"
    return "UNEXPECTED"


def _form_evidence(form: Any) -> list:
    """取 settings 表单 evidence（可能不存在/为 None，兜底空列表）。"""
    if form is None:
        return []
    return list(getattr(form, "evidence", []) or [])


def _submit_result_to_dict(result: Any) -> dict:
    """SubmitResult（dataclass 或任意对象/dict）序列化为纯 dict。"""
    if result is None:
        return {"passed": False, "blocked_reason": "", "error_code": ""}
    if isinstance(result, dict):
        return dict(result)
    return {
        "passed": bool(getattr(result, "passed", False)),
        "blocked_reason": str(getattr(result, "blocked_reason", "")),
        "error_code": str(getattr(result, "error_code", "")),
    }


def _new_batch_id() -> str:
    """批 ID：batch-{UTC 时间戳}-{uuid8}（唯一可追踪）。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"batch-{ts}-{uuid.uuid4().hex[:8]}"


def _page_url(page: PageOps) -> str:
    """取页面当前地址（Mock=current_url；真实 Playwright 页=url 属性）。"""
    for attr in ("current_url", "url"):
        value = getattr(page, attr, None)
        if isinstance(value, str) and value:
            return value
    return ""


def _split_anchors(value: Any) -> list[str]:
    """把 page_signature 锚点值拆成选择器列表（支持换行/逗号/竖线分隔或列表）。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).replace("|", "\n").replace(",", "\n")
    return [part.strip() for part in text.splitlines() if part.strip()]


__all__ = [
    "ShopAdsSession",
    "check_login",
    "BrowserConnector",
    "MockBrowserConnector",
    "PlaywrightBrowserConnector",
    "MockPageOps",
    "verify_page_signature",
    "ShopAdsExecutor",
]
