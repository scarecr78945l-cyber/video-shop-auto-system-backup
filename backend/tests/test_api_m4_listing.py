"""API 层测试 · M4 上架（test_api_m4_listing.py）。

覆盖：任务列表（状态过滤 + 列）、任务详情（audit_records + spu）、op-logs、
确认闸门写（pending→creating + 状态冲突 409）、拒审重提、待上架商品（金额 分→元）。
"""

from __future__ import annotations

import pytest

from tests.api_testing import login, make_client, seed_m4


@pytest.fixture()
def ctx(tmp_path):
    client, services, creds, viewer_creds = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        ids = seed_m4(services)
        yield client, services, creds, ids


def test_tasks_list_with_title_and_error_code(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/listing/tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    items = {item["task_id"]: item for item in body["items"]}
    pending = items[ids["pending"]]
    assert pending["status"] == "pending"
    assert pending["title"] == "免打孔卫生间置物架"
    assert pending["error_code"] is None or pending["error_code"] == ""
    # 过滤
    resp2 = c.get("/api/listing/tasks", params={"status": "listed"})
    assert resp2.json()["total"] == 1
    assert resp2.json()["items"][0]["task_id"] == ids["listed"]


def test_task_detail_with_spu_and_audit(ctx):
    c, services, creds, ids = ctx
    resp = c.get(f"/api/listing/tasks/{ids['listed']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == ids["listed"]
    assert body["status"] == "listed"
    assert body["product_link"].startswith("https://channels.weixin.qq.com")
    assert body["spu"]["spu_id"] == "spu-002"
    assert isinstance(body["audit_records"], list)
    assert body["link_verified_at"] is not None


def test_task_detail_not_found(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/listing/tasks/no-such-task")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_MATCH"


def test_task_op_logs(ctx):
    c, services, creds, ids = ctx
    resp = c.get(f"/api/listing/tasks/{ids['pending']}/op-logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    apis = {item["api"] for item in body["items"]}
    assert {"state_machine", "create_spu"} <= apis
    assert body["items"][0]["error_code"] is None


def test_confirm_pending_to_creating(ctx):
    c, services, creds, ids = ctx
    resp = c.post(f"/api/listing/tasks/{ids['pending']}/confirm", json={"note": "确认上架"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "creating"
    assert body["operator"] == "admin"
    # 状态机轨迹留痕：op-logs 含 state_machine transition
    logs = c.get(f"/api/listing/tasks/{ids['pending']}/op-logs").json()
    assert any(item["api"] == "state_machine" for item in logs["items"])


def test_confirm_wrong_state_409(ctx):
    c, services, creds, ids = ctx
    # listed 任务不能 confirm
    resp = c.post(f"/api/listing/tasks/{ids['listed']}/confirm", json={})
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_STATE"


def test_confirm_requires_login(ctx):
    c, services, creds, ids = ctx
    c.cookies.clear()
    resp = c.post(f"/api/listing/tasks/{ids['pending']}/confirm", json={})
    assert resp.status_code == 401


def test_retry_retry_candidate(ctx):
    c, services, creds, ids = ctx
    resp = c.post(f"/api/listing/tasks/{ids['retry']}/retry")
    assert resp.status_code == 200
    assert resp.json()["status"] == "creating"


def test_retry_rejected_then_creating(ctx):
    c, services, creds, ids = ctx
    # 直接建一个 rejected 任务（状态机 rejected → retry_candidate → creating 由 API 组合）
    from listing.models import ListingTask

    repo = services.m4_repo
    rejected = ListingTask(
        task_id="task-rejected-001",
        product_id=201,
        generation_version="v1",
        status="rejected",
        reject_reason_code="title",
    )
    repo.create_task(rejected)
    resp = c.post("/api/listing/tasks/task-rejected-001/retry")
    assert resp.status_code == 200
    assert resp.json()["status"] == "creating"


def test_retry_wrong_state_409(ctx):
    c, services, creds, ids = ctx
    resp = c.post(f"/api/listing/tasks/{ids['listed']}/retry")
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_STATE"


def test_listing_ready_money_conversion(ctx):
    """候选池价格 分→元 换算断言（1290 分 → 12.9 元；4990 分 → 49.9 元）。"""
    c, services, creds, ids = ctx
    resp = c.get("/api/listing/ready")
    assert resp.status_code == 200
    body = resp.json()
    # 仅 listed 且链接已验证的任务出现
    tasks = {item["task_id"]: item for item in body["items"]}
    assert ids["listed"] in tasks
    assert ids["pending"] not in tasks
    item = tasks[ids["listed"]]
    assert item["price_min_yuan"] == 49.9
    assert item["price_max_yuan"] == 49.9
    assert isinstance(item["price_min_yuan"], float)
