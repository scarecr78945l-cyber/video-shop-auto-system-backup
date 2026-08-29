"""API 层测试 · 人工闸门工作台（test_api_workbench.py）。

覆盖：闸门待办聚合计数、异常中心清单、人工接管重试写（waiting_* → pending）。
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
        yield client, services, creds


def test_gates_counts(ctx):
    c, services, creds = ctx
    resp = c.get("/api/workbench/gates")
    assert resp.status_code == 200
    body = resp.json()
    counts = body["counts"]
    assert counts["sourcing_review"] == 1        # M1 manual_review 商品
    assert counts["listing_confirm"] == 1        # M4 pending 任务
    assert counts["image_review"] == 2           # M3 待审核图片
    assert counts["material_pre_review"] == 1    # M2 manual_review 素材
    assert counts["verification_takeover"] == 1  # M0 waiting_verification
    assert counts["login_takeover"] == 0
    assert body["total"] == sum(counts.values())


def test_exceptions_list(ctx):
    c, services, creds = ctx
    resp = c.get("/api/workbench/exceptions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    statuses = {item["status"] for item in body["items"]}
    assert statuses <= {"blocked", "waiting_verification", "waiting_login"}
    # 过滤
    resp2 = c.get("/api/workbench/exceptions", params={"status": "waiting_verification"})
    assert resp2.json()["total"] == 1
    assert resp2.json()["items"][0]["error_code"] == "VERIFICATION_REQUIRED"


def test_retry_job(ctx):
    c, services, creds = ctx
    exc = c.get("/api/workbench/exceptions", params={"status": "waiting_verification"}).json()
    job_id = exc["items"][0]["id"]
    resp = c.post(f"/api/workbench/retry/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "pending"
    assert body["operator"] == "admin"
    # 已恢复：不再出现在异常中心
    exc2 = c.get("/api/workbench/exceptions", params={"status": "waiting_verification"}).json()
    assert all(item["id"] != job_id for item in exc2["items"])


def test_retry_job_wrong_state_409(ctx):
    c, services, creds = ctx
    jobs = c.get("/api/jobs", params={"status": "success"}).json()["items"]
    job_id = jobs[0]["id"]
    resp = c.post(f"/api/workbench/retry/{job_id}")
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_STATE"


def test_retry_job_not_found(ctx):
    c, services, creds = ctx
    resp = c.post("/api/workbench/retry/999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_MATCH"


def test_retry_requires_login(ctx):
    c, services, creds = ctx
    c.cookies.clear()
    resp = c.post("/api/workbench/retry/1")
    assert resp.status_code == 401
