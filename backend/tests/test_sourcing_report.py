"""REC-融合 P1-6：选品周报聚合 fixtures 测试。

旧系统 sourcing_report 迁移验证：
① 来源分布：每来源 运行/成功/失败/成功率 聚合正确
② 错误分类：AUTH_REQUIRED/RATE_LIMIT/风控 等关键词归类
③ 漏斗统计：采集事件 → 商品 → 候选 → 入池
"""

from datetime import datetime, timedelta, timezone

from sourcing.db import Database
from sourcing.report import SourcingReport, classify_error
from sourcing.tables import Product, SourceCollectionEvent, SourceRun

SINCE = datetime.now(timezone.utc) - timedelta(days=7)


def _seed_run(db: Database, source: str, ok: bool, items: int, error: str = ""):
    with db.session() as s:
        s.add(SourceRun(source=source, board="b1", item_count=items, ok=ok, error=error))
        s.commit()


def test_source_distribution(cfg, db):
    """① 来源分布聚合：成功/失败/条目/成功率。"""
    _seed_run(db, "youmi", ok=True, items=50)
    _seed_run(db, "youmi", ok=True, items=30)
    _seed_run(db, "doudian", ok=False, items=0, error="登录失效 AUTH_REQUIRED")
    rep = SourcingReport(db).weekly()
    assert rep["sources"]["youmi"]["runs"] == 2
    assert rep["sources"]["youmi"]["items"] == 80
    assert rep["sources"]["youmi"]["success_rate"] == 1.0
    assert rep["sources"]["doudian"]["failed"] == 1
    assert rep["sources"]["doudian"]["success_rate"] == 0.0


def test_error_classification():
    """② 错误分类关键词。"""
    assert classify_error("1688 登录态失效，需人工登录 AUTH_REQUIRED") == "AUTH_REQUIRED"
    assert classify_error("限流 RATE_LIMIT 频繁") == "RATE_LIMIT"
    assert classify_error("触发风控 risk_control 暂停") == "风控"
    assert classify_error("页面疑似改版 page_changed") == "PAGE_CHANGED"
    assert classify_error("未知异常 xyz") == "UNEXPECTED"


def test_error_distribution(cfg, db):
    """错误分布按类别计数。"""
    _seed_run(db, "youmi", ok=False, items=0, error="登录失效 AUTH_REQUIRED")
    _seed_run(db, "youmi", ok=False, items=0, error="登录失效，需人工登录")
    _seed_run(db, "doudian", ok=False, items=0, error="限流 RATE_LIMIT 频繁")
    rep = SourcingReport(db).weekly()
    assert rep["error_distribution"].get("AUTH_REQUIRED", 0) == 2
    assert rep["error_distribution"].get("RATE_LIMIT", 0) == 1


def test_funnel_counts(cfg, db):
    """③ 漏斗：采集事件/商品/候选/入池。"""
    with db.session() as s:
        s.add(SourceCollectionEvent(run_id=1, source="youmi", board="b", platform_item_id="x1", title="t"))
        s.add(SourceCollectionEvent(run_id=1, source="youmi", board="b", platform_item_id="x2", title="t"))
        s.commit()
    rep = SourcingReport(db).weekly()
    assert rep["funnel"]["collected_events"] == 2
    assert rep["period_days"] == 7
    assert "generated_at" in rep
