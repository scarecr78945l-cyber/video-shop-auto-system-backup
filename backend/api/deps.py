"""M6 后端 API 层 · 依赖注入（deps）。

- `get_services`：取 app.state.services（服务容器）；
- `get_current_user`：从 httpOnly cookie 解析会话 → AuthUser（未登录 401）；
- `require_admin`：管理员角色校验（403）；
- `pagination`：统一分页参数（page/page_size，1 起，上限 100）。
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Query, Request

from .auth import AuthUser
from .errors import forbidden
from .services import Services

SERVICES_STATE_KEY = "services"


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_current_user(
    request: Request, services: Services = Depends(get_services)
) -> AuthUser:
    """会话依赖：从 cookie 取 token → AuthStore 校验（未登录/失效 → 401）。"""
    cookie_name = services.settings.session_cookie_name
    token = request.cookies.get(cookie_name)
    return services.auth_store.get_session_user(token) or _raise_unauthorized()


def _raise_unauthorized() -> AuthUser:
    from .errors import unauthorized

    raise unauthorized()


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """管理员角色守卫：kill-switch / app-config 写接口仅管理员（R-API-05）。"""
    if user.role != "admin":
        raise forbidden("需要管理员权限")
    return user


def pagination(
    page: int = Query(1, ge=1, description="页码（1 起）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（≤100）"),
):
    return {"page": page, "page_size": page_size}


def optional_str(value: Optional[str] = None) -> Optional[str]:
    """可选字符串参数（空串 → None）。"""
    if value is None or value == "":
        return None
    return value
