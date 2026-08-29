"""API 层测试 · 系统域（test_api_system.py）。

覆盖：overview 聚合、jobs 过滤/分页/详情脱敏、kill-switch 管理员权限、
app-config 读写管理员权限、logs 脱敏。
"""

from __future__ import annotations

import pytest

from tests.api_testing import login, make_client, seed_all


@pytest.fixture()
def ctx(tmp_path):
    client, services, creds, viewer_creds = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        seed_all(services)
        yield client, services, creds, viewer_creds


def test_overview_aggregates(ctx):
    c, services, creds, viewer = ctx
    resp = c.get("/api/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_jobs"] >= 3
    assert body["jobs_by_status"]["success"] >= 1
    assert body["jobs_by_status"]["waiting_verification"] >= 1
    assert body["jobs_by_status"]["blocked"] >= 1
    assert body["jobs_by_error_code"]["VERIFICATION_REQUIRED"] >= 1
    assert "risk" in body
    assert "kill_switch_enabled" in body["risk"]
    assert "ad_balance_yuan" in body["risk"]
    assert body["generated_at"].endswith("Z")


def test_jobs_list_filters_and_pagination(ctx):
    c, services, creds, viewer = ctx
    resp = c.get("/api/jobs", params={"status": "success"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(item["status"] == "success" for item in body["items"])

    resp2 = c.get("/api/jobs", params={"error_code": "VERIFICATION_REQUIRED"})
    body2 = resp2.json()
    assert body2["total"] >= 1
    assert all(item["error_code"] == "VERIFICATION_REQUIRED" for item in body2["items"])

    resp3 = c.get("/api/jobs", params={"stage": "listing_upload"})
    assert resp3.status_code == 200
    assert all(item["stage"] == "listing_upload" for item in resp3.json()["items"])

    resp4 = c.get("/api/jobs", params={"page": 1, "page_size": 2})
    body4 = resp4.json()
    assert len(body4["items"]) <= 2
    assert body4["page"] == 1 and body4["page_size"] == 2


def test_job_detail_redacts_evidence(ctx):
    c, services, creds, viewer = ctx
    jobs = c.get("/api/jobs").json()["items"]
    job_id = jobs[0]["id"]
    resp = c.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    # 证据脱敏：token 值不得出现明文（P-004）
    text = str(body.get("evidence") or {}) + str(body.get("payload") or {})
    assert "SECRET" not in text


def test_job_detail_not_found(ctx):
    c, services, creds, viewer = ctx
    resp = c.get("/api/jobs/999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_MATCH"


def test_kill_switch_admin_only(ctx):
    c, services, creds, viewer_creds = ctx
    # 未登录 → 401
    c.cookies.clear()
    assert c.post("/api/kill-switch", json={"enabled": True}).status_code == 401
    # viewer（非管理员）→ 403
    assert login(c, viewer_creds).status_code == 200
    resp = c.post("/api/kill-switch", json={"enabled": True})
    assert resp.status_code == 403
    assert resp.json()["code"] == "AUTH_REQUIRED"
    # 管理员 → 200，且生效
    assert login(c, creds).status_code == 200
    resp2 = c.post("/api/kill-switch", json={"enabled": True})
    assert resp2.status_code == 200
    assert resp2.json()["enabled"] is True
    assert c.get("/api/overview").json()["risk"]["kill_switch_enabled"] is True
    assert c.post("/api/kill-switch", json={"enabled": False}).status_code == 200


def test_app_config_admin_write_only(ctx):
    c, services, creds, viewer_creds = ctx
    # 未登录 PUT → 401
    c.cookies.clear()
    assert (
        c.put("/api/app-config/category.whitelist", json={"value": ["收纳整理"]}).status_code
        == 401
    )
    # viewer → 403
    assert login(c, viewer_creds).status_code == 200
    assert (
        c.put("/api/app-config/category.whitelist", json={"value": ["收纳整理"]}).status_code
        == 403
    )
    # 管理员 PUT + GET
    assert login(c, creds).status_code == 200
    resp = c.put(
        "/api/app-config/category.whitelist",
        json={"value": ["收纳整理", "宠物用品"], "description": "类目白名单"},
    )
    assert resp.status_code == 200
    assert resp.json()["key"] == "category.whitelist"
    assert resp.json()["value"] == ["收纳整理", "宠物用品"]
    resp2 = c.get("/api/app-config/category.whitelist")
    assert resp2.status_code == 200
    assert resp2.json()["value"] == ["收纳整理", "宠物用品"]
    # GET 不存在 → 404 错误格式
    resp3 = c.get("/api/app-config/no.such.key")
    assert resp3.status_code == 404
    assert resp3.json()["code"] == "NO_MATCH"


def test_logs_endpoint_redacted(ctx):
    c, services, creds, viewer = ctx
    # 触发一次审计写入（kill-switch 会写 logs）
    c.post("/api/kill-switch", json={"enabled": True})
    resp = c.get("/api/logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    events = [item["event"] for item in body["items"]]
    assert "kill_switch.set" in events
    for item in body["items"]:
        text = str(item.get("evidence") or {})
        assert "SECRET" not in text
