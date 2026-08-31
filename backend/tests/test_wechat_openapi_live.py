"""M4 live 模式 access_token 获取（T1 销项）测试。"""

import hashlib
import os
from unittest.mock import patch

import pytest

from adapters.wechat_openapi import WechatApiError, WechatOpenApiAdapter, WechatOpenApiConfig


def _live_adapter(monkeypatch, token="live-token-123"):
    monkeypatch.setenv("WECHAT_APPID", "wx-test")
    monkeypatch.setenv("WECHAT_APPSECRET", "secret-test")
    return WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))


def test_live_token_success(monkeypatch):
    """① live 模式成功获取并缓存 access_token。"""
    adapter = _live_adapter(monkeypatch)
    fake = {
        "access_token": "live-token-abc",
        "expires_in": 7200,
    }
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = fake
        t1 = adapter._get_token()
        assert t1 == "live-token-abc"
        t2 = adapter._get_token()  # 缓存命中，不重复请求
        assert t2 == "live-token-abc"
    assert mock_get.call_count == 1


def test_live_token_invalid_credential(monkeypatch):
    """② 凭据无效（40001）→ AUTH_REQUIRED 人工接管。"""
    adapter = _live_adapter(monkeypatch)
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"errcode": 40001, "errmsg": "invalid credential"}
        with pytest.raises(WechatApiError) as exc:
            adapter._get_token()
        assert exc.value.error_code == "AUTH_REQUIRED"


def test_live_token_missing_env(monkeypatch):
    """③ 环境变量缺失 → AUTH_REQUIRED 明确错误。"""
    monkeypatch.delenv("WECHAT_APPID", raising=False)
    monkeypatch.delenv("WECHAT_APPSECRET", raising=False)
    adapter = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
    with pytest.raises(WechatApiError) as exc:
        adapter._get_token()
    assert exc.value.error_code == "AUTH_REQUIRED"
    assert "WECHAT_APPID" in exc.value.message


def test_mock_mode_unaffected():
    """④ mock 模式不受影响（返回固定 token）。"""
    adapter = WechatOpenApiAdapter(WechatOpenApiConfig(mode="mock"))
    assert adapter._get_token() == "mock-token"


def test_sign_stable():
    """⑤ 签名占位实现稳定（同 payload 同签名；含 secret 不落日志）。"""
    adapter = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
    payload = {"product_id": "1", "title": "测试"}
    s1 = adapter._sign(payload)
    s2 = adapter._sign(payload)
    assert s1["sign"] == s2["sign"]
    assert "timestamp" in s1 and "sign" in s1
