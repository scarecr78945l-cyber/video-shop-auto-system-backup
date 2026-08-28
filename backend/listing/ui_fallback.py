"""M4 自动上架：Playwright 兜底降级通道（仅处理官方 API 未覆盖操作）。

- 零真实浏览器：本模块禁止 import playwright / 发起真实浏览器或网络调用；
  浏览器操作全部走 PageOps 抽象接口 + MockPageOps 脚本化注入（测试与离线模拟）。
- P-003 纪律：页面改版即检测留证据 —— 锚点签名校验失败抛 PageChangedError，
  evidence 携带 {page_key, missing, current_url, screenshot_path}，不静默放行。
- 07 文档原则：UI 失败不阻塞 OpenAPI 队列 —— run() 失败一律返回结构化 dict，
  不向队列层抛异常；连续失败 >=2 返回 error_code="UNEXPECTED" 并建议人工接管（R10/R11）。
- P-006：批处理 ≤batch_size（默认 50）/批串行，item_interval_s 防风控间隔。

运行：cd backend && python -m pytest tests/test_listing_fallback.py -q --basetemp=".pytest-tmp-m4"
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional, Protocol

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UiFallbackConfig(BaseSettings):
    """UI 兜底通道配置。环境变量前缀 `LISTING_UI_`（如 LISTING_UI_BATCH_SIZE）。"""

    model_config = SettingsConfigDict(
        env_prefix="LISTING_UI_", env_file=".env", extra="ignore"
    )

    batch_size: int = 50  # 批处理上限（≤50/批串行，P-006）
    item_interval_s: float = 5.0  # 防风控间隔（批内相邻商品最小间隔，秒）
    page_timeout_ms: int = 15000  # 页面操作超时（毫秒）
    screenshot_dir: str = "data/ui_evidence"  # 改版/失败证据截图目录
    # 每页面锚点选择器列表：全部存在才算页面签名未变
    signatures: dict[str, list[str]] = Field(default_factory=dict)


class PageOps(Protocol):
    """浏览器操作抽象接口（真实实现 = Playwright 封装，测试 = MockPageOps）。"""

    def goto(self, page_key: str) -> None: ...

    def click(self, selector: str) -> None: ...

    def fill(self, selector: str, value: str) -> None: ...

    def screenshot(self, path: str) -> str: ...

    def current_url(self) -> str: ...

    def has_selector(self, selector: str) -> bool: ...


class PageChangedError(Exception):
    """页面签名变化：配置锚点缺失，携带改版证据（P-003，不静默）。"""

    def __init__(
        self,
        page_key: str,
        missing: list[str],
        current_url: str,
        screenshot_path: str,
    ):
        self.page_key = page_key
        self.missing = list(missing)
        self.current_url = current_url
        self.screenshot_path = screenshot_path
        self.evidence = {
            "page_key": page_key,
            "missing": self.missing,
            "current_url": current_url,
            "screenshot_path": screenshot_path,
        }
        super().__init__(
            f"页面签名变化: page_key={page_key} 缺失锚点 {self.missing}，"
            f"截图 {screenshot_path}（P-003 改版留证）"
        )


class MockPageOps:
    """脚本化 PageOps：script 字典驱动行为 + 全量 ops 历史（含时间戳）留痕。

    script 键格式：
      - "{op}:{selector}"（如 "click:.save-btn"）或裸 "{op}"（对该操作全局生效）；
      - 值为 Exception 实例 → 执行该操作时抛出；
      - "has_selector" / "current_url" 的值可为 bool / str（作为返回值）；
      - "missing_selectors": [..] → 这些选择器 has_selector 返回 False。
    """

    def __init__(self, script: dict[str, Any] | None = None):
        self.script: dict[str, Any] = dict(script or {})
        self.ops: list[dict[str, Any]] = []  # [{op, selector/path/value, at, result|error}]
        self._current_url: str = "https://mock.page/"
        self.missing_selectors: set[str] = set(self.script.get("missing_selectors", []))

    # ------------------------------------------------------------ 内部

    def _apply(self, op: str, selector: str = "", value: Any = None) -> Any:
        entry: dict[str, Any] = {"op": op, "at": time.time()}
        if selector:
            entry["selector"] = selector
        if value is not None:
            entry["value"] = value
        action = self.script.get(f"{op}:{selector}", self.script.get(op))
        if isinstance(action, Exception):
            entry["error"] = str(action)
            self.ops.append(entry)
            raise action
        entry["result"] = action
        self.ops.append(entry)
        return action

    # ------------------------------------------------------------ PageOps

    def goto(self, page_key: str) -> None:
        self._apply("goto", page_key)
        self._current_url = f"https://mock.page/{page_key}"

    def click(self, selector: str) -> None:
        self._apply("click", selector)

    def fill(self, selector: str, value: str) -> None:
        self._apply("fill", selector, value)

    def screenshot(self, path: str) -> str:
        path = str(path)
        action = self.script.get("screenshot")
        if isinstance(action, Exception):
            self.ops.append({"op": "screenshot", "path": path, "at": time.time(), "error": str(action)})
            raise action
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)  # 截图目录自动创建
        with open(path, "wb") as f:
            f.write(b"mock-screenshot-png")
        self.ops.append({"op": "screenshot", "path": path, "at": time.time(), "result": "written"})
        return path

    def current_url(self) -> str:
        action = self.script.get("current_url")
        if isinstance(action, str):
            self._current_url = action
        return self._current_url

    def has_selector(self, selector: str) -> bool:
        action = self._apply("has_selector", selector)
        if isinstance(action, bool):
            return action
        return selector not in self.missing_selectors


def verify_page_signature(ops: PageOps, page_key: str, config: UiFallbackConfig) -> None:
    """校验页面锚点签名：全部锚点 has_selector 通过则放行，否则截图留证抛 PageChangedError。

    页面未登记签名（signatures 无该 page_key）→ 视为通过（兜底通道不在白名单页操作）。
    """
    anchors = config.signatures.get(page_key, [])
    missing = [s for s in anchors if not ops.has_selector(s)]
    if missing:
        ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        screenshot_path = os.path.join(
            config.screenshot_dir, f"page_changed_{page_key}_{ts}.png"
        )
        ops.screenshot(screenshot_path)
        raise PageChangedError(page_key, missing, ops.current_url(), screenshot_path)


# 内置操作集：每操作 = goto + click/fill 步骤序列；
# 选择器默认值可被 params["selectors"] 覆盖（运行期适配改版页面）。
OPERATION_SELECTORS: dict[str, dict[str, Any]] = {
    "select_category": {
        "steps": [
            ("click", ".category-tree"),
            ("click", ".category-node"),
        ],
    },
    "set_purchase_limit": {
        "steps": [
            ("fill", "#purchase-limit", "purchase_limit"),
            ("click", ".save-btn"),
        ],
    },
    "fill_custom_param": {
        "steps": [
            ("fill", "#custom-param", "value"),
            ("click", ".save-btn"),
        ],
    },
}


class FallbackRunner:
    """UI 兜底通道执行器：签名校验 → 操作序列 → 结构化结果（失败不抛到队列层）。"""

    def __init__(self, config: UiFallbackConfig, ops: Optional[PageOps] = None):
        self.config = config
        self.ops: PageOps = ops if ops is not None else MockPageOps()
        self.consecutive_failures: int = 0  # 连续失败计数（>=2 建议人工接管，R10/R11）

    # ------------------------------------------------------------ 主入口

    def run(
        self,
        page_key: str,
        operation: str,
        params: dict[str, Any] | None = None,
    ) -> dict:
        """单页单操作：verify_page_signature → goto → 操作步骤 → {ok, evidence}。

        任何失败（改版/超时/无匹配/未知）→ 结构化 dict，绝不向队列层抛异常。
        """
        params = params or {}
        try:
            verify_page_signature(self.ops, page_key, self.config)
            self.ops.goto(page_key)
            self._execute(operation, params)
            self.consecutive_failures = 0
            return {
                "ok": True,
                "evidence": {
                    "page_key": page_key,
                    "operation": operation,
                    "params": params,
                    "url": self.ops.current_url(),
                    "screenshot_dir": self.config.screenshot_dir,
                    "page_timeout_ms": self.config.page_timeout_ms,
                },
            }
        except PageChangedError as exc:
            return self._fail("page_changed", exc.evidence)
        except Exception as exc:
            return self._fail(
                self._map_error(exc),
                {"page_key": page_key, "operation": operation, "error": str(exc)},
            )

    def run_batch(self, items: list[dict]) -> list[dict]:
        """串行批处理：≤batch_size/批，批内相邻商品间隔 item_interval_s（P-006 防风控）。

        items: [{"page_key", "operation", "params"}]；超出 batch_size 的部分不处理。
        """
        results: list[dict] = []
        for i, item in enumerate(items[: self.config.batch_size]):
            if i > 0:
                time.sleep(self.config.item_interval_s)
            results.append(
                self.run(
                    item["page_key"],
                    item["operation"],
                    item.get("params"),
                )
            )
        return results

    # ------------------------------------------------------------ 内部

    def _execute(self, operation: str, params: dict[str, Any]) -> None:
        spec = OPERATION_SELECTORS.get(operation)
        if spec is None:
            raise ValueError(f"未知 UI 操作: {operation}")
        for step in spec["steps"]:
            action = step[0]
            selector = self._resolve_selector(step[1], params)
            if action == "click":
                self.ops.click(selector)
            elif action == "fill":
                param_key = step[2]
                value = params.get(param_key)
                if value is None:  # 兼容 params 直接以选择器为键
                    value = params.get(step[1])
                self.ops.fill(selector, "" if value is None else str(value))
            else:
                raise ValueError(f"未知步骤动作: {action}")

    @staticmethod
    def _resolve_selector(default: str, params: dict[str, Any]) -> str:
        overrides = params.get("selectors") or {}
        return overrides.get(default, default)

    @staticmethod
    def _map_error(exc: Exception) -> str:
        msg = str(exc)
        lowered = msg.lower()
        if isinstance(exc, TimeoutError) or "timeout" in lowered:
            return "TIMEOUT"
        if "no_match" in lowered or "no match" in lowered:
            return "NO_MATCH"
        return "UNEXPECTED"

    def _fail(self, error_code: str, evidence: dict[str, Any]) -> dict:
        self.consecutive_failures += 1
        result = {"ok": False, "error_code": error_code, "evidence": evidence}
        if self.consecutive_failures >= 2:
            # R10/R11：连续失败 >=2 → UNEXPECTED + 人工接管建议
            result["error_code"] = "UNEXPECTED"
            result["evidence"] = {
                **evidence,
                "consecutive_failures": self.consecutive_failures,
                "manual_takeover": True,
                "suggestion": "连续失败 >=2 次，UI 兜底通道建议人工接管（R10/R11）",
            }
        return result
