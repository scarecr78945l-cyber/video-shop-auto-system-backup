"""M5 投放样本 fixtures 吸收测试（P2 数据吸收）。

`backend/fixtures/ads/campaign_report_sample.json` —— 投放管理列表回读样本
（08 文档后台事实锚点 + DA-001 口径：金额「元」字符串 → 分 int、时间 UTC+8 → UTC、
中文枚举 → 英文），验证「样本数据 → parse_snapshot_row → 快照入库」吸收链路。

来源说明：old-system-assets 无投放/报表样本（仅 7 个规则 JSON；旧系统 wechat_ads.py
仅有页面文本解析器 parse_campaign_metrics，无结构化报表快照可吸收），本样本按
08 文档后台事实锚点构造，后续若总控提供真实导出样本可原样替换 rows。

运行（P-001 + P-011：必须带独立 basetemp `.pytest-tmp-m5`，禁止共用 .pytest-tmp）：
  python -m pytest tests/test_ads_fixtures.py -q --basetemp=".pytest-tmp-m5"
"""

import json
from datetime import timezone
from pathlib import Path

import pytest

from ads import repo
from ads.models import ensure_aware
from ads.report import SnapshotCollector, parse_snapshot_row

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ads"


@pytest.fixture()
def db_ads(tmp_path):
    """M5 样本吸收隔离库（独立 tmp_path 临时 SQLite，不动其他模块库）。"""
    from ads.config import load_config
    from ads.db import Database

    database = Database(load_config(db_url=f"sqlite:///{tmp_path / 'ads-fixture-test.db'}"))
    database.create_all()
    return database


def _load_sample() -> dict:
    with (FIXTURE_DIR / "campaign_report_sample.json").open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- 样本文件结构
def test_fixture_file_present_and_schema():
    sample = _load_sample()
    assert sample["schema_version"] == 1
    assert sample["recorded_at"].endswith("+08:00")  # 展示层 UTC+8（DA-001）
    assert isinstance(sample["rows"], list)
    assert len(sample["rows"]) >= 4  # 覆盖 优秀/良好/1项待优化/2项待优化 + 投放中/暂停/不可投放
    for row in sample["rows"]:
        assert set(row) >= {"campaign_id", "impressions", "spend", "gmv",
                            "platform_subsidy", "diagnosis", "status"}


# ---------------------------------------------------------------- 口径吸收（元→分 / 枚举 / UTC）
def test_sample_row_money_units_and_enums():
    rows = _load_sample()["rows"]
    parsed = parse_snapshot_row({**rows[0], "recorded_at": _load_sample()["recorded_at"]})
    assert parsed["campaign_id"] == 2001          # 字符串 → int
    assert parsed["impressions"] == 12345         # "12,345" → 12345
    assert parsed["spend"] == 4560                # 45.60 元 → 4560 分
    assert parsed["gmv"] == 128800                # 1,288.00 元 → 128800 分
    assert parsed["platform_subsidy"] == 1000     # 10.00 元 → 1000 分
    assert parsed["diagnosis"] == "excellent"     # 优秀 → excellent
    assert parsed["status"] == "active"           # 投放中 → active
    assert parsed["recorded_at"].tzinfo is not None  # aware UTC


def test_sample_diagnosis_status_variants():
    rows = _load_sample()["rows"]
    expect = [
        ("1项待优化", "optimize_1"),
        ("2项待优化", "optimize_n"),
        ("良好", "good"),
    ]
    for i, (zh, en) in enumerate(expect, start=1):
        parsed = parse_snapshot_row({**rows[i], "recorded_at": _load_sample()["recorded_at"]})
        assert parsed["diagnosis"] == en, f"row {i}: {zh} → {en}"
    assert parse_snapshot_row({**rows[3], "recorded_at": _load_sample()["recorded_at"]})["status"] == "not_eligible"


# ---------------------------------------------------------------- 吸收链路（样本 → 快照入库）
def test_sample_rows_absorb_to_snapshots(db_ads):
    sample = _load_sample()
    rows = list(sample["rows"])
    recorded_at = sample["recorded_at"]
    with db_ads.session() as s:
        # 样本 campaign_id 为后台展示 id，非本库自增主键：先建 campaign 再用真实主键替换
        created = [repo.create_campaign(s, product_id=1000 + i) for i in range(len(rows))]
        assert len(created) == len(rows)
        for row, camp_id in zip(rows, created):
            row["campaign_id"] = camp_id
            row["recorded_at"] = recorded_at
        res = SnapshotCollector(s).run_once(rows)
        assert res.collected == len(rows)
        assert res.upserted == len(rows)
        assert res.errors == []
        snaps = repo.list_snapshots(s)
        assert len(snaps) == len(rows)
        for snap in snaps:
            assert isinstance(snap.spend, int) and snap.spend >= 0  # 金额分 int
            assert snap.diagnosis in {"excellent", "good", "optimize_1", "optimize_n", "unknown"}
            assert snap.status in {"active", "paused", "not_eligible", "unknown"}
            assert ensure_aware(snap.recorded_at).tzinfo is not None
            assert ensure_aware(snap.recorded_at).tzinfo is timezone.utc
