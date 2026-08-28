"""M3 上传素材库 upload · UiUploader（mode=ui，Playwright 兜底抽象）。

REC-002 Playwright 兜底链路。本子包独立定义最小 PageOps 协议（复用 M5
ads/interfaces.py 的思路但不跨包 import），选择器全配置化；fixtures 阶段
用 MockPageOps 记录调用、脚本驱动失败场景，零真实浏览器零网络。

page_changed 检测（P-003）：上传前 ``verify_page_signature`` 校验页面锚点
选择器，缺失即抛 PageChangedError（证据含 missing/current_url/screenshot_path），
上传结果映射为 NO_MATCH + evidence["page_changed"]=True，留痕并转人工接管。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from .service import (
    ERR_AUTH_REQUIRED,
    ERR_NO_MATCH,
    ERR_PLATFORM_REJECT,
    ERR_RATE_LIMIT,
    ERR_TIMEOUT,
    ERR_UNEXPECTED,
    UploadResult,
    UploadService,
    derive_target_id,
    deterministic_material_id,
)


@runtime_checkable
class PageOps(Protocol):
    """浏览器页面最小操作集（Playwright 语义子集，本子包独立定义）。

    真实实现后续用 Playwright Page 包装（goto/wait_for/click/fill/read_text/
    exists/screenshot/current_url 一一对应）；Mock 实现逐方法记录调用供断言。
    """

    def goto(self, url: str) -> None: ...
    def wait_for(self, selector: str, timeout_ms: int = 15000) -> None: ...
    def click(self, selector: str) -> None: ...
    def fill(self, selector: str, value: str) -> None: ...
    def read_text(self, selector: str) -> str: ...
    def exists(self, selector: str) -> bool: ...
    def screenshot(self, path: str) -> str: ...
    def current_url(self) -> str: ...


class PageChangedError(RuntimeError):
    """页面结构与配置锚点不一致（P-003）：携带 evidence 供留痕与人工接管。"""

    def __init__(self, message: str, evidence: Optional[dict] = None):
        super().__init__(message)
        self.evidence: dict = evidence or {}


# 默认选择器（全配置化，P-003：UI 改版只改配置不改代码）
DEFAULT_SELECTORS: dict[str, Any] = {
    "page_anchors": [
        "[data-testid=material-upload-page]",
        ".material-upload-container",
    ],
    "upload_entry": "text=上传素材",
    "file_input": "input[type=file]",
    "title_input": "#material-title",
    "submit": "button:has-text('提交上传')",
    "result_id": "#material-id",
    "error_box": ".upload-error",
}

FAIL_TEXT: dict[str, str] = {
    ERR_AUTH_REQUIRED: "登录已失效，请重新登录",
    ERR_RATE_LIMIT: "操作太频繁，请稍后再试",
    ERR_PLATFORM_REJECT: "素材审核不通过，不支持投放",
    ERR_TIMEOUT: "请求超时",
}


class MockPageOps:
    """fixtures 记录型实现：逐调用留痕 + script 驱动失败场景（零浏览器）。"""

    def __init__(
        self,
        *,
        material_id: Optional[str] = None,
        fail_code: str = "",
        error_text: str = "",
        missing_selectors: Optional[list[str]] = None,
        timeout_selectors: Optional[list[str]] = None,
        url: str = "https://channels.weixin.qq.com/shop/material/upload",
    ):
        self.material_id = material_id
        self.fail_code = fail_code
        self.error_text = error_text or FAIL_TEXT.get(fail_code, "")
        self.missing_selectors = set(missing_selectors or [])
        self.timeout_selectors = set(timeout_selectors or [])
        self.url = url
        self.calls: list[dict[str, Any]] = []
        self._error_visible = False

    # ---------- 记录型操作 ----------

    def _record(self, op: str, **kw: Any) -> None:
        self.calls.append({"op": op, **kw})

    def goto(self, url: str) -> None:
        self._record("goto", url=url)

    def current_url(self) -> str:
        self._record("current_url")
        return self.url

    def wait_for(self, selector: str, timeout_ms: int = 15000) -> None:
        self._record("wait_for", selector=selector, timeout_ms=timeout_ms)
        if selector in self.timeout_selectors:
            raise TimeoutError(f"wait_for 超时: {selector}")

    def exists(self, selector: str) -> bool:
        self._record("exists", selector=selector)
        if selector in self.missing_selectors:
            return False
        if selector == DEFAULT_SELECTORS["error_box"]:
            return self._error_visible
        return True

    def click(self, selector: str) -> None:
        self._record("click", selector=selector)
        if self.fail_code and selector == DEFAULT_SELECTORS["submit"]:
            self._error_visible = True  # 提交后平台报错 → 错误框出现

    def fill(self, selector: str, value: str) -> None:
        self._record("fill", selector=selector, value=value)

    def read_text(self, selector: str) -> str:
        self._record("read_text", selector=selector)
        if selector == DEFAULT_SELECTORS["result_id"]:
            return self.material_id or ""
        if selector == DEFAULT_SELECTORS["error_box"]:
            return self.error_text
        return ""

    def screenshot(self, path: str) -> str:
        self._record("screenshot", path=str(path))
        return str(path)


class UiUploader(UploadService):
    """Playwright 兜底上传（fixtures：page_ops 缺省 MockPageOps，零浏览器）。"""

    mode = "ui"
    DEFAULT_UPLOAD_URL = "https://channels.weixin.qq.com/shop/material/upload"

    def __init__(
        self,
        config=None,
        db=None,
        repo=None,
        *,
        page_ops: Optional[PageOps] = None,
        selectors: Optional[dict[str, Any]] = None,
        upload_url: Optional[str] = None,
        screenshot_dir: Optional[Any] = None,
        signature_anchors: Optional[list[str]] = None,
        page_timeout_ms: int = 15000,
    ):
        super().__init__(config, db, repo)
        self.page_ops: PageOps = page_ops or MockPageOps()
        self.selectors: dict[str, Any] = {**DEFAULT_SELECTORS, **(selectors or {})}
        self.upload_url = upload_url or self.DEFAULT_UPLOAD_URL
        self.screenshot_dir = (
            Path(screenshot_dir)
            if screenshot_dir is not None
            else Path(self.config.data_dir) / "upload_screenshots"
        )
        self.signature_anchors = list(
            signature_anchors
            if signature_anchors is not None
            else (self.selectors.get("page_anchors") or [])
        )
        self.page_timeout_ms = int(page_timeout_ms)

    # ---------------------------------------------------------------- 双轨接口

    def upload_video(self, file_path, meta, *, target_id=None, batch_no=1, batch_id=None):
        return self._upload("video", file_path, meta, target_id=target_id, batch_no=batch_no, batch_id=batch_id)

    def upload_image(self, file_path, meta, *, target_id=None, batch_no=1, batch_id=None):
        return self._upload("image", file_path, meta, target_id=target_id, batch_no=batch_no, batch_id=batch_id)

    # ---------------------------------------------------------------- 内部

    def verify_page_signature(self, page_ops: Optional[PageOps] = None) -> None:
        """页面结构校验（P-003）：锚点缺失 → PageChangedError（截图 + 缺失清单证据）。"""
        ops = page_ops or self.page_ops
        missing = [s for s in self.signature_anchors if not ops.exists(s)]
        if missing:
            shot = str(self.screenshot_dir / "page_changed.png")
            try:
                ops.screenshot(shot)
            except Exception:  # noqa: BLE001 —— 截图失败不掩盖 page_changed 主因
                pass
            current_url = ""
            getter = getattr(ops, "current_url", None)
            if callable(getter):
                try:
                    current_url = str(getter())
                except Exception:  # noqa: BLE001
                    current_url = ""
            raise PageChangedError(
                "页面结构与配置锚点不一致（P-003）：" + ",".join(missing),
                evidence={
                    "missing": missing,
                    "current_url": current_url,
                    "screenshot_path": shot,
                },
            )

    def _classify_error(self, text: str) -> str:
        """按错误文案关键词分类（真实后台文案变化后走 UNEXPECTED 留证据）。"""
        t = text or ""
        for code, keyword in (
            (ERR_AUTH_REQUIRED, "登录"),
            (ERR_RATE_LIMIT, "频繁"),
            (ERR_PLATFORM_REJECT, "审核"),
            (ERR_TIMEOUT, "超时"),
        ):
            if keyword in t:
                return code
        return ERR_UNEXPECTED

    def _upload(self, target_type, file_path, meta, *, target_id, batch_no, batch_id):
        tid = target_id or derive_target_id(meta, file_path)
        base = {
            "mode": "ui",
            "url": self.upload_url,
            "target_type": target_type,
        }
        if batch_id:
            base["batch_id"] = batch_id

        # P-003 page_changed 前置检测
        try:
            self.verify_page_signature()
        except PageChangedError as exc:
            return self._finish_failed(
                target_type, tid, ERR_NO_MATCH, base,
                extra={**exc.evidence, "page_changed": True, "message": str(exc)},
                batch_no=batch_no,
            )

        flow: list[str] = []
        try:
            self.page_ops.goto(self.upload_url)
            flow.append("goto")
            self.page_ops.wait_for(self.selectors["file_input"], timeout_ms=self.page_timeout_ms)
            flow.append("wait_for_file_input")
            self.page_ops.fill(self.selectors["file_input"], str(file_path))
            flow.append("fill_file_input")
            title = (meta or {}).get("title")
            if title:
                self.page_ops.fill(self.selectors["title_input"], str(title))
                flow.append("fill_title")
            self.page_ops.click(self.selectors["submit"])
            flow.append("click_submit")

            if self.page_ops.exists(self.selectors["error_box"]):
                text = self.page_ops.read_text(self.selectors["error_box"])
                code = self._classify_error(text)
                return self._finish_failed(
                    target_type, tid, code, base,
                    extra={
                        "error_text": text,
                        "flow": flow,
                        "manual_handoff": code == ERR_AUTH_REQUIRED,  # P-002
                        "retried": False,  # UI 兜底不自动重试，节流由编排层 item_interval 承担（P-006）
                    },
                    batch_no=batch_no,
                )

            page_id = self.page_ops.read_text(self.selectors["result_id"])
            mid = page_id or deterministic_material_id(str(file_path), meta or {})
            result = UploadResult(
                status="success",
                platform_material_id=mid,
                platform_evaluation="exploration",
                evidence={
                    **base,
                    "flow": flow,
                    "material_id_source": "page" if page_id else "deterministic",
                    "ops_calls": [dict(c) for c in getattr(self.page_ops, "calls", [])],
                },
            )
        except PageChangedError as exc:
            return self._finish_failed(
                target_type, tid, ERR_NO_MATCH, base,
                extra={**exc.evidence, "page_changed": True},
                batch_no=batch_no,
            )
        except TimeoutError:
            return self._finish_failed(
                target_type, tid, ERR_TIMEOUT, base,
                extra={
                    "timeout_selector": self.selectors["file_input"],
                    "timeout_ms": self.page_timeout_ms,
                },
                batch_no=batch_no,
            )
        except Exception as exc:  # noqa: BLE001 —— 未预期异常留证据，不静默
            return self._finish_failed(
                target_type, tid, ERR_UNEXPECTED, base,
                extra={"error": f"{type(exc).__name__}: {exc}"},
                batch_no=batch_no,
            )

        self._persist(target_type, tid, result, batch_no=batch_no)
        return result

    def _finish_failed(self, target_type, tid, error_code, base, *, extra, batch_no) -> UploadResult:
        result = UploadResult(
            status="failed",
            error_code=error_code,
            evidence={
                **base,
                **extra,
                "ops_calls": [dict(c) for c in getattr(self.page_ops, "calls", [])],
            },
        )
        self._persist(target_type, tid, result, batch_no=batch_no)
        return result
