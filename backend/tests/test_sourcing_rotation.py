"""REC-融合 P0-4：来源轮换 fixtures 测试。

旧系统 source_rotation 迁移验证：
① 三源配置下调度 N 轮 → 无单源连续占用超过阈值（轮换生效）
② 单源连续失败 → 进入 risk_control → 其余源正常采集（失败隔离）
③ 失败源恢复后重新参与轮换
"""

from sourcing.source_rotation import SourceRotation


def test_rotation_prevents_monopoly():
    """① 三源多轮 → 无单源连续占用超过 max_consecutive_uses。"""
    rot = SourceRotation(["youmi", "opportunities", "doudian"], max_consecutive_uses=2)
    for _ in range(6):
        src = rot.next()
        assert src is not None
        rot.record_success(src)
        # 连续占用不超过阈值
        assert rot.consecutive_uses[src] <= 2


def test_risk_control_isolates_failed_source():
    """② 单源连续失败 → risk_control 跳过，其余源正常。"""
    rot = SourceRotation(["youmi", "opportunities", "doudian"], risk_control_threshold=2)
    rot.record_failure("youmi")
    rot.record_failure("youmi")  # 触发 risk_control
    assert rot.in_risk_control("youmi") is True
    ordered = rot.ordered_sources()
    assert "youmi" not in ordered
    assert set(ordered) == {"opportunities", "doudian"}
    # 连续取下一个不返回风控源
    assert rot.next() in ("opportunities", "doudian")


def test_all_sources_risk_controlled_returns_none():
    """全部源风控 → next 返回 None（不采集，等恢复）。"""
    rot = SourceRotation(["youmi", "doudian"], risk_control_threshold=1)
    rot.record_failure("youmi")
    rot.record_failure("doudian")
    assert rot.next() is None


def test_recovery_after_success():
    """③ 失败源成功一次后退出 risk_control，重新参与轮换。"""
    rot = SourceRotation(["youmi", "doudian"], risk_control_threshold=2)
    rot.record_failure("youmi")
    rot.record_failure("youmi")
    assert rot.in_risk_control("youmi") is True
    rot.record_success("youmi")  # 恢复
    assert rot.in_risk_control("youmi") is False
    assert "youmi" in rot.ordered_sources()


def test_failure_weight_prioritizes_healthy_source():
    """失败计数低的源优先（降权语义）。"""
    rot = SourceRotation(["youmi", "opportunities", "doudian"], risk_control_threshold=5)
    rot.record_failure("doudian")
    rot.record_failure("doudian")
    rot.record_failure("opportunities")
    ordered = rot.ordered_sources()
    assert ordered[0] == "youmi"  # 零失败者优先
    assert ordered[-1] == "doudian"  # 失败最多者最后
