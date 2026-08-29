"""M3 上传素材库 upload · ApiUploader（mode=api，OpenAPI 假设接口 mock）。

REC-002 默认优先链路。OpenAPI 素材上传接口真实契约未实测，本实现为
fixtures/模拟：构造请求记录 + 确定性返回 ``platform_material_id``
（material_<hash8>）；``post`` 可注入测试失败路径（默认内置 mock post，
零真实网络）。

失败语义（错误码复用 WorkflowJob 表）：
- AUTH_REQUIRED：不自动重试，标记 manual_handoff 转人工（P-002）；
- RATE_LIMIT：按 ``rate_limit_backoff_seconds``（默认 180s）退避重试
  ``max_retries`` 次（sleep_fn 可注入，测试不真等）；
- TIMEOUT / PLATFORM_REJECT / UNEXPECTED：直接失败留证据，不静默。
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Optional

from .service import (
    ERR_AUTH_REQUIRED,
    ERR_RATE_LIMIT,
    ERR_UNEXPECTED,
    UploadResult,
    UploadService,
    derive_target_id,
    deterministic_material_id,
)


class UploadApiError(RuntimeError):
    """注入 post 可抛出的带错误码异常（如 UploadApiError(ERR_TIMEOUT, "超时")）。"""

    def __init__(self, error_code: str, message: str = ""):
        super().__init__(message or error_code)
        self.error_code = error_code


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ApiUploader(UploadService):
    """OpenAPI 假设接口的 mock 实现（fixtures 模式，可注入 post 测失败路径）。"""

    mode = "api"
    # 假设接口占位（真实契约待小店账号实测后替换；fixtures 不真跑网络）
    DEFAULT_ENDPOINT = "https://channels.weixin.qq.com/shop/openapi/material/upload"
    TOKEN_ENV = "M3_PLATFORM_TOKEN"  # 密钥只写环境变量名，值经 os.environ 读取

    def __init__(
        self,
        config=None,
        db=None,
        repo=None,
        *,
        post: Optional[Callable[..., dict]] = None,
        endpoint: Optional[str] = None,
        rate_limit_backoff_seconds: float = 180.0,
        max_retries: int = 1,
        timeout_seconds: float = 60.0,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ):
        super().__init__(config, db, repo)
        self.post = post or self._default_mock_post
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.rate_limit_backoff_seconds = float(rate_limit_backoff_seconds)
        self.max_retries = int(max_retries)
        self.timeout_seconds = float(timeout_seconds)
        self.sleep_fn = sleep_fn or time.sleep
        # 请求/响应留痕（证据），值经环境变量读取，不落明文
        self.request_log: list[dict[str, Any]] = []
        self.last_request: dict[str, Any] = {}
        self.last_response: dict[str, Any] = {}

    # ---------------------------------------------------------------- 双轨接口

    def upload_video(self, file_path, meta, *, target_id=None, batch_no=1, batch_id=None):
        return self._upload("video", file_path, meta, target_id=target_id, batch_no=batch_no, batch_id=batch_id)

    def upload_image(self, file_path, meta, *, target_id=None, batch_no=1, batch_id=None):
        return self._upload("image", file_path, meta, target_id=target_id, batch_no=batch_no, batch_id=batch_id)

    # ---------------------------------------------------------------- 内部

    def _upload(self, target_type, file_path, meta, *, target_id, batch_no, batch_id):
        tid = target_id or derive_target_id(meta, file_path)
        payload = self._build_payload(file_path, meta, target_type)
        headers = self._build_headers()
        request = {"endpoint": self.endpoint, "method": "POST", "payload": payload}
        self.request_log.append(request)
        self.last_request = request

        resp, attempts = self._call_with_retry(headers, payload)
        self.last_response = resp

        evidence = {
            "endpoint": self.endpoint,
            "request": request,
            "response": resp,
            "attempts": attempts,
            "retried": attempts > 1,          # RATE_LIMIT 退避重试过则 True
            "backoff_seconds": resp.get("backoff_seconds", 0.0),
        }
        if batch_id:
            evidence["batch_id"] = batch_id

        if resp.get("ok"):
            mid = str(
                resp.get("platform_material_id")
                or deterministic_material_id(str(file_path), meta or {})
            )
            evaluation = str(resp.get("platform_evaluation") or "exploring")
            result = UploadResult(
                status="success",
                platform_material_id=mid,
                platform_evaluation=evaluation,
                error_code="",
                evidence=evidence,
            )
        else:
            code = str(resp.get("error_code") or ERR_UNEXPECTED)
            result = UploadResult(
                status="failed",
                error_code=code,
                evidence={
                    **evidence,
                    "message": resp.get("message", ""),
                    "manual_handoff": code == ERR_AUTH_REQUIRED,  # P-002 不重试转人工
                    "retried": attempts > 1,
                    "backoff_seconds": resp.get("backoff_seconds", 0.0),
                },
            )
        self._persist(target_type, tid, result, batch_no=batch_no)
        return result

    def _call_with_retry(self, headers, payload) -> tuple[dict[str, Any], int]:
        """RATE_LIMIT → 退避重试（可测）；AUTH_REQUIRED/其余错误码直接失败。"""
        attempts = 0
        while True:
            attempts += 1
            resp = self._do_post(headers, payload)
            if resp.get("ok"):
                return resp, attempts
            code = str(resp.get("error_code") or ERR_UNEXPECTED)
            if code == ERR_RATE_LIMIT and attempts <= self.max_retries:
                backoff = _to_float(resp.get("retry_after")) or self.rate_limit_backoff_seconds
                resp["backoff_seconds"] = float(backoff)
                self.sleep_fn(float(backoff))
                continue
            return resp, attempts

    def _do_post(self, headers, payload) -> dict[str, Any]:
        try:
            resp = self.post(self.endpoint, payload, headers=headers, timeout=self.timeout_seconds)
            return dict(resp or {})
        except UploadApiError as exc:
            return {"ok": False, "error_code": exc.error_code, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001 —— 未预期异常留证据，不静默
            return {
                "ok": False,
                "error_code": ERR_UNEXPECTED,
                "message": f"{type(exc).__name__}: {exc}",
            }

    def _build_payload(self, file_path, meta, target_type) -> dict[str, Any]:
        meta = meta or {}
        material = {k: v for k, v in meta.items() if k not in {
            "target_id", "variant_id", "image_id", "asset_id",
        }}
        return {
            "file_path": str(file_path),
            "target_type": target_type,
            "material": material,
        }

    def _build_headers(self) -> dict[str, str]:
        """密钥只经环境变量读取（值不落日志/证据）。"""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = os.environ.get(self.TOKEN_ENV, "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _default_mock_post(self, url, payload, headers=None, timeout=None) -> dict[str, Any]:
        """内置 mock post：确定性成功（同 payload 幂等），零真实网络。"""
        return {
            "ok": True,
            "platform_material_id": deterministic_material_id(
                str(payload.get("file_path") or ""),
                dict(payload.get("material") or {}),
            ),
            "platform_evaluation": "exploring",
            "mock": True,
        }
