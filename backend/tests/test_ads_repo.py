"""M5 自动小店投放（商品托管）基座 · repo 层测试。

覆盖：campaign CRUD、run 创建/回写、snapshot 幂等 upsert、预算汇总、
account 状态/节流、material 幂等 upsert、app_config 只读。

运行（P-001：必须带 --basetemp，Windows 默认临时目录无权限）：
  python -m pytest tests/test_ads_repo.py -q --basetemp=".pytest-tmp"
"""

from datetime import timedelta

from sqlalchemy import text

from ads import tables as T
from ads.models import utcnow
from ads.repo import (
    bump_throttle,
    count_active_campaigns,
    count_runs,
    create_campaign,
    create_run,
    get_account_state,
    get_campaign,
    list_active_campaigns,
    list_campaigns,
    list_materials,
    list_snapshots,
    read_app_config,
    reset_throttle,
    sum_spend_since,
    update_campaign_diagnosis,
    update_campaign_status,
    update_run_result,
    upsert_account_state,
    upsert_material,
    upsert_snapshot,
)


def _new_campaign(db_ads, product_id=101, **over):
    with db_ads.session() as s:
        return create_campaign(s, product_id=product_id, **over)


# ---------------------------------------------------------------- campaign
def test_campaign_crud(db_ads):
    cid = _new_campaign(
        db_ads, product_id=101, target_roi=3.0, material_ids=["m1", "m2"]
    )
    with db_ads.session() as s:
        c = get_campaign(s, cid)
        assert c is not None
        assert c.product_id == 101
        assert c.ad_mode == "goods_trust"
        assert c.target_type == "roi"
        assert c.target_roi == 3.0
        assert c.material_ids_json == ["m1", "m2"]
        assert c.status == "pending"
        assert c.diagnosis is None
        # 列表/过滤
        assert [x.id for x in list_campaigns(s)] == [cid]
        assert list_campaigns(s, status="active") == []
        # 状态/诊断更新
        assert update_campaign_status(s, cid, "active") is True
        assert update_campaign_diagnosis(s, cid, "excellent") is True
        c = get_campaign(s, cid)
        assert c.status == "active"
        assert c.diagnosis == "excellent"
        # 活跃清单与计数
        assert [x.id for x in list_active_campaigns(s)] == [cid]
        assert count_active_campaigns(s) == 1
        # 不存在的 id 更新返回 False
        assert update_campaign_status(s, 99999, "ended") is False
        assert update_campaign_diagnosis(s, 99999, "good") is False


def test_list_campaigns_status_filter(db_ads):
    _new_campaign(db_ads, product_id=1)
    _new_campaign(db_ads, product_id=2, status="paused")
    with db_ads.session() as s:
        assert len(list_campaigns(s)) == 2
        assert [x.product_id for x in list_campaigns(s, status="paused")] == [2]
        assert [x.product_id for x in list_campaigns(s, status="pending")] == [1]


# ---------------------------------------------------------------- run
def test_run_create_and_update_result(db_ads):
    cid = _new_campaign(db_ads)
    with db_ads.session() as s:
        rid = create_run(s, campaign_id=cid, attempt=1, lease_owner="worker-1")
        assert rid > 0
        assert count_runs(s) == 1
        assert count_runs(s, campaign_id=cid) == 1
        assert count_runs(s, status="running") == 1
        ok = update_run_result(
            s,
            campaign_id=cid,
            attempt=1,
            status="failed",
            error_code="RATE_LIMIT",
            evidence={"url": "https://store.weixin.qq.com", "ms": 123},
        )
        assert ok is True
        row = s.get(T.AdRun, rid)
        assert row.status == "failed"
        assert row.error_code == "RATE_LIMIT"
        assert row.evidence_json["ms"] == 123
        assert row.lease_owner == "worker-1"
        assert count_runs(s, status="failed") == 1
        # 不存在的 attempt 返回 False
        assert update_run_result(s, campaign_id=cid, attempt=9, status="success") is False


def test_run_multi_attempt(db_ads):
    cid = _new_campaign(db_ads)
    with db_ads.session() as s:
        r1 = create_run(s, campaign_id=cid, attempt=1)
        r2 = create_run(s, campaign_id=cid, attempt=2)
        assert r1 != r2
        assert count_runs(s, campaign_id=cid) == 2
        assert update_run_result(s, campaign_id=cid, attempt=1, status="success") is True
        assert update_run_result(s, campaign_id=cid, attempt=2, status="blocked", error_code="AUTH_REQUIRED") is True
        assert s.get(T.AdRun, r1).status == "success"
        assert s.get(T.AdRun, r2).status == "blocked"
        assert s.get(T.AdRun, r2).error_code == "AUTH_REQUIRED"


# ---------------------------------------------------------------- snapshot（幂等关键）
def test_snapshot_upsert_idempotent(db_ads):
    """同 (campaign_id, recorded_at) upsert 两次仍 1 行，且值更新为最新。"""
    cid = _new_campaign(db_ads)
    t = utcnow()
    with db_ads.session() as s:
        upsert_snapshot(s, campaign_id=cid, recorded_at=t, impressions=100, spend=50, gmv=200)
    with db_ads.session() as s:
        upsert_snapshot(s, campaign_id=cid, recorded_at=t, impressions=200, spend=80, gmv=400, platform_subsidy=10)
    with db_ads.session() as s:
        snaps = list_snapshots(s, campaign_id=cid)
        assert len(snaps) == 1  # 幂等：仍 1 行
        assert snaps[0].impressions == 200
        assert snaps[0].spend == 80
        assert snaps[0].gmv == 400
        assert snaps[0].platform_subsidy == 10


def test_snapshot_distinct_times_append(db_ads):
    cid = _new_campaign(db_ads)
    with db_ads.session() as s:
        upsert_snapshot(s, campaign_id=cid, recorded_at=utcnow(), spend=10)
        upsert_snapshot(s, campaign_id=cid, recorded_at=utcnow(), spend=20)
        assert len(list_snapshots(s, campaign_id=cid)) == 2  # 不同时间各自成行


# ---------------------------------------------------------------- 预算汇总
def test_sum_spend_since(db_ads):
    cid1 = _new_campaign(db_ads, product_id=101)
    cid2 = _new_campaign(db_ads, product_id=102)
    now = utcnow()
    with db_ads.session() as s:
        upsert_snapshot(s, campaign_id=cid1, recorded_at=now - timedelta(hours=2), spend=100)
        upsert_snapshot(s, campaign_id=cid1, recorded_at=now - timedelta(minutes=30), spend=200)
        upsert_snapshot(s, campaign_id=cid2, recorded_at=now - timedelta(minutes=10), spend=300)
        # 1 小时内：30min(200) + 10min(300)
        assert sum_spend_since(s, since=now - timedelta(hours=1)) == 500
        # 3 小时内：全部 600
        assert sum_spend_since(s, since=now - timedelta(hours=3)) == 600
        # 过滤查询
        assert len(list_snapshots(s)) == 3
        assert len(list_snapshots(s, campaign_id=cid1)) == 2
        assert len(list_snapshots(s, since=now - timedelta(hours=1))) == 2


# ---------------------------------------------------------------- account
def test_account_state_upsert_and_throttle(db_ads):
    with db_ads.session() as s:
        assert get_account_state(s) is None  # 初始无记录
        st = upsert_account_state(s, balance=5000, status="active")
        assert st.balance == 5000
        assert st.status == "active"
        assert st.throttle_level == 0
        # 单例：第二次 upsert 更新而非新增
        st2 = upsert_account_state(s, balance=3000)
        assert st2.id == st.id
        assert get_account_state(s).balance == 3000
        assert get_account_state(s).status == "active"  # 未给字段不变
        # 节流 0→4 封顶
        assert bump_throttle(s) == 1
        assert bump_throttle(s) == 2
        assert get_account_state(s).throttle_level == 2
        assert reset_throttle(s) == 0
        assert get_account_state(s).throttle_level == 0
        # 风控/暂停字段
        upsert_account_state(s, status="risk_control", pause_reason="连续失败≥2")
        st = get_account_state(s)
        assert st.status == "risk_control"
        assert st.pause_reason == "连续失败≥2"


def test_throttle_caps_at_4(db_ads):
    with db_ads.session() as s:
        upsert_account_state(s, throttle_level=4)
        assert bump_throttle(s) == 4  # 上限 4 不再提升


# ---------------------------------------------------------------- material（幂等）
def test_material_upsert_idempotent(db_ads):
    with db_ads.session() as s:
        m = upsert_material(
            s,
            material_id="mat-1",
            asset_id=5,
            file_path="videos/2025/a.mp4",
            duration=15.0,
            resolution="720x1280",
            evaluation="exploring",
        )
        assert m.evaluation == "exploring"
        assert m.upload_status == "reviewing"
        assert m.asset_id == 5
        # 同 material_id 二次 upsert：更新而非新增
        m2 = upsert_material(
            s,
            material_id="mat-1",
            duration=16.0,
            evaluation="efficient",
            upload_status="approved",
            platform_material_id="pf-9",
        )
        assert m2.id == m.id
        assert m2.evaluation == "efficient"
        assert m2.upload_status == "approved"
        assert m2.platform_material_id == "pf-9"
        assert m2.asset_id == 5  # 未给字段不变
        assert m2.file_path == "videos/2025/a.mp4"
        # 不同 material_id 各自成行
        upsert_material(s, material_id="mat-2", evaluation="potential")
        assert len(list_materials(s)) == 2
        assert len(list_materials(s, evaluation="efficient")) == 1
        assert len(list_materials(s, evaluation="potential")) == 1
        assert len(list_materials(s, evaluation="exploring")) == 0


# ---------------------------------------------------------------- app_config（只读）
def test_read_app_config_fallback_when_table_missing(db_ads):
    """本模块库无 app_config 表（M0 基座表在 m1-sourcing.db）→ 兜底 default 不报错。"""
    with db_ads.session() as s:
        assert read_app_config(s, "ads.batch_size", 50) == 50


def test_read_app_config_readonly(db_ads):
    """临时库建最小 app_config 表，验证只读读取 + 读后内容不变。"""
    with db_ads.session() as s:
        s.execute(text(
            "CREATE TABLE app_config ("
            " key VARCHAR(120) PRIMARY KEY, value TEXT, description TEXT, updated_at TEXT)"
        ))
        s.execute(
            text("INSERT INTO app_config (key, value, description) VALUES (:k, :v, :d)"),
            {"k": "ads.batch_size", "v": "60", "d": ""},
        )
        s.execute(
            text("INSERT INTO app_config (key, value, description) VALUES (:k, :v, :d)"),
            {"k": "ads.report_interval_s", "v": '"2400"', "d": ""},
        )
    with db_ads.session() as s:
        # JSON 数字解析为 int
        assert read_app_config(s, "ads.batch_size", 50) == 60
        # JSON 字符串保持 str
        assert read_app_config(s, "ads.report_interval_s", 1800) == "2400"
        # 缺失 key 返回 default
        assert read_app_config(s, "ads.no_such_key", "fallback") == "fallback"
        # 只读验证：读后表内容不变（无 INSERT/UPDATE）
        rows_before = s.execute(text("SELECT key, value FROM app_config ORDER BY key")).all()
        read_app_config(s, "ads.batch_size", 50)
        read_app_config(s, "ads.report_interval_s", 1800)
        rows_after = s.execute(text("SELECT key, value FROM app_config ORDER BY key")).all()
        assert rows_before == rows_after
