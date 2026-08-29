"""微信小店 OpenAPI 薄封装单元测试（全部 mock，零网络）。

运行：cd backend && python -m pytest tests/test_wechat_openapi.py -q --basetemp=".pytest-tmp-m4"
"""

import logging

import pytest

from adapters.wechat_openapi import (
    TokenBucket,
    WechatApiError,
    WechatOpenApiAdapter,
)

TEST_SECRET = "unit-test-secret-0123456789"


@pytest.fixture()
def adapter() -> WechatOpenApiAdapter:
    return WechatOpenApiAdapter(mode="mock", secret=TEST_SECRET)


def test_sign_deterministic(adapter):
    payload = {"spu_id": "spu_123", "title": "测试商品"}
    first = adapter._sign(payload)
    second = adapter._sign(payload)
    assert "timestamp" in first and "sign" in first
    assert isinstance(first["timestamp"], int)
    assert first["sign"] == second["sign"]


def test_token_bucket_exhausted():
    """令牌桶耗尽语义（live 模式行为；mock 模式跳过限流——P0-1 预填集成
    暴露跨任务共享 bucket 会误伤 mock 连续提交，见 wechat_openapi.py _call）。"""
    bucket = TokenBucket(capacity=10, refill_rate=1.0, tokens=0.0)
    assert bucket.try_acquire() is False


def test_retry_then_success(adapter, monkeypatch):
    calls = {"n": 0}

    def flaky(api, biz):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise WechatApiError("RATE_LIMIT", message="mock 限流")
        return {"spu_id": "mock_spu_ok"}

    monkeypatch.setattr(adapter, "_mock_dispatch", flaky)
    monkeypatch.setattr(adapter, "_backoff_delay", lambda error_code: 0.0)

    result = adapter.create_spu(
        title="重试成功",
        category_id=1001,
        qualification=None,
        freight_template_id=1,
        purchase_limit=5,
    )
    assert result["spu_id"] == "mock_spu_ok"
    assert calls["n"] == 3


def test_error_classification(adapter, monkeypatch):
    def boom(api, biz):
        raise WechatApiError("PLATFORM_REJECT", message="平台拒绝", platform_code="200001")

    monkeypatch.setattr(adapter, "_mock_dispatch", boom)
    monkeypatch.setattr(adapter, "_backoff_delay", lambda error_code: 0.0)

    with pytest.raises(WechatApiError) as exc_info:
        adapter.query_audit_status(audit_id="audit_1")
    assert exc_info.value.error_code == "PLATFORM_REJECT"
    assert exc_info.value.platform_code == "200001"


def test_mock_full_flow(adapter):
    spu = adapter.create_spu(
        title="秋冬新款羽绒服",
        category_id=1001,
        qualification=None,
        freight_template_id=1,
        purchase_limit=3,
    )
    assert spu["spu_id"].startswith("mock_spu_")
    spu_id = spu["spu_id"]

    skus = adapter.create_skus(
        spu_id=spu_id,
        skus=[
            {"sku_id": "s1", "price_cents": 29900},
            {"sku_id": "s2", "price_cents": 31900},
        ],
    )
    assert len(skus["sku_ids"]) == 2

    img = adapter.upload_image(file_path="C:/tmp/p1.png", usage="main")
    assert img["media_id"].startswith("mock_media_")

    audit = adapter.submit_audit(spu_id=spu_id, media_ids=[img["media_id"]])
    assert audit["audit_id"].startswith("mock_audit_")

    status = adapter.query_audit_status(audit_id=audit["audit_id"])
    assert status["audit_status"] == "pass"
    assert status["reject_reason"] == ""

    link = adapter.get_product_link(spu_id=spu_id)
    assert link["product_link"].startswith("https://")


def test_log_redaction(adapter, caplog):
    with caplog.at_level(logging.INFO):
        adapter.create_spu(
            title="日志脱敏",
            category_id=1001,
            qualification=None,
            freight_template_id=1,
            purchase_limit=5,
            task_id="task-12345",
        )
    assert "task-12345" in caplog.text
    assert "mock-token" not in caplog.text
    assert TEST_SECRET not in caplog.text
