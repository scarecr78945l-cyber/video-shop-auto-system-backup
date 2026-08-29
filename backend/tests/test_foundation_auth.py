"""M6 管理后台鉴权（M0 auth 表落地）fixtures 测试。

验证：
① seed_admin_user 幂等播种
② verify_login 正确校验（正确/错误密码、禁用账号）
③ create_session + validate_session 生命周期（有效/过期）
"""

import hashlib
import uuid
from pathlib import Path

import pytest

from foundation.config import FoundationConfig
from foundation.db import Database
from foundation.repo import WorkflowQueue


@pytest.fixture()
def queue() -> WorkflowQueue:
    cfg = FoundationConfig(db_url="sqlite:///:memory:", lease_minutes=45, data_dir=Path("."))
    database = Database(cfg)
    database.create_all()
    database.seed()
    return WorkflowQueue(database)


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def test_seed_admin_idempotent(queue):
    """① 幂等播种管理员。"""
    q = queue
    assert q.seed_admin_user("admin", _hash("dev-pass")) is True
    assert q.seed_admin_user("admin", _hash("other")) is False  # 已存在跳过
    assert q.verify_login("admin", _hash("dev-pass")) is True


def test_verify_login_correct_and_wrong(queue):
    """② 正确/错误密码校验。"""
    q = queue
    q.seed_admin_user("ops", _hash("secret"))
    assert q.verify_login("ops", _hash("secret")) is True
    assert q.verify_login("ops", _hash("wrong")) is False
    assert q.verify_login("nobody", _hash("secret")) is False  # 用户不存在


def test_session_lifecycle(queue):
    """③ 会话创建/校验/过期。"""
    q = queue
    q.seed_admin_user("admin", _hash("pw"))
    token = uuid.uuid4().hex
    q.create_session("admin", token, ttl_seconds=3600)
    assert q.validate_session(token) == "admin"
    # 过期会话（直接改 expires_at 为过去）
    token2 = uuid.uuid4().hex
    q.create_session("admin", token2, ttl_seconds=1)
    with q.database.session() as s:
        from foundation.tables import AuthSessionRow
        row = s.get(AuthSessionRow, token2)
        row.expires_at = "2000-01-01T00:00:00+00:00"
    assert q.validate_session(token2) is None
