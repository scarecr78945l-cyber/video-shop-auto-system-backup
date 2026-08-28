"""M5 自动小店投放（商品托管）基座 · 表结构测试：5 表可建、默认值生效、唯一约束生效。

运行（P-001：必须带 --basetemp，Windows 默认临时目录无权限）：
  python -m pytest tests/test_ads_tables.py -q --basetemp=".pytest-tmp"
"""

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from ads import tables as T
from ads.models import utcnow

EXPECTED_TABLES = {
    "ad_campaigns",
    "ad_runs",
    "ad_report_snapshots",
    "ad_account_states",
    "ad_materials",
}


def _unique_column_sets(engine, table: str) -> list[set[str]]:
    insp = inspect(engine)
    return [set(u["column_names"]) for u in insp.get_unique_constraints(table)]


def _create_campaign(db_ads, product_id=1, **over):
    with db_ads.session() as s:
        row = T.AdCampaign(product_id=product_id, **over)
        s.add(row)
        s.flush()
        return row.id


# ---------------------------------------------------------------- 建表
def test_five_tables_created(db_ads):
    insp = inspect(db_ads.engine)
    names = set(insp.get_table_names())
    assert EXPECTED_TABLES <= names


def test_ad_campaigns_columns(db_ads):
    insp = inspect(db_ads.engine)
    cols = {c["name"] for c in insp.get_columns("ad_campaigns")}
    for name in (
        "id", "product_id", "ad_mode", "target_type", "target_roi",
        "material_ids_json", "status", "diagnosis", "batch_id",
        "created_at", "updated_at",
    ):
        assert name in cols, f"ad_campaigns 缺列 {name}"


def test_ad_runs_columns(db_ads):
    insp = inspect(db_ads.engine)
    cols = {c["name"] for c in insp.get_columns("ad_runs")}
    for name in (
        "id", "campaign_id", "attempt", "status", "error_code",
        "evidence_json", "lease_owner", "lease_expires_at", "batch_id", "created_at",
    ):
        assert name in cols, f"ad_runs 缺列 {name}"


def test_ad_report_snapshots_columns(db_ads):
    insp = inspect(db_ads.engine)
    cols = {c["name"] for c in insp.get_columns("ad_report_snapshots")}
    for name in (
        "id", "campaign_id", "recorded_at", "impressions", "spend",
        "gmv", "platform_subsidy", "diagnosis", "status",
    ):
        assert name in cols, f"ad_report_snapshots 缺列 {name}"


def test_ad_account_states_columns(db_ads):
    insp = inspect(db_ads.engine)
    cols = {c["name"] for c in insp.get_columns("ad_account_states")}
    for name in (
        "id", "balance", "status", "throttle_level", "paused_until",
        "pause_reason", "updated_at",
    ):
        assert name in cols, f"ad_account_states 缺列 {name}"


def test_ad_materials_columns(db_ads):
    insp = inspect(db_ads.engine)
    cols = {c["name"] for c in insp.get_columns("ad_materials")}
    for name in (
        "id", "material_id", "asset_id", "file_path", "duration",
        "resolution", "evaluation", "upload_status", "platform_material_id",
        "created_at", "updated_at",
    ):
        assert name in cols, f"ad_materials 缺列 {name}"


# ---------------------------------------------------------------- 默认值
def test_ad_campaigns_defaults(db_ads):
    with db_ads.session() as s:
        row = T.AdCampaign(product_id=7)
        s.add(row)
        s.flush()
        assert row.ad_mode == "goods_trust"
        assert row.target_type == "roi"
        assert row.target_roi == 2.00
        assert row.material_ids_json == []
        assert row.status == "pending"
        assert row.diagnosis is None
        assert row.batch_id is None
        assert row.created_at is not None
        assert row.updated_at is not None


def test_ad_runs_defaults(db_ads):
    cid = _create_campaign(db_ads)
    with db_ads.session() as s:
        row = T.AdRun(campaign_id=cid)
        s.add(row)
        s.flush()
        assert row.attempt == 1
        assert row.status == "running"
        assert row.evidence_json == {}
        assert row.error_code is None
        assert row.lease_owner is None
        assert row.lease_expires_at is None
        assert row.created_at is not None


def test_ad_report_snapshot_defaults(db_ads):
    cid = _create_campaign(db_ads)
    with db_ads.session() as s:
        row = T.AdReportSnapshot(campaign_id=cid)
        s.add(row)
        s.flush()
        assert row.impressions == 0
        assert row.spend == 0
        assert row.gmv == 0
        assert row.platform_subsidy == 0
        assert row.diagnosis is None
        assert row.status is None
        assert row.recorded_at is not None


def test_ad_account_state_defaults(db_ads):
    with db_ads.session() as s:
        row = T.AdAccountState()
        s.add(row)
        s.flush()
        assert row.balance == 0
        assert row.status == "active"
        assert row.throttle_level == 0
        assert row.paused_until is None
        assert row.pause_reason == ""


def test_ad_material_defaults(db_ads):
    with db_ads.session() as s:
        row = T.AdMaterial(material_id="mat-1")
        s.add(row)
        s.flush()
        assert row.evaluation == "exploring"
        assert row.upload_status == "reviewing"
        assert row.asset_id is None
        assert row.duration is None
        assert row.resolution is None
        assert row.platform_material_id is None


# ---------------------------------------------------------------- NOT NULL
def test_campaign_product_id_required(db_ads):
    with pytest.raises(IntegrityError):
        with db_ads.session() as s:
            s.add(T.AdCampaign())


def test_material_id_required(db_ads):
    with pytest.raises(IntegrityError):
        with db_ads.session() as s:
            s.add(T.AdMaterial(material_id=None))


# ---------------------------------------------------------------- 唯一约束
def test_snapshot_unique_campaign_time(db_ads):
    cid = _create_campaign(db_ads)
    t = utcnow()
    with db_ads.session() as s:
        s.add(T.AdReportSnapshot(campaign_id=cid, recorded_at=t))
    with pytest.raises(IntegrityError):
        with db_ads.session() as s:
            s.add(T.AdReportSnapshot(campaign_id=cid, recorded_at=t))


def test_material_id_unique(db_ads):
    with db_ads.session() as s:
        s.add(T.AdMaterial(material_id="mat-1"))
    with pytest.raises(IntegrityError):
        with db_ads.session() as s:
            s.add(T.AdMaterial(material_id="mat-1"))
