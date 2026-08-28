"""选品调度器（继承半成品 SourcingScheduler 模式，进程化版本）。

机制（对齐方案文档 09 第三节）：
- 账本：每（平台,榜单）游标 / next_run_at / completed_for_date / 空转计数 / 节流级
- 节流：失败次数 → throttle 0~4 级，间隔 ×1/2/4/8/16
- 熔断：连续失败 ≥2 → risk_control 暂停整平台，探针板恢复
- 实时榜降频：连续空转 24 次，小时轮询 → 日轮询
- 静态榜：扫完当天跳过
- 独立进程运行：python -m sourcing scheduler --loop
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from .collectors import make_collector, resolve_mode
from .config import SourcingConfig
from .db import Database
from .models import BoardRunState, utcnow
from .pipeline import SourcingPipeline

log = logging.getLogger("sourcing.scheduler")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class SourcingScheduler:
    def __init__(
        self,
        config: SourcingConfig,
        db: Optional[Database] = None,
        mode: str = "fixtures",
    ):
        self.config = config
        self.db = db or Database(config)
        self.mode = mode
        self.pipeline = SourcingPipeline(config, self.db)
        self.cfg = config.scheduler

    # ------------------------------------------------------------ 账本
    def _load(self, session, source: str, board: str) -> BoardRunState:
        from . import repo

        return repo.load_board_state(session, source, board)

    def _save(self, session, state: BoardRunState) -> None:
        from . import repo

        repo.save_board_state(session, state)

    def _board_kind(self, source: str, board: str) -> str:
        spec = getattr(self.config, source)
        for b in spec.boards:
            if b.name == board:
                return b.kind
        return "static"

    def _platform_paused(self, session, source: str) -> bool:
        from . import repo

        st = repo.get_platform_state(session, source)
        if st.status == "risk_control":
            if st.paused_until is None:
                st.paused_until = utcnow() + timedelta(minutes=30)  # 兜底暂停
            if st.paused_until > utcnow():
                return True
            if self._probe(source):
                st.status = "active"
                st.consecutive_failures = 0
                st.reason = "探针恢复"
                log.info("平台 %s 探针通过，解除熔断", source)
                return False
            st.paused_until = utcnow() + timedelta(minutes=10)
            log.warning("平台 %s 探针未通过，继续熔断", source)
            return True
        if st.status in ("waiting_login", "waiting_verification"):
            return True
        return False

    def _probe(self, source: str) -> bool:
        try:
            collector = make_collector(
                source, self.config, resolve_mode(source, self.config, self.mode)
            )
            return collector.probe()
        except Exception:
            return False

    # ------------------------------------------------------------ 调度
    def due_boards(self, sources: Optional[list[str]] = None) -> list[tuple[str, str]]:
        """返回到期可执行的（source, board）。"""
        sources = sources or ["opportunities", "youmi", "doudian"]
        now = utcnow()
        today = _today()
        due: list[tuple[str, str]] = []
        with self.db.session() as session:
            for source in sources:
                if self._platform_paused(session, source):
                    continue
                collector = make_collector(
                    source, self.config, resolve_mode(source, self.config, self.mode)
                )
                for board in collector.boards:
                    st = self._load(session, source, board)
                    if st.status != "active":
                        continue
                    kind = self._board_kind(source, board)
                    if kind == "static" and st.completed_for_date == today:
                        continue  # 静态榜当天已扫，跳过
                    if st.next_run_at <= now:
                        due.append((source, board))
        return due

    def run_once(self, sources: Optional[list[str]] = None) -> dict:
        """执行一轮：所有到期的榜单各扫一次，条目进入流水线（统一去重入池）。"""
        due = self.due_boards(sources)
        stats: dict = {"due": len(due), "ok": 0, "failed": 0, "items": 0}
        if not due:
            return stats

        accumulated: list = []
        with self.db.session() as session:
            for source, board in due:
                st = self._load(session, source, board)
                kind = self._board_kind(source, board)
                failed = False
                try:
                    collector = make_collector(
                        source, self.config, resolve_mode(source, self.config, self.mode)
                    )
                    items = collector.collect_board(board, limit=self.cfg.max_items_per_run)
                    run_id = self._record_run(session, source, board, len(items), True)
                    self._record_events(session, run_id, items)
                    accumulated.extend(items)
                    stats["items"] += len(items)
                    stats["ok"] += 1
                    self._on_success(st, len(items), items[-1].platform_item_id if items else None)
                    st.completed_for_date = _today() if kind == "static" else st.completed_for_date
                except Exception as e:
                    log.warning("榜单 %s/%s 失败: %s", source, board, e)
                    self._on_failure(session, source, st, str(e))
                    stats["failed"] += 1
                    failed = True
                st.next_run_at = self._next_run_at(st, kind, failed)
                self._save(session, st)

        if accumulated:
            result = self.pipeline.run_from_items(accumulated, mode=self.mode)
            stats["candidates"] = result.candidates
            stats["pool"] = result.pool_entered
            stats["hard_rejected"] = result.hard_rejected
            stats["manual_review"] = result.manual_review
        return stats

    # ------------------------------------------------------------ 状态机
    def _on_success(self, st: BoardRunState, item_count: int, last_item_id: Optional[str] = None) -> None:
        st.consecutive_failures = 0
        st.throttle_level = 0
        st.last_error = ""
        if item_count == 0:
            st.empty_run_count += 1
        else:
            st.empty_run_count = 0
            if last_item_id:
                st.last_item_id = last_item_id

    def _on_failure(self, session, source: str, st: BoardRunState, error: str) -> None:
        from . import repo

        st.consecutive_failures += 1
        st.last_error = error[:300]
        if st.throttle_level < self.cfg.throttle_levels - 1:
            st.throttle_level += 1
        if st.consecutive_failures >= self.cfg.circuit_breaker_failures:
            st.status = "risk_control"
            ps = repo.get_platform_state(session, source)
            ps.status = "risk_control"
            ps.consecutive_failures = st.consecutive_failures
            ps.paused_until = utcnow() + timedelta(minutes=30)
            ps.reason = f"连续失败 {st.consecutive_failures} 次，熔断"
            log.warning("平台 %s 熔断（risk_control），30 分钟后探针恢复", source)

    def _interval_for(self, st: BoardRunState, board_kind: str) -> timedelta:
        """实时榜小时轮询，连续空转 24 次降日轮询；静态榜日扫。"""
        if board_kind == "static":
            return timedelta(seconds=self.cfg.static_interval_seconds)
        if st.empty_run_count >= self.cfg.empty_runs_before_downgrade:
            return timedelta(seconds=self.cfg.static_interval_seconds)
        return timedelta(seconds=self.cfg.realtime_interval_seconds)

    def _next_run_at(self, st: BoardRunState, board_kind: str, failed: bool) -> datetime:
        """下次执行时间。

        成功：按榜单正常间隔（静态日扫 / 实时小时轮询，空转降频）；
        失败：按节流退避 throttle_base × 2^throttle_level（短间隔快速重试，逐级拉长）。
        """
        if failed:
            backoff = self.cfg.throttle_base_seconds * (2 ** st.throttle_level)
            return utcnow() + timedelta(seconds=backoff)
        return utcnow() + self._interval_for(st, board_kind)

    def _record_run(self, session, source: str, board: str, n: int, ok: bool) -> int:
        from . import repo

        return repo.record_run(session, source, board, n, ok)

    def _record_events(self, session, run_id: int, items) -> None:
        from . import repo

        repo.record_events(session, run_id, items)

    # ------------------------------------------------------------ 主循环
    def loop(self, interval_seconds: float = 60.0, sources: Optional[list[str]] = None) -> None:
        """常驻调度循环（独立进程）。"""
        log.info("调度器启动（mode=%s, 轮询 %ss）", self.mode, interval_seconds)
        while True:
            try:
                stats = self.run_once(sources)
                if stats["due"]:
                    log.info("本轮完成: %s", stats)
            except Exception as e:
                log.exception("调度循环异常: %s", e)
            time.sleep(interval_seconds)
