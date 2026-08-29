"""API 层测试 · M1 选品（test_api_m1_sourcing.py）。

覆盖：商品池列表（score 排序 + 过滤）、商品详情（quotes + source_evidence 脱敏）、
调度状态、复核闸门写（成功/鉴权/404）、选品周报。
"""

from __future__ import annotations

import pytest

from tests.api_testing import login, make_client, seed_m1


@pytest.fixture()
def ctx(tmp_path):
    client, services, creds, viewer_creds = make_client(tmp_path)
    with client:
        assert login(client, creds).status_code == 200
        ids = seed_m1(services)
        yield client, services, creds, ids


def test_products_list_sorted_by_score(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/products")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    scores = [item["score"] for item in body["items"]]
    assert scores == sorted(scores, reverse=True), "商品池必须按 score 降序"
    first = body["items"][0]
    # M1 元字段直接透传
    assert isinstance(first["platform_price"], float)
    assert isinstance(first["suggested_price"], float)
    # compliance 三态
    assert first["compliance"]["state"] in ("candidate", "manual_review", "hard_reject")
    # score_breakdown 摘要
    assert "dimensions" in first["score_breakdown"]


def test_products_list_filters(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/products", params={"state": "pool"})
    body = resp.json()
    assert body["total"] == 2
    assert all(item["state"] == "pool" for item in body["items"])

    resp2 = c.get("/api/products", params={"compliance": "manual_review"})
    assert resp2.json()["total"] == 1

    resp3 = c.get("/api/products", params={"min_score": 70, "max_score": 80})
    assert all(70 <= item["score"] <= 80 for item in resp3.json()["items"])

    resp4 = c.get("/api/products", params={"category": "宠物用品"})
    assert resp4.json()["total"] == 1


def test_products_list_ad_conversion_money(ctx):
    """ad_conversion.sales_amount（分）→ 元 换算断言（128000 分 → 1280.0 元）。"""
    c, services, creds, ids = ctx
    resp = c.get("/api/products")
    body = resp.json()
    top = body["items"][0]
    assert top["ad_conversion"]["roi"] == 3.2
    assert top["ad_conversion"]["sales_amount_yuan"] == 1280.0
    assert isinstance(top["ad_conversion"]["sales_amount_yuan"], float)
    assert "sales_amount" not in top["ad_conversion"], "禁止把分输出给前端（DA-001）"


def test_product_detail_with_quotes_and_evidence(ctx):
    c, services, creds, ids = ctx
    product_id = ids["免打孔卫生间置物架 浴室收纳架"]
    resp = c.get(f"/api/products/{product_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == product_id
    assert len(body["quotes"]) >= 1
    quote = body["quotes"][0]
    assert isinstance(quote["unit_cost"], float)  # 元
    assert len(body["source_evidence"]) >= 1
    evidence = body["source_evidence"][0]
    # 脱敏：raw 中 token 值不得出现明文
    assert "SHOULD_BE_REDACTED" not in str(evidence["raw"])
    # 五维打分字段
    dims = body["score_breakdown"]["dimensions"]
    assert "trend" in dims and "profit" in dims
    assert "weighted" in dims["trend"]


def test_product_detail_not_found(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/products/999999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_MATCH"


def test_sourcing_status(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/sourcing/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "boards" in body and "platforms" in body
    # 造数时未建账本行 → 空数组亦可（字段形状正确）
    assert isinstance(body["boards"], list)


def test_gate_confirm_success(ctx):
    c, services, creds, ids = ctx
    product_id = ids["便携榨汁杯 无线充电 家用小型果汁机"]  # manual_review
    resp = c.post("/api/sourcing/gate-confirm", json={"product_id": product_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["state"] == "pool"
    assert body["operator"] == "admin"
    # 再次确认 → 409（已在池中）
    resp2 = c.post("/api/sourcing/gate-confirm", json={"product_id": product_id})
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "INVALID_STATE"


def test_gate_confirm_requires_login(ctx):
    c, services, creds, ids = ctx
    c.cookies.clear()
    product_id = ids["便携榨汁杯 无线充电 家用小型果汁机"]
    resp = c.post("/api/sourcing/gate-confirm", json={"product_id": product_id})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_REQUIRED"


def test_gate_confirm_not_found(ctx):
    c, services, creds, ids = ctx
    resp = c.post("/api/sourcing/gate-confirm", json={"product_id": 999999})
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_MATCH"


def test_sourcing_report(ctx):
    c, services, creds, ids = ctx
    resp = c.get("/api/sourcing/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["period_days"] == 7
    assert "sources" in body and "error_distribution" in body and "funnel" in body
    assert "collected_events" in body["funnel"]
