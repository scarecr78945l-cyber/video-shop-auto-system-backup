"""REC-融合 P0-4：来源轮换（M1 scheduler 增强）。

旧系统 services/source_rotation.py 迁移：
- 多源采集按间隔与失败状态轮换，降低单平台风控概率；
- 选源顺序按「失败计数升序 + 最近使用时间」排序（失败多的源排后/降权）；
- 单源 risk_control（连续失败 ≥ 阈值）→ 跳过该源，其余源正常采集（失败隔离）。

用法：scheduler.due_boards / run_once 用 ordered_sources() 决定扫描顺序。
"""

from __future__ import annotations

from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceRotation:
    """来源轮换调度（内存态；持久化账本/熔断仍在 SourcingScheduler）。"""

    def __init__(
        self,
        sources: list[str],
        risk_control_threshold: int = 2,
        max_consecutive_uses: int = 2,
    ) -> None:
        self.sources = list(sources)
        self.risk_control_threshold = risk_control_threshold  # 连续失败 ≥N → 降权跳过
        self.max_consecutive_uses = max_consecutive_uses  # 单源连续占用上限
        self.failures: dict[str, int] = {s: 0 for s in self.sources}
        self.consecutive_uses: dict[str, int] = {s: 0 for s in self.sources}
        self.last_used_at: dict[str, datetime] = {}

    def record_success(self, source: str) -> None:
        self.failures[source] = 0
        self.consecutive_uses[source] += 1
        self.last_used_at[source] = _utcnow()

    def record_failure(self, source: str) -> None:
        self.failures[source] = self.failures.get(source, 0) + 1
        self.consecutive_uses[source] = 0  # 失败打断连续占用
        self.last_used_at[source] = _utcnow()

    def in_risk_control(self, source: str) -> bool:
        """单源连续失败 ≥ 阈值 → 进入风控降权（跳过）。"""
        return self.failures.get(source, 0) >= self.risk_control_threshold

    def ordered_sources(self) -> list[str]:
        """轮换后的采集顺序：
        1. 剔除 risk_control 中的源（失败隔离）；
        2. 按 (失败计数升序, 连续占用升序, 最近使用升序) 排序 → 失败少/久未用者优先。
        """
        now = _utcnow()
        active = [s for s in self.sources if not self.in_risk_control(s)]
        if not active:
            return []
        return sorted(
            active,
            key=lambda s: (
                self.failures.get(s, 0),
                self.consecutive_uses.get(s, 0),
                (now - self.last_used_at[s]).total_seconds() if s in self.last_used_at else 0.0,
            ),
        )

    def next(self) -> str | None:
        """取下一个应采集的源（None=全部风控）。"""
        ordered = self.ordered_sources()
        if not ordered:
            return None
        # 连续占用超上限的源排最后（降权）
        ordered.sort(key=lambda s: self.consecutive_uses.get(s, 0))
        return ordered[0]
