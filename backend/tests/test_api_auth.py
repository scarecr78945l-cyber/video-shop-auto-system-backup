"""API 层测试 · 鉴权闭环（test_api_auth.py）。

覆盖：登录成功（200 + Set-Cookie httpOnly/SameSite=Lax）、错误密码 401、
未登录访问业务接口 401、登出后会话失效、m0 模式表未落地明确报错。
"""

from __future__ import annotations

import secrets

import pytest

from api.auth import AuthStoreConfigError, FixturesAuthStore, M0AuthStore
from api.config import M6Config
from api.services import Services
from tests.api_testing import ADMIN_USERNAME, login, make_client, make_services, random_password


@pytest.fixture()
def client(tmp_path):
    client, services, creds, viewer_creds = make_client(tmp_path)
    with client:
        yield client, services, creds


def test_login_success_sets_http_only_cookie(client):
    c, services, creds = client
    resp = login(c, creds)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == ADMIN_USERNAME
    assert body["role"] == "admin"
    set_cookie = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie, "会话 cookie 必须 httpOnly（R-API-02）"
    assert "samesite=lax" in set_cookie.lower(), "会话 cookie 必须 SameSite=Lax"
    assert services.auth_store.session_count() > 0, "登录后应存在会话"


def test_login_wrong_password_401_error_format(client):
    c, services, creds = client
    resp = c.post(
        "/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": "wrong-" + secrets.token_urlsafe(4)},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message"}
    assert body["code"] == "AUTH_REQUIRED"


def test_login_unknown_user_401(client):
    c, services, creds = client
    resp = c.post(
        "/api/auth/login",
        json={"username": "ghost", "password": random_password()},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_REQUIRED"


def test_business_endpoint_without_login_401(client):
    c, services, creds = client
    for path in ["/api/overview", "/api/products", "/api/ads/campaigns"]:
        resp = c.get(path)
        assert resp.status_code == 401, f"{path} 未登录应 401"
        assert resp.json()["code"] == "AUTH_REQUIRED"


def test_me_after_login(client):
    c, services, creds = client
    assert login(c, creds).status_code == 200
    resp = c.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == ADMIN_USERNAME
    assert body["role"] == "admin"


def test_logout_invalidates_session(client):
    c, services, creds = client
    assert login(c, creds).status_code == 200
    assert c.get("/api/auth/me").status_code == 200
    resp = c.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # 登出后会话失效：业务接口 401
    assert c.get("/api/auth/me").status_code == 401
    assert c.get("/api/overview").status_code == 401


def test_login_validation_422_error_format(client):
    c, services, creds = client
    resp = c.post("/api/auth/login", json={"username": ""})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "detail" in body


def test_fixtures_store_no_plaintext_password_in_files():
    """fixtures 账号密码运行时随机生成：确认存储不依赖任何明文密码字面量。"""
    store = FixturesAuthStore(admin_username="admin", admin_password_hash="")
    assert store.verify_user("admin", random_password()) is None
    pwd = random_password()
    store.seed_user_plain("dev", pwd)
    user = store.verify_user("dev", pwd)
    assert user is not None and user.role == "admin"


def test_m0_mode_requires_auth_tables(tmp_path):
    """m0 模式：M0 foundation auth 表未落地 → 构造即抛明确错误（不静默降级）。"""
    from foundation.config import load_config as m0_load_config
    from foundation.db import Database

    cfg = m0_load_config(db_url=f"sqlite:///{tmp_path / 'm0-empty.db'}")
    db = Database(cfg)
    db.create_all()  # 只建共享五表，无 auth 表
    with pytest.raises(AuthStoreConfigError) as exc:
        M0AuthStore(db)
    msg = str(exc.value)
    assert "admin_users" in msg and "auth_sessions" in msg
    assert "M6_API_AUTH_MODE=m0" in msg


def test_services_auth_mode_m0_raises_clear_error(tmp_path):
    """Services 在 m0 模式下访问 auth_store → 抛 AuthStoreConfigError。"""
    from foundation.config import load_config as m0_load_config
    from foundation.db import Database

    cfg = m0_load_config(db_url=f"sqlite:///{tmp_path / 'm0-empty2.db'}")
    db = Database(cfg)
    db.create_all()
    services = Services(M6Config(api_auth_mode="m0"))
    services._dbs["m0"] = db  # 注入空 m0 库
    with pytest.raises(AuthStoreConfigError):
        _ = services.auth_store


def test_health_endpoint_is_open(client):
    c, services, creds = client
    resp = c.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["auth_mode"] == "fixtures"
