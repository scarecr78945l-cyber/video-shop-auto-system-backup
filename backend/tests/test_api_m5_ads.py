"""API 层测试 · M5 投放/托管（test_api_m5_ads.py）。

覆盖：托管看板列表（金额 分→元 + 最新快照）、托管详情（快照序列）、账户状态、
暂停/恢复/结束、素材绑定、报表聚合（分→元）。
"""

from __future__ import annotations

import pytest

from tests.api_testing import login, make_client, seed_m5


@pytest.fixture()
def ctx(tmp_path):
    client, services, creds, viewer_creds = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        ids = seed_m5(services)
        yield client, services, creds, ids


def test_campaigns_list_with_snapshot_money(ctx):
    """金额换算断言：spend 1290 分 → 12.9 元；gmv 2580 分 → 25.8 元；subsidy 100 分 → 1.0 元。"""
    c, services, creds, ids = ctx
    resp = c.get("/api/ads/campaigns")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    items = {item["id"]: item for item in body["items"]}
    active = items[ids["active"]]
    assert active["status"] == "active"
    assert active["target_type"] == "roi"
    assert active["target_roi"] == 2.0
    snap = active["latest_snapshot"]
    assert snap is not None
    assert snap["spend_yuan"] == 12.9
    assert snap["gmv_yuan"] == 25.8
    assert snap["subsidy_yuan"] == 1.0
    assert snap["impressions"] == 10000
    assert isinstance(snap["spend_yuan"], float)
    # 过滤
    resp2 = c.get("/api/ads/campaigns", params={"status": "paused"})
    assert resp2.json()["total"] == 1


def test_campaign_detail_snapshots_series(ctx):
    c, services, creds, ids = ctx
    resp = c.get(f"/api/ads/campaigns/{ids['active']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ids["active"]
    assert body["material_ids"] == ["mat-001"]
    assert len(body["snapshots"]) == 1
    snap = body["snapshots"][0]
    assert snap["spend_yuan"] == 12.9
    assert snap["recorded_at"].endswith("Z")


def test_campaign_detail_not_found(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/ads/campaigns/999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_MATCH"


def test_account_state_money(ctx):
    """余额换算断言：50000 分 → 500.0 元；min_balance 10000 分 → 100.0 元。"""
    c, services, creds, ids = ctx
    resp = c.get("/api/ads/account")
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance_yuan"] == 500.0
    assert body["min_balance_yuan"] == 100.0
    assert body["status"] == "active"
    assert body["throttle_level"] == 0
    assert isinstance(body["balance_yuan"], float)


def test_campaign_pause_resume(ctx):
    c, services, creds, ids = ctx
    resp = c.post(f"/api/ads/campaigns/{ids['active']}/pause")
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"
    assert resp.json()["operator"] == "admin"
    # 幂等：重复 pause → already
    resp2 = c.post(f"/api/ads/campaigns/{ids['active']}/pause")
    assert resp2.status_code == 200
    assert resp2.json()["already"] is True
    # resume → active
    resp3 = c.post(f"/api/ads/campaigns/{ids['active']}/resume")
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "active"


def test_campaign_end(ctx):
    c, services, creds, ids = ctx
    resp = c.post(f"/api/ads/campaigns/{ids['paused']}/end")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ended"
    # ended 后不能 resume → 409
    resp2 = c.post(f"/api/ads/campaigns/{ids['paused']}/resume")
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "INVALID_STATE"


def test_campaign_action_requires_login(ctx):
    c, services, creds, ids = ctx
    c.cookies.clear()
    resp = c.post(f"/api/ads/campaigns/{ids['active']}/pause")
    assert resp.status_code == 401


def test_campaign_materials(ctx):
    c, services, creds, ids = ctx
    resp = c.post(
        f"/api/ads/campaigns/{ids['active']}/materials",
        json={"material_ids": ["mat-001", "mat-002"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["material_ids"] == ["mat-001", "mat-002"]
    assert "preferred_order" in body
    # 详情回读
    detail = c.get(f"/api/ads/campaigns/{ids['active']}").json()
    assert detail["material_ids"] == ["mat-001", "mat-002"]


def test_campaign_materials_empty_422(ctx):
    c, services, creds, ids = ctx
    resp = c.post(f"/api/ads/campaigns/{ids['active']}/materials", json={"material_ids": []})
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_ads_report_aggregation(ctx):
    """报表按日聚合：spend 1290+990 分 → 22.8 元；gmv 2580 分 → 25.8 元。"""
    c, services, creds, ids = ctx
    resp = c.get("/api/ads/report", params={"days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    row = body["items"][0]
    assert row["spend_yuan"] == 22.8
    assert row["gmv_yuan"] == 25.8
    assert row["subsidy_yuan"] == 1.0
    assert row["campaign_count"] == 2
