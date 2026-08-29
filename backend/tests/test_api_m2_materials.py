"""API 层测试 · M2 素材（test_api_m2_materials.py）。

覆盖：素材库列表（多条件过滤 + 分页）、素材详情、相关性人工确认写（成功/404/
非法 decision）、上传记录。
"""

from __future__ import annotations

import pytest

from tests.api_testing import login, make_client, seed_m2


@pytest.fixture()
def ctx(tmp_path):
    client, services, creds, viewer_creds = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        ids = seed_m2(services)
        yield client, services, creds, ids


def test_assets_list_filters_and_pagination(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/assets")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2

    resp2 = c.get("/api/assets", params={"asset_type": "video"})
    assert resp2.json()["total"] == 1

    resp3 = c.get("/api/assets", params={"relevance_status": "manual_review"})
    assert resp3.json()["total"] == 1
    assert resp3.json()["items"][0]["relevance_status"] == "manual_review"

    resp4 = c.get("/api/assets", params={"upload_status": "uploaded"})
    assert resp4.json()["total"] == 1

    resp5 = c.get("/api/assets", params={"page": 1, "page_size": 1})
    assert len(resp5.json()["items"]) == 1


def test_asset_detail_redacts_source_url(ctx):
    c, services, creds, ids = ctx
    aid = ids["video"]
    resp = c.get(f"/api/assets/{aid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == aid
    assert body["asset_type"] == "video"
    assert body["duration"] == 30
    assert body["resolution"] == "720x1280"
    # source_url 敏感查询参数脱敏（token 值 → ***）
    assert "REDACT_ME" not in (body["source_url"] or "")


def test_asset_detail_not_found(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/assets/999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_MATCH"


def test_relevance_confirm_pass(ctx):
    c, services, creds, ids = ctx
    aid = ids["video"]  # 当前 manual_review
    resp = c.post(f"/api/assets/{aid}/relevance-confirm", json={"decision": "pass"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["relevance_status"] == "passed"
    # 幂等：重复 pass → changed=False 仍 200
    resp2 = c.post(f"/api/assets/{aid}/relevance-confirm", json={"decision": "pass"})
    assert resp2.status_code == 200
    assert resp2.json()["changed"] is False


def test_relevance_confirm_reject(ctx):
    c, services, creds, ids = ctx
    aid = ids["image"]
    resp = c.post(f"/api/assets/{aid}/relevance-confirm", json={"decision": "reject"})
    assert resp.status_code == 200
    assert resp.json()["relevance_status"] == "failed"


def test_relevance_confirm_requires_login(ctx):
    c, services, creds, ids = ctx
    c.cookies.clear()
    resp = c.post(f"/api/assets/{ids['video']}/relevance-confirm", json={"decision": "pass"})
    assert resp.status_code == 401


def test_relevance_confirm_not_found(ctx):
    c, services, creds, ids = ctx
    resp = c.post("/api/assets/999999/relevance-confirm", json={"decision": "pass"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_MATCH"


def test_relevance_confirm_invalid_decision(ctx):
    c, services, creds, ids = ctx
    resp = c.post(f"/api/assets/{ids['video']}/relevance-confirm", json={"decision": "bogus"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "PLATFORM_REJECT"


def test_asset_uploads_list(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/assets/uploads")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    up = body["items"][0]
    assert up["status"] == "success"
    assert up["platform_material_id"] == "mat-upload-001"
    # 过滤
    resp2 = c.get("/api/assets/uploads", params={"status": "failed"})
    assert resp2.json()["total"] == 0
