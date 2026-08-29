"""API 层测试 · M3 素材优化（test_api_m3_optimization.py）。

覆盖：批次列表/详情、图片审核人工判定写（approve → review_status + P0-2 规则草稿）、
整批通过、文案候选列表。
"""

from __future__ import annotations

import pytest

from tests.api_testing import login, make_client, seed_m3


@pytest.fixture()
def ctx(tmp_path):
    client, services, creds, viewer_creds = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        data = seed_m3(services)
        yield client, services, creds, data


def test_batches_list(ctx):
    c, services, creds, data = ctx
    resp = c.get("/api/optimization/batches")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    batch = body["items"][0]
    assert batch["batch_id"] == "batch-001"
    assert batch["status"] == "generating"
    assert batch["image_count"] == 2


def test_batch_detail_with_assets(ctx):
    c, services, creds, data = ctx
    resp = c.get("/api/optimization/batches/batch-001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["batch_id"] == "batch-001"
    assert len(body["assets"]) == 2
    asset = body["assets"][0]
    assert asset["image_type"] == "main"
    assert asset["review_status"] == "pending"
    assert "audit" in asset


def test_batch_detail_not_found(ctx):
    c, services, creds, data = ctx
    resp = c.get("/api/optimization/batches/no-such-batch")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_MATCH"


def test_image_decision_approve(ctx):
    c, services, creds, data = ctx
    image_id = data["image_id"]
    resp = c.post(
        f"/api/optimization/assets/{image_id}/decision",
        json={"decision": "approve", "reason": "构图合格"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["review_status"] == "approved"
    assert body["rule_draft_created"] is True
    # P0-2：learning_rule_drafts 已沉淀
    from sqlalchemy import select

    from foundation.tables import LearningRuleDraft

    with services.m0_db.session() as session:
        drafts = list(session.scalars(select(LearningRuleDraft)).all())
    assert any(d.rule_key == "image_review_approve" for d in drafts)


def test_image_decision_reject(ctx):
    c, services, creds, data = ctx
    image_id = data["image_id"]
    resp = c.post(
        f"/api/optimization/assets/{image_id}/decision",
        json={"decision": "reject", "reason": "文字遮挡主体"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_status"] == "rejected"
    # 详情中 reject_reason 可见
    detail = c.get("/api/optimization/batches/batch-001").json()
    target = [a for a in detail["assets"] if a["image_id"] == image_id][0]
    assert target["reject_reason"] == "文字遮挡主体"


def test_image_decision_invalid_value(ctx):
    c, services, creds, data = ctx
    resp = c.post(
        f"/api/optimization/assets/{data['image_id']}/decision",
        json={"decision": "maybe"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_image_decision_not_found(ctx):
    c, services, creds, data = ctx
    resp = c.post("/api/optimization/assets/no-such-image/decision", json={"decision": "approve"})
    assert resp.status_code == 404


def test_image_decision_requires_login(ctx):
    c, services, creds, data = ctx
    c.cookies.clear()
    resp = c.post(
        f"/api/optimization/assets/{data['image_id']}/decision",
        json={"decision": "approve"},
    )
    assert resp.status_code == 401


def test_approve_batch(ctx):
    c, services, creds, data = ctx
    resp = c.post("/api/optimization/batches/batch-001/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["images_approved"] == 2
    detail = c.get("/api/optimization/batches/batch-001").json()
    assert all(a["review_status"] == "approved" for a in detail["assets"])
    # 幂等：再次 approve → already_approved
    resp2 = c.post("/api/optimization/batches/batch-001/approve")
    assert resp2.status_code == 200
    assert resp2.json()["already_approved"] is True


def test_approve_batch_not_found(ctx):
    c, services, creds, data = ctx
    resp = c.post("/api/optimization/batches/no-such/approve")
    assert resp.status_code == 404


def test_copywrites_list(ctx):
    c, services, creds, data = ctx
    resp = c.get("/api/optimization/copywrites")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    types = {item["copy_type"] for item in body["items"]}
    assert {"title", "ad"} <= types
    # 过滤
    resp2 = c.get("/api/optimization/copywrites", params={"copy_type": "ad"})
    assert resp2.json()["total"] == 1
