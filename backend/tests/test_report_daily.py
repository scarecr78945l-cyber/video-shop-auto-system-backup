"""S4 联调度量：日有效候选 ≥200 度量测试。

覆盖：
① 跨日分组：UTC 日期聚合，daily 升序
② state 过滤：rejected 不计，pool/manual_review 计
③ 采集事件 / 运行（ok_runs）按日计数
④ 达标判定：≥200 → target_met=True 且 gap=0；不足 → False + 缺口
⑤ 空数据：daily=[] 不抛异常
⑥ CLI report-daily 冒烟（空库 / 有数据）
"""

import json
from datetime import datetime, timedelta, timezone

from click.testing import CliRunner

from sourcing.cli import cli
from sourcing.db import Database
from sourcing.report import DAILY_EFFECTIVE_TARGET, SourcingReport
from sourcing.tables import Product, SourceCollectionEvent, SourceRun

NOW = datetime.now(timezone.utc)


def _day(offset: int) -> datetime:
    """相对今天的 UTC 中午（保证落在默认 7 天窗口内，避免依赖真实时钟日期）。"""
    return (NOW - timedelta(days=offset)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )


def _seed_products(db, states, when):
    with db.session() as s:
        for i, st in enumerate(states):
            s.add(
                Product(
                    fingerprint=f"fp-{when.date().isoformat()}-{i}",
                    title=f"商品{i}",
                    state=st,
                    created_at=when,
                )
            )
        s.commit()


def _seed_runs(db, specs, when):
    """specs: [(source, ok)] → 返回 run_id 列表（供事件引用）。"""
    ids = []
    with db.session() as s:
        for source, ok in specs:
            run = SourceRun(
                source=source,
                board="b",
                item_count=1,
                ok=ok,
                started_at=when,
                error="" if ok else "RATE_LIMIT",
            )
            s.add(run)
            s.flush()
            ids.append(run.id)
        s.commit()
    return ids


def _seed_events(db, run_ids, count, when):
    with db.session() as s:
        for i in range(count):
            s.add(
                SourceCollectionEvent(
                    run_id=run_ids[i % len(run_ids)],
                    source="youmi",
                    board="b",
                    platform_item_id=f"item-{when.date().isoformat()}-{i}",
                    title="t",
                    created_at=when,
                )
            )
        s.commit()


# ---------------------------------------------------------------- ①+②+③ 跨日分组 / state 过滤 / 事件与运行计数
def test_daily_cross_day_grouping_and_state_filter(cfg, db):
    """跨日分组 + rejected 不计 + 采集事件/运行（ok_runs）按日计数。"""
    d1, d2 = _day(2), _day(1)
    _seed_products(db, ["pool", "manual_review", "rejected"], d1)
    _seed_products(db, ["pool"], d2)
    run_ids = _seed_runs(db, [("youmi", True), ("youmi", False)], d1)
    _seed_events(db, run_ids, 3, d1)
    run_ids2 = _seed_runs(db, [("doudian", True)], d2)
    _seed_events(db, run_ids2, 1, d2)

    rep = SourcingReport(db).daily_effective_candidates(days=7)
    assert rep["period_days"] == 7
    assert "generated_at" in rep
    daily = rep["daily"]
    # ① 升序、跨日两条
    assert [d["date"] for d in daily] == [
        d1.date().isoformat(),
        d2.date().isoformat(),
    ]
    # ② rejected 不计：3 条商品中只计 pool + manual_review
    first = daily[0]
    assert first["effective_candidates"] == 2
    # ③ 事件/运行按日
    assert first["collected_events"] == 3
    assert first["runs"] == 2
    assert first["ok_runs"] == 1
    second = daily[1]
    assert second["collected_events"] == 1
    assert second["runs"] == 1
    assert second["ok_runs"] == 1
    assert second["effective_candidates"] == 1


def test_products_without_state_filtered(db):
    """未知 state（如空串）同样不计入有效候选。"""
    _seed_products(db, ["pool", "", "rejected", "manual_review"], _day(1))
    daily = SourcingReport(db).daily_effective_candidates(days=7)["daily"]
    assert len(daily) == 1
    assert daily[0]["effective_candidates"] == 2


# ---------------------------------------------------------------- ④ 达标 / 不达标
def test_target_met_boundary_and_gap(db):
    """≥200 达标（恰 200 边界 + 205 超线），不足不达标且 gap 正确。"""
    d_hit, d_over, d_low = _day(3), _day(2), _day(1)
    _seed_products(db, ["pool"] * DAILY_EFFECTIVE_TARGET, d_hit)  # 恰 200 → 达标
    _seed_products(db, ["manual_review"] * (DAILY_EFFECTIVE_TARGET + 5), d_over)  # 205 → 达标
    _seed_products(db, ["pool"] * 10, d_low)  # 10 → 不达标

    daily = SourcingReport(db).daily_effective_candidates(days=7)["daily"]
    by_date = {d["date"]: d for d in daily}
    hit = by_date[d_hit.date().isoformat()]
    assert hit["effective_candidates"] == DAILY_EFFECTIVE_TARGET
    assert hit["target_met"] is True
    assert hit["gap"] == 0
    over = by_date[d_over.date().isoformat()]
    assert over["effective_candidates"] == DAILY_EFFECTIVE_TARGET + 5
    assert over["target_met"] is True
    assert over["gap"] == 0
    low = by_date[d_low.date().isoformat()]
    assert low["effective_candidates"] == 10
    assert low["target_met"] is False
    assert low["gap"] == DAILY_EFFECTIVE_TARGET - 10


# ---------------------------------------------------------------- ⑤ 空数据
def test_empty_data_no_exception(cfg, db):
    """空库：daily=[]，不抛异常，结构完整。"""
    rep = SourcingReport(db).daily_effective_candidates(days=7)
    assert rep["daily"] == []
    assert rep["period_days"] == 7
    assert "generated_at" in rep


# ---------------------------------------------------------------- ⑥ CLI 冒烟
def test_cli_report_daily_with_data(tmp_path):
    """report-daily：有数据时输出结构正确（有效候选数/达标判定）。"""
    from sourcing.config import SourcingConfig

    url = f"sqlite:///{tmp_path / 'cli.db'}"
    database = Database(SourcingConfig(db_url=url))
    database.create_all()
    _seed_products(database, ["pool", "rejected", "manual_review"], _day(1))

    runner = CliRunner()
    result = runner.invoke(cli, ["--db-url", url, "report-daily", "--days", "7"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["period_days"] == 7
    assert len(data["daily"]) == 1
    row = data["daily"][0]
    assert row["effective_candidates"] == 2
    assert row["target_met"] is False
    assert row["gap"] == DAILY_EFFECTIVE_TARGET - 2


def test_cli_report_daily_empty(tmp_path):
    """report-daily：空库输出 daily=[] 不抛异常。"""
    from sourcing.config import SourcingConfig

    url = f"sqlite:///{tmp_path / 'empty.db'}"
    database = Database(SourcingConfig(db_url=url))
    database.create_all()

    runner = CliRunner()
    result = runner.invoke(cli, ["--db-url", url, "report-daily"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["daily"] == []
