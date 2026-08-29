"""M6 后端 API 层 · 统一错误与辅助工具。

错误格式铁律（总控裁决）：业务失败统一 `{code, message, detail?}`。
- 业务错误 code 复用 DA-008 码表：VERIFICATION_REQUIRED / AUTH_REQUIRED /
  RATE_LIMIT / TIMEOUT / NO_MATCH / PLATFORM_REJECT / UNEXPECTED；
- API 层局部扩展两个非业务码（供前端直接展示 message，REPORT.md 已登记待会签）：
  VALIDATION_ERROR（HTTP 422，请求校验失败）/ INVALID_STATE（HTTP 409，状态冲突）；
- HTTP 语义：401（未登录/会话失效）→ AUTH_REQUIRED；403（权限不足）→ AUTH_REQUIRED；
  404（资源不存在）→ NO_MATCH。

金额口径（DA-001 总控裁决）：API 对外一律「元（float）」——内部存储分不变，
API 层 ÷100（round 2 位）换算；M1 商品池元字段直接透传。禁止把分输出给前端。
时间口径：ISO8601 UTC（`...Z`），字段名 `*_at` 后缀。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from foundation.security import redact_text, redact_url

# ---------------------------------------------------------------- 错误模型

# DA-008 业务错误码（唯一权威，复用 09 文档码表）
BUSINESS_ERROR_CODES = (
    "VERIFICATION_REQUIRED",
    "AUTH_REQUIRED",
    "RATE_LIMIT",
    "TIMEOUT",
    "NO_MATCH",
    "PLATFORM_REJECT",
    "UNEXPECTED",
)

# API 层局部扩展码（非业务码，前端直接展示 message）
CODE_VALIDATION_ERROR = "VALIDATION_ERROR"
CODE_INVALID_STATE = "INVALID_STATE"


class ApiError(Exception):
    """API 业务错误：带 HTTP 状态码 + DA-008 码 + 消息 + 可选详情。"""

    def __init__(
        self,
        status_code: int = 400,
        code: str = "UNEXPECTED",
        message: str = "",
        detail: Any = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail is not None:
            body["detail"] = self.detail
        return body


def not_found(message: str = "资源不存在") -> ApiError:
    return ApiError(status_code=404, code="NO_MATCH", message=message)


def unauthorized(message: str = "未登录或会话已失效") -> ApiError:
    return ApiError(status_code=401, code="AUTH_REQUIRED", message=message)


def forbidden(message: str = "权限不足") -> ApiError:
    return ApiError(status_code=403, code="AUTH_REQUIRED", message=message)


def invalid_state(message: str) -> ApiError:
    return ApiError(status_code=409, code=CODE_INVALID_STATE, message=message)


# ---------------------------------------------------------------- 注册处理器


def register_error_handlers(app: FastAPI) -> None:
    """注册统一错误处理器：ApiError / 校验错误 / HTTP 异常 / 兜底 500。"""

    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.payload())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        detail = exc.errors()
        return JSONResponse(
            status_code=422,
            content={
                "code": CODE_VALIDATION_ERROR,
                "message": "请求参数校验失败",
                "detail": detail,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "AUTH_REQUIRED" if exc.status_code == 401 else "UNEXPECTED"
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": str(exc.detail)},
        )

    @app.exception_handler(Exception)
    async def _unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        # 兜底：不把堆栈/内部细节抛给前端（R-SEC-05），仅日志留痕
        return JSONResponse(
            status_code=500,
            content={
                "code": "UNEXPECTED",
                "message": "服务内部错误",
                "detail": f"{type(exc).__name__}: {redact_text(str(exc))}",
            },
        )


# ---------------------------------------------------------------- 金额/时间换算


def cents_to_yuan(cents: Any) -> float | None:
    """分 → 元（round 2 位）。None/空 → None。禁止把分输出给前端（DA-001）。"""
    if cents is None:
        return None
    try:
        return round(float(cents) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_z(value: Any) -> str | None:
    """任意时间值 → ISO8601 UTC（`...Z`）；解析失败原样返回字符串。"""
    dt = _parse_dt(value)
    if dt is not None:
        return dt.isoformat().replace("+00:00", "Z")
    if value is None:
        return None
    return str(value)


# ---------------------------------------------------------------- 脱敏工具


def redact_value(value: Any, max_len: int = 300) -> Any:
    """递归脱敏 dict/list/str（URL 敏感参数→***、疑似密钥键值→***、截断）。

    任何 evidence / 原始 JSON 输出前必须经本函数（宪法第 8 节第 5 条，P-004）。
    """
    if isinstance(value, dict):
        return {str(k): redact_value(v, max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v, max_len) for v in value]
    if isinstance(value, str):
        return redact_text(value, max_len=max_len)
    return value


def redact_urls_in(value: Any, max_len: int = 300) -> Any:
    """递归脱敏，仅对 URL 字符串做敏感参数掩码（保留路径/非敏感文本原样）。"""
    if isinstance(value, dict):
        return {str(k): redact_urls_in(v, max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_urls_in(v, max_len) for v in value]
    if isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://"):
            return redact_url(value)
        return value
    return value


def json_safe(value: Any) -> Any:
    """把可能为 JSON 文本的字段解析为 dict/list；解析失败原样返回。"""
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def as_list(value: Any) -> list:
    """JSON 字段 → list（兼容 None / 非法）。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []
    return []
