"""调度器测试：账本到期、节流升级、熔断、实时榜降频。"""

from datetime import timedelta

from sourcing.config import SourcingConfig
from sourcing.db import Database
from sourcing.models import BoardRunState
from sourcing.scheduler import SourcingScheduler
from sourcing import repo


def make_scheduler(tmp_path, **cfg_overrides) -> SourcingScheduler:
    cfg = SourcingConfig(
        db_url=f"sqlite:///{tmp_path/'sched.db'}",
        fixtures_dir=__import__("pathlib").Path(__file__).parent.parent / "fixtures",
        **cfg_overrides,
    )
    db = Database(cfg)
    db.create_all()
    return SourcingScheduler(cfg, db, mode="fixtures")


def test_due_boards_initial(tmp_path):
    sch = make_scheduler(tmp_path)
    due = sch.due_boards()
    # 首次运行：三个来源全部榜单到期（fixtures 模式）
    assert len(due) >= 3
    sources = {s for s, _ in due}
    assert sources == {"opportunities", "youmi", "doudian"}


def test_run_once_updates_ledger(tmp_path):
    sch = make_scheduler(tmp_path)
    stats = sch.run_once()
    assert stats["ok"] >= 1
    assert stats["items"] > 0
    with sch.db.session() as session:
        st = repo.load_board_state(session, "opportunities", "机会品")
        assert st.consecutive_failures == 0
        assert st.throttle_level == 0
        # 静态榜完成标记当日
        assert st.completed_for_date


def test_success_sets_next_run_in_future(tmp_path):
    sch = make_scheduler(tmp_path)
    sch.run_once()
    with sch.db.session() as session:
        st = repo.load_board_state(session, "opportunities", "机会品")
        assert st.next_run_at > st.updated_at


def test_throttle_and_circuit_breaker(tmp_path):
    """连续失败 → 节流升级 → 熔断平台 risk_control。

    throttle_base_seconds=0 让失败后仍立即到期，使连续失败在单测试内累计。
    """
    sch = make_scheduler(tmp_path, scheduler={"throttle_base_seconds": 0.0})

    class Boom:
        enabled = True
        boards = ["机会品"]

        def collect_board(self, board, limit=200):
            raise RuntimeError("boom")

        def probe(self):
            return False

    # 替换采集器：全失败（scheduler 模块已把 make_collector 绑定进自身命名空间）
    import sourcing.scheduler as scheduler_mod

    original = scheduler_mod.make_collector
    scheduler_mod.make_collector = lambda source, config, mode="fixtures": Boom() if source == "opportunities" else original(source, config, mode)
    try:
        for _ in range(3):
            sch.run_once(sources=["opportunities"])
    finally:
        scheduler_mod.make_collector = original

    with sch.db.session() as session:
        st = repo.load_board_state(session, "opportunities", "机会品")
        assert st.consecutive_failures >= 2
        assert st.throttle_level >= 1
        # 平台熔断
        ps = repo.get_platform_state(session, "opportunities")
        assert ps.status == "risk_control"
    # 熔断后到期列表为空（暂停中）
    assert sch.due_boards(sources=["opportunities"]) == []


def test_realtime_downgrade_after_empty_runs(tmp_path):
    """实时榜连续空转 N 次 → 降为日轮询；有数据则重置。"""
    sch = make_scheduler(tmp_path, scheduler={"empty_runs_before_downgrade": 3})
    st = BoardRunState(source="youmi", board="实时榜")

    for _ in range(3):
        sch._on_success(st, 0, None)
    assert st.empty_run_count == 3
    # 降频：间隔升为日轮询
    assert sch._interval_for(st, "realtime").total_seconds() >= sch.cfg.static_interval_seconds

    # 有数据 → 空转计数重置，恢复小时轮询
    sch._on_success(st, 1, "item-1")
    assert st.empty_run_count == 0
    assert sch._interval_for(st, "realtime").total_seconds() == sch.cfg.realtime_interval_seconds


def test_platform_pause_blocks_boards(tmp_path):
    from datetime import datetime, timezone

    sch = make_scheduler(tmp_path)
    with sch.db.session() as session:
        ps = repo.get_platform_state(session, "youmi")
        ps.status = "risk_control"
        ps.paused_until = datetime.now(timezone.utc) + timedelta(minutes=30)
    due = sch.due_boards(sources=["youmi"])
    assert due == []
