"""REC-融合 P0-3：浏览器会话管理服务 fixtures 测试。

旧系统 session_watcher 迁移验证：
① 注册来源 → 心跳探测 → logged_in
② 登录态失效（连续探测失败 ≥2）→ expired → 阻塞该来源（waiting_login）
③ 失效来源阻塞不影响其它来源（失败隔离）
④ 人工登录后 resume → 恢复可采集（断点续跑）
"""

from foundation.session_service import SessionService


def test_register_and_probe_logged_in():
    """① 注册 + 心跳探测 → logged_in。"""
    svc = SessionService()
    svc.register("youmi", cdp_port=9555, probe_fn=lambda: True)
    statuses = svc.probe_all()
    assert statuses["youmi"] == "logged_in"
    assert svc.is_ready("youmi") is True


def test_login_expiry_blocks_source():
    """② 连续 2 次探测失败 → expired → 置 waiting_login（阻塞）。"""
    svc = SessionService()
    svc.register("opportunities", cdp_port=9223, probe_fn=lambda: False)
    svc.probe_all()  # 1 次失败 → unknown
    svc.probe_all()  # 2 次失败 → expired
    assert svc.status_of("opportunities") == "expired"
    svc.block("opportunities", reason="AUTH_REQUIRED 登录失效")
    assert svc.status_of("opportunities") == "waiting_login"
    assert svc.is_ready("opportunities") is False


def test_failure_isolation_between_sources():
    """③ 失效来源阻塞不影响其它来源。"""
    svc = SessionService()
    svc.register("youmi", cdp_port=9555, probe_fn=lambda: True)
    svc.register("doudian", cdp_port=9223, probe_fn=lambda: False)
    svc.probe_all()
    svc.probe_all()  # doudian 连续 2 失败 → expired
    svc.block("doudian")
    assert svc.is_ready("doudian") is False
    assert svc.is_ready("youmi") is True  # 失败隔离


def test_resume_after_manual_login():
    """④ 人工登录后 resume → 恢复可采集（断点续跑）。"""
    svc = SessionService()
    svc.register("youmi", cdp_port=9555, probe_fn=lambda: False)
    svc.probe_all()
    svc.probe_all()
    svc.block("youmi")
    assert svc.is_ready("youmi") is False
    svc.resume("youmi")
    assert svc.is_ready("youmi") is True
    assert svc.status_of("youmi") == "logged_in"


def test_snapshot_json_redacted():
    """快照 JSON 可序列化且不含明文凭证（仅端口/状态）。"""
    svc = SessionService()
    svc.register("youmi", cdp_port=9555, probe_fn=lambda: True)
    svc.probe_all()
    snap = svc.snapshot()
    assert snap[0]["source"] == "youmi"
    assert "password" not in svc.to_json().lower()
    assert "cookie" not in svc.to_json().lower()
