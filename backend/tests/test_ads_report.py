"""M5 自动小店投放（商品托管）· 监控回读测试（v0.4 监控层第一部分）。

覆盖：诊断/状态枚举归一化、金额解析（str 元→分 / 数值按分直取）、快照行解析
（字段映射/默认值/recorded_at）、SnapshotCollector.run_once（正常入库/幂等/单行
错误隔离/空列表）、collect_missing（已存在跳过/缺失补齐/since 过滤/campaign 过滤/
无数据源）、next_run_hint（UTC 建议时间 + config 默认间隔）。

fixtures 全部在测试文件内自建（独立 tmp_path 临时库，只追加不动 conftest）。

运行（P-001 + P-011：必须带独立 basetemp `.pytest-tmp-m5`，禁止共用 .pytest-tmp）：
  python -m pytest tests/test_ads_report.py -q --basetemp=".pytest-tmp-m5"
"""

from datetime import datetime, timedelta, timezone

import pytest

import ads.report as report_mod
from ads import repo
from ads.models import ensure_aware, utcnow
from ads.report import (
    CollectResult,
    SnapshotCollector,
    next_run_hint,
    normalize_diagnosis,
    normalize_status,
    parse_amount_fen,
    parse_snapshot_row,
)


@pytest.fixture()
def db_report(tmp_path):
    """M5 监控回读隔离库（独立 tmp_path 临时 SQLite，不动其他模块库）。"""
    from ads.config import load_config
    from ads.db import Database

    database = Database(load_config(db_url=f"sqlite:///{tmp_path / 'report-test.db'}"))
    database.create_all()
    return database


# ---------------------------------------------------------------- 测试工具
def _new_campaign(db, product_id=101, **over):
    with db.session() as s:
        return repo.create_campaign(s, product_id=product_id, **over)


def _row(campaign_id, recorded_at=None, **over):
    """构造一行原始投放列表 dict（fixtures 模拟后台表格行）。"""
    row = {
        "campaign_id": campaign_id,
        "impressions": 100,
        "spend": "12.34",
        "gmv": "1,234.56",
        "platform_subsidy": "5.00",
        "diagnosis": "优秀",
        "status": "投放中",
    }
    if recorded_at is not None:
        row["recorded_at"] = recorded_at
    row.update(over)
    return row


# ---------------------------------------------------------------- normalize_diagnosis
def test_normalize_diagnosis_exact():
    assert normalize_diagnosis("优秀") == "excellent"
    assert normalize_diagnosis("良好") == "good"
    assert normalize_diagnosis("1项待优化") == "optimize_1"
    assert normalize_diagnosis("2项待优化") == "optimize_n"
    assert normalize_diagnosis("12项待优化") == "optimize_n"


def test_normalize_diagnosis_unknown():
    assert normalize_diagnosis(None) == "unknown"
    assert normalize_diagnosis("") == "unknown"
    assert normalize_diagnosis("   ") == "unknown"
    assert normalize_diagnosis("未知诊断") == "unknown"
    assert normalize_diagnosis("0项待优化") == "unknown"  # N==0 无对应枚举
    assert normalize_diagnosis("excellent") == "unknown"  # 已是英文不识别


def test_normalize_diagnosis_strip_tolerant():
    assert normalize_diagnosis("  优秀  ") == "excellent"
    assert normalize_diagnosis(" 良好\t") == "good"
    assert normalize_diagnosis(" 1项待优化 ") == "optimize_1"
    assert normalize_diagnosis("2 项待优化") == "optimize_n"  # 数字与「项」间空白容忍


# ---------------------------------------------------------------- normalize_status
def test_normalize_status_enum():
    assert normalize_status("投放中") == "active"
    assert normalize_status("暂停投放") == "paused"
    assert normalize_status("已暂停") == "paused"
    assert normalize_status("暂停") == "paused"
    assert normalize_status("暂停（投放）") == "paused"
    assert normalize_status("不可投放") == "not_eligible"
    assert normalize_status("待托管") == "pending"
    assert normalize_status("已结束") == "ended"


def test_normalize_status_unknown():
    assert normalize_status(None) == "unknown"
    assert normalize_status("") == "unknown"
    assert normalize_status("  ") == "unknown"
    assert normalize_status("奇怪状态") == "unknown"
    assert normalize_status("active") == "unknown"


def test_normalize_status_strip():
    assert normalize_status(" 投放中 ") == "active"
    assert normalize_status("  已暂停  ") == "paused"


# ---------------------------------------------------------------- parse_amount_fen
def test_parse_amount_fen_yuan_string():
    assert parse_amount_fen("12.34") == 1234  # 元 → 分 ×100
    assert parse_amount_fen("1234") == 123400  # 字符串一律按元（非分）
    assert parse_amount_fen("100") == 10000
    assert parse_amount_fen("0") == 0
    assert parse_amount_fen(" 5.50 ") == 550  # 空白容忍


def test_parse_amount_fen_thousands():
    assert parse_amount_fen("1,234.56") == 123456
    assert parse_amount_fen("1,000") == 100000
    assert parse_amount_fen("12,345.67") == 1234567


def test_parse_amount_fen_numeric_as_fen():
    assert parse_amount_fen(1234) == 1234  # int 按分直取
    assert parse_amount_fen(12.9) == 12  # float 按分截断取整
    assert parse_amount_fen(0) == 0


def test_parse_amount_fen_invalid_default():
    assert parse_amount_fen(None) == 0
    assert parse_amount_fen("") == 0
    assert parse_amount_fen("abc") == 0
    assert parse_amount_fen("12.34.56") == 0  # 多余小数点 → 非法
    assert parse_amount_fen(True) == 0  # bool 按非法
    assert parse_amount_fen(None, 5) == 5  # 自定义默认
    assert parse_amount_fen("oops", 99) == 99


# ---------------------------------------------------------------- parse_snapshot_row
def test_parse_snapshot_row_full_mapping():
    raw = {
        "campaign_id": "101",
        "impressions": "1,234",
        "spend": "12.34",
        "gmv": "1,234.56",
        "platform_subsidy": "5.00",
        "diagnosis": "优秀",
        "status": "投放中",
        "recorded_at": "2025-01-01T08:00:00+08:00",
    }
    parsed = parse_snapshot_row(raw)
    assert parsed["campaign_id"] == 101  # 字符串 → int
    assert parsed["impressions"] == 1234
    assert parsed["spend"] == 1234  # 元 → 分
    assert parsed["gmv"] == 123456
    assert parsed["platform_subsidy"] == 500
    assert parsed["diagnosis"] == "excellent"  # 中文 → 英文枚举
    assert parsed["status"] == "active"
    assert parsed["recorded_at"] == datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)  # +08:00 → UTC
    assert parsed["raw_json"] == raw  # 原始行副本保留


def test_parse_snapshot_row_missing_fields_defaults():
    parsed = parse_snapshot_row({"campaign_id": 7})
    assert parsed["campaign_id"] == 7
    assert parsed["impressions"] == 0
    assert parsed["spend"] == 0
    assert parsed["gmv"] == 0
    assert parsed["platform_subsidy"] == 0
    assert parsed["diagnosis"] == "unknown"
    assert parsed["status"] == "unknown"
    assert "raw_json" in parsed


def test_parse_snapshot_row_recorded_at_variants():
    # 带偏移字符串 → 转 UTC
    parsed = parse_snapshot_row(_row(1, recorded_at="2025-01-01T08:00:00+08:00"))
    assert parsed["recorded_at"] == datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    # naive 字符串视为 UTC
    parsed2 = parse_snapshot_row(_row(1, recorded_at="2025-01-01T08:00:00"))
    assert parsed2["recorded_at"] == datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc)
    # Z 后缀（ISO8601 UTC）
    parsed3 = parse_snapshot_row(_row(1, recorded_at="2025-01-01T08:00:00Z"))
    assert parsed3["recorded_at"] == datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc)
    # datetime 输入：naive 补 UTC
    parsed4 = parse_snapshot_row(_row(1, recorded_at=datetime(2025, 1, 1, 8, 0)))
    assert parsed4["recorded_at"] == datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc)
    # 缺省 → 当前 UTC（带时区；recorded_at 于解析时取 now，与断言时刻应接近）
    parsed5 = parse_snapshot_row(_row(1))
    assert parsed5["recorded_at"].tzinfo is not None
    assert abs((parsed5["recorded_at"] - utcnow()).total_seconds()) < 60


def test_parse_snapshot_row_invalid_raises():
    with pytest.raises(ValueError, match="campaign_id"):
        parse_snapshot_row({})  # campaign_id 缺失
    with pytest.raises(ValueError, match="campaign_id"):
        parse_snapshot_row({"campaign_id": "abc"})  # 非法 id
    with pytest.raises(ValueError, match="recorded_at"):
        parse_snapshot_row(_row(1, recorded_at="not-a-date"))
    with pytest.raises(ValueError, match="recorded_at"):
        parse_snapshot_row(_row(1, recorded_at=""))
    with pytest.raises(ValueError, match="dict"):
        parse_snapshot_row(None)
    with pytest.raises(ValueError, match="dict"):
        parse_snapshot_row("row")


# ---------------------------------------------------------------- run_once
def test_run_once_inserts_rows(db_report):
    cid = _new_campaign(db_report)
    t0 = utcnow()
    rows = [
        _row(cid, recorded_at=t0, impressions=100, spend="10.00", gmv="200.00",
             platform_subsidy="3.50", diagnosis="良好", status="投放中"),
        _row(cid, recorded_at=t0 + timedelta(minutes=5), impressions=200, spend="20.00",
             gmv="400.00", diagnosis="1项待优化", status="暂停投放"),
    ]
    with db_report.session() as s:
        res = SnapshotCollector(s).run_once(rows)
        assert isinstance(res, CollectResult)
        assert res.collected == 2
        assert res.upserted == 2
        assert res.skipped == 0
        assert res.errors == []
        snaps = repo.list_snapshots(s, campaign_id=cid)
        assert len(snaps) == 2
        snap = snaps[0]
        assert snap.campaign_id == cid
        assert snap.impressions == 100
        assert snap.spend == 1000  # 元 → 分
        assert snap.gmv == 20000
        assert snap.platform_subsidy == 350
        assert snap.diagnosis == "good"
        assert snap.status == "active"
        assert ensure_aware(snap.recorded_at) == t0


def test_run_once_idempotent_same_period(db_report):
    """同 (campaign_id, recorded_at) 两次 run 仍 1 行，且值更新为最新（幂等）。"""
    cid = _new_campaign(db_report)
    t = utcnow()
    with db_report.session() as s:
        col = SnapshotCollector(s)
        r1 = col.run_once([_row(cid, recorded_at=t, impressions=100, spend="1.00")])
        assert r1.upserted == 1
        # 同周期重跑：更新不新增
        r2 = col.run_once([_row(cid, recorded_at=t, impressions=200, spend="9.99")])
        assert r2.upserted == 1
        snaps = repo.list_snapshots(s, campaign_id=cid)
        assert len(snaps) == 1  # 幂等：仍 1 行
        assert snaps[0].impressions == 200
        assert snaps[0].spend == 999


def test_run_once_error_isolation(db_report):
    """单行解析失败（campaign_id 缺失）→ 记 errors 继续，其余行成功入库。"""
    cid = _new_campaign(db_report)
    t0 = utcnow()
    rows = [
        _row(cid, recorded_at=t0),
        {"impressions": 1},  # campaign_id 缺失 → 失败行
        _row(cid, recorded_at=t0 + timedelta(minutes=5)),
    ]
    with db_report.session() as s:
        res = SnapshotCollector(s).run_once(rows)
        assert res.collected == 2
        assert res.upserted == 2
        assert len(res.errors) == 1
        err = res.errors[0]
        assert err["row"] == 2  # 行号（1 起）
        assert "campaign_id" in err["reason"]
        assert "raw" in err  # 脱敏原始行
        assert repo.list_snapshots(s, campaign_id=cid)  # 其余成功入库


def test_run_once_upsert_failure_isolated(db_report, monkeypatch):
    """入库层失败（模拟 DB 异常）→ 记 errors 不整批崩（每行独立 savepoint 回滚）。"""
    cid = _new_campaign(db_report)
    t0 = utcnow()
    rows = [
        _row(cid, recorded_at=t0),
        _row(99999, recorded_at=t0 + timedelta(minutes=1)),  # 不存在的 campaign → 注入失败
        _row(cid, recorded_at=t0 + timedelta(minutes=2)),
    ]
    real = report_mod.repo.upsert_snapshot

    def fake_upsert(session, **kw):
        if kw["campaign_id"] == 99999:
            raise RuntimeError("boom: 入库失败模拟")
        return real(session, **kw)

    monkeypatch.setattr(report_mod.repo, "upsert_snapshot", fake_upsert)
    with db_report.session() as s:
        res = SnapshotCollector(s).run_once(rows)
        assert res.collected == 2
        assert res.upserted == 2
        assert len(res.errors) == 1
        assert res.errors[0]["row"] == 2
        assert "boom" in res.errors[0]["reason"]
        assert len(repo.list_snapshots(s, campaign_id=cid)) == 2  # 其余成功


def test_run_once_empty_rows(db_report):
    with db_report.session() as s:
        res = SnapshotCollector(s).run_once([])
        assert res.collected == 0
        assert res.upserted == 0
        assert res.skipped == 0
        assert res.errors == []
        assert repo.list_snapshots(s) == []


# ---------------------------------------------------------------- collect_missing
def test_collect_missing_skip_existing_fill_missing(db_report):
    cid = _new_campaign(db_report)
    t1 = utcnow() - timedelta(minutes=30)
    t2 = utcnow()
    with db_report.session() as s:  # 预置 t1 快照
        repo.upsert_snapshot(s, campaign_id=cid, recorded_at=t1, spend=100)
    rows = [_row(cid, recorded_at=t1), _row(cid, recorded_at=t2)]
    with db_report.session() as s:
        res = SnapshotCollector(s).collect_missing([cid], rows=rows)
        assert res.collected == 2
        assert res.skipped == 1  # t1 已存在 → skipped
        assert res.upserted == 1  # t2 缺失 → 补齐
        assert res.errors == []
        assert len(repo.list_snapshots(s, campaign_id=cid)) == 2


def test_collect_missing_since_filter(db_report):
    cid = _new_campaign(db_report)
    t1 = utcnow() - timedelta(hours=2)  # since 之前 → 排除
    t2 = utcnow() - timedelta(hours=1)
    t3 = utcnow()
    since = utcnow() - timedelta(hours=1, minutes=30)
    rows = [_row(cid, recorded_at=t1), _row(cid, recorded_at=t2), _row(cid, recorded_at=t3)]
    with db_report.session() as s:
        res = SnapshotCollector(s).collect_missing([cid], since=since, rows=rows)
        assert res.collected == 2  # 仅 t2/t3
        assert res.upserted == 2
        assert res.skipped == 0
        snaps = repo.list_snapshots(s, campaign_id=cid)
        assert len(snaps) == 2
        assert all(ensure_aware(sn.recorded_at) >= since for sn in snaps)


def test_collect_missing_campaign_filter_and_no_rows(db_report):
    c1 = _new_campaign(db_report, product_id=1)
    c2 = _new_campaign(db_report, product_id=2)
    rows = [_row(c1, recorded_at=utcnow()), _row(c2, recorded_at=utcnow())]
    with db_report.session() as s:
        # 只处理指定 campaign：c2 的行整体排除
        res = SnapshotCollector(s).collect_missing([c1], rows=rows)
        assert res.collected == 1
        assert res.upserted == 1
        assert res.skipped == 0
        assert [sn.campaign_id for sn in repo.list_snapshots(s)] == [c1]
    with db_report.session() as s:
        # 无数据源（rows=None）：纯数据驱动层无事可做，返回空结果不报错
        res = SnapshotCollector(s).collect_missing([c1])
        assert res.collected == 0
        assert res.upserted == 0
        assert res.skipped == 0
        assert res.errors == []


def test_collect_missing_same_batch_dedup(db_report):
    """批内同 (campaign_id, recorded_at) 重复行：仅首次 upsert，后续 skipped。"""
    cid = _new_campaign(db_report)
    t = utcnow()
    rows = [_row(cid, recorded_at=t), _row(cid, recorded_at=t)]
    with db_report.session() as s:
        res = SnapshotCollector(s).collect_missing([cid], rows=rows)
        assert res.collected == 2
        assert res.upserted == 1
        assert res.skipped == 1
        assert len(repo.list_snapshots(s, campaign_id=cid)) == 1


# ---------------------------------------------------------------- next_run_hint
def test_next_run_hint():
    base = datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc)
    assert next_run_hint(1800, last_run_at=base) == datetime(2025, 1, 1, 8, 30, tzinfo=timezone.utc)
    # 无 last_run_at → 基于当前 UTC（aware）
    h = next_run_hint(1800)
    assert h.tzinfo is not None
    assert 1799 <= (h - utcnow()).total_seconds() <= 1800
    # 类静态方法入口同口径
    h2 = SnapshotCollector.next_run_hint(60, last_run_at=base)
    assert h2 == datetime(2025, 1, 1, 8, 1, tzinfo=timezone.utc)
    # interval 缺省 → 读 config.report_interval_s（只读默认值，不修改配置）
    h3 = SnapshotCollector.next_run_hint()
    assert h3.tzinfo is not None
    assert (h3 - utcnow()).total_seconds() > 0
