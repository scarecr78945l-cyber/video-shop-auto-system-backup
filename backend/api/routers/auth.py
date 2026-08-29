"""鉴权路由：登录 / 登出 / 当前用户（/api/auth/*）。

- POST /api/auth/login：唯一免登录端点；成功设 httpOnly + SameSite=Lax 会话 cookie；
- POST /api/auth/logout：失效会话并清 cookie；
- GET /api/auth/me：当前用户/权限（前端路由守卫用，R-API-04）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from ..auth import AuthUser
from ..deps import get_current_user, get_services
from ..errors import ApiError
from ..schemas import LoginBody, LoginResponse, MeResponse
from ..services import Services

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, services: Services, token: str) -> None:
    """设置会话 cookie：httpOnly + SameSite=Lax（R-API-02：防 CSRF/XSS 窃取）。"""
    response.set_cookie(
        key=services.settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=int(services.settings.session_ttl_hours * 3600),
    )


def _clear_session_cookie(response: Response, services: Services) -> None:
    response.delete_cookie(key=services.settings.session_cookie_name, path="/")


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginBody,
    response: Response,
    services: Services = Depends(get_services),
) -> dict:
    """管理后台登录：成功发 httpOnly 会话 cookie（fixtures/m0 双模式）。"""
    store = services.auth_store
    user = store.verify_user(body.username, body.password)
    if user is None:
        raise ApiError(
            status_code=401,
            code="AUTH_REQUIRED",
            message="用户名或密码错误",
        )
    token = store.create_session(user)
    _set_session_cookie(response, services, token)
    services.audit(
        event="auth.login",
        message=f"用户登录成功: {body.username}",
        evidence={"username": body.username},
        operator=body.username,
    )
    return user.public()


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    user: AuthUser = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> dict:
    """登出：失效会话并清 cookie。"""
    token = request.cookies.get(services.settings.session_cookie_name)
    if token:
        services.auth_store.delete_session(token)
    _clear_session_cookie(response, services)
    return {"ok": True, "message": "已登出"}


@router.get("/me", response_model=MeResponse)
def me(user: AuthUser = Depends(get_current_user)) -> dict:
    """当前用户/权限（前端路由守卫用）。"""
    return user.public()
