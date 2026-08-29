"""M6 后端 API 层配置（pydantic-settings，环境变量前缀 M6_）。

环境变量（只列名不列值，见 m6-frontend/context/README.md 第四节注册表）：
M6_ADMIN_USERNAME / M6_ADMIN_PASSWORD_HASH / M6_API_HOST / M6_API_PORT /
M6_API_AUTH_MODE / M6_CORS_ORIGINS / M6_SESSION_TTL_HOURS
只读消费（可覆盖各模块库连接，测试用）：M6_M0_DB_URL / M6_SOURCING_DB_URL /
M6_MATERIALS_DB_URL / M6_M3_DB_URL / M6_M4_DB_URL / M6_M5_DB_URL
密钥纪律（P-004）：本文件只存变量名与默认值，不存任何明文密钥。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AUTH_MODE_FIXTURES = "fixtures"
AUTH_MODE_M0 = "m0"


class M6Config(BaseSettings):
    """API 层总配置。"""

    model_config = SettingsConfigDict(env_prefix="M6_", env_file=".env", extra="ignore")

    # ---- 监听 ----
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # ---- 鉴权 ----
    # 密码只走环境变量：M6_ADMIN_USERNAME（默认 admin）/ M6_ADMIN_PASSWORD_HASH
    admin_username: str = "admin"
    admin_password_hash: str = ""  # 密码 SHA-256 hex；未设置时 fixtures 模式无内置账号（由部署方设置）
    api_auth_mode: str = AUTH_MODE_FIXTURES  # fixtures（内存会话+测试账号）/ m0（M0 auth 表）
    session_ttl_hours: float = 12.0  # 会话有效期（小时）
    session_cookie_name: str = "m6_session"

    # ---- CORS（逗号分隔前端 origin，默认空=仅本机）----
    cors_origins: str = ""

    # ---- 各模块库连接覆盖（只读消费；缺省回落到各模块默认库）----
    m0_db_url: str = ""
    sourcing_db_url: str = ""
    materials_db_url: str = ""
    m3_db_url: str = ""
    m4_db_url: str = ""
    m5_db_url: str = ""

    # ---- 日志 ----
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in (self.cors_origins or "").split(",") if o.strip()]

    @property
    def auth_mode_valid(self) -> bool:
        return self.api_auth_mode in (AUTH_MODE_FIXTURES, AUTH_MODE_M0)


def load_config(**overrides: Any) -> M6Config:
    """加载配置，支持关键字覆盖（测试/CLI 常用）。"""
    return M6Config(**overrides)
