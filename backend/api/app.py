"""M6 后端 API 层 · FastAPI 应用工厂（app）。

- `create_app(settings=None, services=None)`：可注入 Services（测试用 tmp 库）；
- 中间件：请求日志（脱敏）、CORS 白名单（M6_CORS_ORIGINS，默认空=仅本机）；
- 错误处理器：统一 `{code, message, detail?}`（见 errors.py）；
- 鉴权：除 POST /api/auth/login 外全部端点需登录（会话 cookie httpOnly，
  AuthStore fixtures/m0 双模式，见 auth.py）。
启动：`python -m api`（backend/ 目录）或 `uvicorn api.app:app --port 8000`。
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import M6Config, load_config
from .errors import register_error_handlers, redact_text
from .routers import auth as router_auth
from .routers import m1_sourcing, m2_materials, m3_optimization, m4_listing, m5_ads
from .routers import system as router_system
from .routers import workbench
from .services import Services

logger = logging.getLogger("api")

APP_TITLE = "视频号小店全自动系统 · 管理控制台 API"
APP_VERSION = "0.1.0"


def create_app(
    settings: Optional[M6Config] = None,
    services: Optional[Services] = None,
) -> FastAPI:
    """应用工厂：构建 FastAPI 实例并注册路由/中间件/错误处理器。

    services 缺省时按 settings（M6_* 环境变量）惰性构建模块库连接。
    """
    settings = settings or load_config()
    if not settings.auth_mode_valid:
        raise ValueError(
            f"M6_API_AUTH_MODE 非法: {settings.api_auth_mode!r}（可选 fixtures/m0）"
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = services if services is not None else Services(settings)
        app.state.services = svc
        # 提前触发 auth store 构造：m0 模式表未落地 → 启动即报明确错误（不静默降级）
        _ = svc.auth_store
        yield

    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # ---- CORS：白名单收口（R-API-02 / R-SEC-04），credentials 精确匹配 ----
    origins = settings.cors_origin_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # ---- 请求日志中间件（路径/状态码；不打印请求体/响应体敏感内容）----
    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            redact_text(request.url.path, 200),
            response.status_code,
            elapsed_ms,
        )
        return response

    # ---- 鉴权守卫（总控裁决：除 POST /api/auth/login 外全部端点需登录）----
    # 中间件级兜底 + 路由级依赖双保险（R-API-01：鉴权仅作用于 HTTP 路由层，
    # 各模块 CLI/repo 内部调用不受影响）。
    @app.middleware("http")
    async def auth_guard(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS":  # CORS 预检不鉴权
            return await call_next(request)
        if (
            path == "/api/auth/login"
            or path == "/api/health"
            or path.startswith("/api/docs")
            or path.startswith("/api/openapi.json")
            or path.startswith("/docs")
            or path.startswith("/redoc")
        ):
            return await call_next(request)
        token = request.cookies.get(settings.session_cookie_name)
        svc = request.app.state.services
        user = svc.auth_store.get_session_user(token or "")
        if user is None:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"code": "AUTH_REQUIRED", "message": "未登录或会话已失效"},
            )
        request.state.user = user
        return await call_next(request)

    # ---- 统一错误处理器 ----
    register_error_handlers(app)

    # ---- 路由注册 ----
    app.include_router(router_auth.router)
    app.include_router(router_system.router)
    app.include_router(m1_sourcing.router)
    app.include_router(m2_materials.router)
    app.include_router(m3_optimization.router)
    app.include_router(m4_listing.router)
    app.include_router(m5_ads.router)
    app.include_router(workbench.router)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        """健康检查（免登录）：服务与鉴权模式状态。"""
        return {
            "ok": True,
            "service": APP_TITLE,
            "version": APP_VERSION,
            "auth_mode": settings.api_auth_mode,
        }

    return app


app = create_app()
