"""M4 live 模式 _call 统一调用测试（mock HTTP；T1/T3 落地）。"""

from unittest.mock import patch

import pytest

from adapters.wechat_openapi import WechatApiError, WechatOpenApiAdapter, WechatOpenApiConfig


def _live(monkeypatch):
    monkeypatch.setenv("WECHAT_APPID", "wx-test")
    monkeypatch.setenv("WECHAT_APPSECRET", "secret-test")
    adapter = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
    adapter._token_cache = "tok"
    adapter._token_cache_expires_at = 9999999999
    return adapter


def test_live_call_success(monkeypatch):
    """① live _call 成功：POST + access_token + 返回数据。"""
    a = _live(monkeypatch)
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"errcode": 0, "product_ids": ["p1"], "total_num": 1}
        r = a._call("list_products", {"page": 0}, retry=1)
        assert r["total_num"] == 1
        url = mock_post.call_args[0][0]
        assert "access_token=tok" in url


def test_live_call_auth_error(monkeypatch):
    """② 40001 → AUTH_REQUIRED。"""
    a = _live(monkeypatch)
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"errcode": 40001, "errmsg": "invalid credential"}
        with pytest.raises(WechatApiError) as exc:
            a._call("list_products", {}, retry=1)
        assert exc.value.error_code == "AUTH_REQUIRED"


def test_live_call_rate_limit(monkeypatch):
    """③ 频控 → RATE_LIMIT。"""
    a = _live(monkeypatch)
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"errcode": 45009, "errmsg": "reach max api daily quota limit"}
        with pytest.raises(WechatApiError) as exc:
            a._call("list_products", {}, retry=1)
        assert exc.value.error_code == "RATE_LIMIT"


def test_live_call_unverified_path(monkeypatch):
    """④ 未核对接口路径 → UNEXPECTED 明确错误。"""
    a = _live(monkeypatch)
    with pytest.raises(WechatApiError) as exc:
        a._call("create_spu", {}, retry=1)
    assert exc.value.error_code == "UNEXPECTED"
    assert "T3/T4" in exc.value.message


def test_mock_still_works(monkeypatch):
    """⑤ mock 模式不受影响。"""
    a = WechatOpenApiAdapter(WechatOpenApiConfig(mode="mock"))
    r = a._call("list_products", {}, retry=1) if False else a.create_spu(
        title="测试", category_id=1, qualification=None, freight_template_id=1, purchase_limit=1
    )
    assert r["spu_id"].startswith("mock_spu_")
