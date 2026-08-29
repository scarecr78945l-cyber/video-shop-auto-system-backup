"""M6 后端 API 层 · 管理后台登录鉴权（AuthStore 抽象 + fixtures/m0 两种实现）。

总控裁决：会话表归属挂 M0 foundation（跨模块共享），API 层**只消费不重复建表**——
实现 `AuthStore` 抽象接口：
- `M6_API_AUTH_MODE=fixtures`（默认）：内存会话 + 测试账号（fixtures 模式，供开发/
  测试/前端 mock 联调）；内置 admin 角色；
- `M6_API_AUTH_MODE=m0`：读 M0 foundation auth 表（`admin_users` / `auth_sessions`）；
  表未落地时启动即抛 `AuthStoreConfigError`（明确错误提示，不静默降级）。

密码只走环境变量：`M6_ADMIN_USERNAME` / `M6_ADMIN_PASSWORD_HASH`（SHA-256 hex）。
会话：登录成功发 httpOnly + SameSite=Lax cookie（`M6_SESSION_COOKIE_NAME`）。
任何文件不写明文密码/token/cookie 值（宪法第 4 节，P-004）。
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text

from .errors import unauthorized


# ---------------------------------------------------------------- 工具


def sha256_hex(password: str) -> str:
    """密码 → SHA-256 hex（fixtures 模式哈希；m0 模式由 M0 侧定义校验规则）。"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    """常数时间字符串比较（防时序侧信道）。"""
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@dataclass
class AuthUser:
    """当前登录用户（响应 `{username, role}`）。"""

    username: str
    role: str = "admin"
    # 会话内部字段（不外发）
    token: str = ""

    def public(self) -> dict[str, str]:
        return {"username": self.username, "role": self.role}


# ---------------------------------------------------------------- 抽象接口


class AuthStoreConfigError(Exception):
    """AuthStore 配置错误（如 m0 模式 auth 表未落地）。"""


class AuthStore(ABC):
    """鉴权存储抽象：验证账号 / 建会话 / 查会话 / 删会话。"""

    @abstractmethod
    def verify_user(self, username: str, password: str) -> Optional[AuthUser]:
        """校验账号密码；成功返回用户（含角色），失败返回 None。"""

    @abstractmethod
    def create_session(self, user: AuthUser) -> str:
        """为已认证用户创建会话，返回会话 token。"""

    @abstractmethod
    def get_session_user(self, token: str) -> Optional[AuthUser]:
        """按 token 取会话用户；无效/过期返回 None。"""

    @abstractmethod
    def delete_session(self, token: str) -> None:
        """失效会话（登出）。"""


# ---------------------------------------------------------------- fixtures 实现


class FixturesAuthStore(AuthStore):
    """fixtures 模式：内存会话 + 测试账号（开发/测试/前端 mock 联调）。

    - 账号来源：环境变量 `M6_ADMIN_USERNAME`（默认 admin）+ `M6_ADMIN_PASSWORD_HASH`
      （SHA-256 hex）。未设置 HASH 时本存储不内置任何账号（登录返回 401 并提示设置
      环境变量）；测试可通过 `seed_user` / `seed_user_plain` 显式造号（运行时哈希，
      不落任何文件）。
    - 会话：进程内存 dict（token → 用户 + 过期时间），TTL 可配（M6_SESSION_TTL_HOURS）。
    - 内置 admin 角色：seed 的账号 role=admin（kill-switch/config 写接口仅管理员）。
    """

    def __init__(
        self,
        *,
        admin_username: str = "admin",
        admin_password_hash: str = "",
        session_ttl_hours: float = 12.0,
    ):
        self.session_ttl_seconds = float(session_ttl_hours) * 3600.0
        self._users: dict[str, dict[str, str]] = {}  # username -> {password_hash, role}
        self._sessions: dict[str, dict[str, Any]] = {}  # token -> {username, expires_at}
        self._lock = threading.Lock()
        if admin_username and admin_password_hash:
            self.seed_user(admin_username, admin_password_hash, role="admin")

    # ------------------------------------------------------------ 账号管理
    def seed_user(self, username: str, password_hash: str, role: str = "admin") -> None:
        """注入账号（幂等覆盖）。password_hash 为 SHA-256 hex。"""
        with self._lock:
            self._users[username] = {"password_hash": password_hash, "role": role}

    def seed_user_plain(self, username: str, password: str, role: str = "admin") -> None:
        """注入账号（明文密码 → 运行时哈希，测试用；不落任何文件）。"""
        self.seed_user(username, sha256_hex(password), role=role)

    # ------------------------------------------------------------ 接口实现
    def verify_user(self, username: str, password: str) -> Optional[AuthUser]:
        with self._lock:
            record = self._users.get(username)
            if record is None:
                return None
            if not constant_time_eq(record["password_hash"], sha256_hex(password)):
                return None
            return AuthUser(username=username, role=record["role"])

    def create_session(self, user: AuthUser) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = {
                "username": user.username,
                "role": user.role,
                "expires_at": time.time() + self.session_ttl_seconds,
            }
        return token

    def get_session_user(self, token: str) -> Optional[AuthUser]:
        if not token:
            return None
        with self._lock:
            record = self._sessions.get(token)
            if record is None:
                return None
            if record["expires_at"] < time.time():
                self._sessions.pop(token, None)
                return None
            return AuthUser(
                username=record["username"], role=record["role"], token=token
            )

    def delete_session(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)


# ---------------------------------------------------------------- m0 实现


class M0AuthStore(AuthStore):
    """m0 模式：读 M0 foundation auth 表（会话表挂 M0，只消费不重复建表）。

    期望 M0 落地两张表（契约待会签，见 REPORT.md 遗留项）：
    - `admin_users`：username(PK) / password_hash / role / created_at
    - `auth_sessions`：token(PK) / username / created_at / expires_at
    表未落地 → 构造时抛 `AuthStoreConfigError`（明确错误提示，不静默降级）。
    密码校验规则由 M0 侧定义（当前假定 SHA-256 hex，会签后按 M0 契约调整）。
    """

    ADMIN_USERS_TABLE = "admin_users"
    SESSIONS_TABLE = "auth_sessions"

    def __init__(self, database, session_ttl_hours: float = 12.0):
        from sqlalchemy import inspect

        self.database = database
        self.session_ttl_seconds = float(session_ttl_hours) * 3600.0
        inspector = inspect(database.engine)
        existing = set(inspector.get_table_names())
        missing = [
            t
            for t in (self.ADMIN_USERS_TABLE, self.SESSIONS_TABLE)
            if t not in existing
        ]
        if missing:
            raise AuthStoreConfigError(
                "M6_API_AUTH_MODE=m0 需要 M0 foundation 已落地 auth 表："
                + ", ".join(missing)
                + "（当前未建表；请 M0 按契约落地 admin_users/auth_sessions，"
                "或在开发期使用 M6_API_AUTH_MODE=fixtures）"
            )

    # ------------------------------------------------------------ 接口实现
    def verify_user(self, username: str, password: str) -> Optional[AuthUser]:
        with self.database.session() as session:
            row = session.execute(
                text(
                    "SELECT username, password_hash, role FROM "
                    f"{self.ADMIN_USERS_TABLE} WHERE username = :u"
                ),
                {"u": username},
            ).mappings().first()
        if row is None:
            return None
        if not constant_time_eq(str(row["password_hash"]), sha256_hex(password)):
            return None
        return AuthUser(username=username, role=str(row.get("role") or "admin"))

    def create_session(self, user: AuthUser) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self.database.session() as session:
            session.execute(
                text(
                    "INSERT INTO "
                    f"{self.SESSIONS_TABLE}(token, username, created_at, expires_at) "
                    "VALUES (:t, :u, :c, :e)"
                ),
                {
                    "t": token,
                    "u": user.username,
                    "c": now,
                    "e": now + self.session_ttl_seconds,
                },
            )
        return token

    def get_session_user(self, token: str) -> Optional[AuthUser]:
        if not token:
            return None
        with self.database.session() as session:
            row = session.execute(
                text(
                    "SELECT username, expires_at FROM "
                    f"{self.SESSIONS_TABLE} WHERE token = :t"
                ),
                {"t": token},
            ).mappings().first()
        if row is None:
            return None
        if float(row["expires_at"]) < time.time():
            self.delete_session(token)
            return None
        return AuthUser(username=str(row["username"]), role="admin", token=token)

    def delete_session(self, token: str) -> None:
        with self.database.session() as session:
            session.execute(
                text(f"DELETE FROM {self.SESSIONS_TABLE} WHERE token = :t"),
                {"t": token},
            )


# ---------------------------------------------------------------- 会话依赖


class SessionManager:
    """Cookie 会话门面：从请求 cookie 取 token → AuthStore 校验 → AuthUser。"""

    def __init__(self, store: AuthStore, cookie_name: str):
        self.store = store
        self.cookie_name = cookie_name

    def resolve(self, cookie_value: Optional[str]) -> AuthUser:
        user = self.store.get_session_user(cookie_value or "")
        if user is None:
            raise unauthorized()
        return user
