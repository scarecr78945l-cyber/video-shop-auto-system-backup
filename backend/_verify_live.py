"""M4 live 只读验证：调官方只读接口（不提交商品，REC-004 铁律）。"""
import json
import os
import sys

import requests

sys.path.insert(0, ".")
from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig

adapter = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
token = adapter._get_token()
print("token ok, len:", len(token))

# 只读接口尝试（按官方文档命名模式；错误响应不造成任何影响）
candidates = [
    ("获取店铺基本信息", "https://api.weixin.qq.com/channels/ec/merchant/get_basic_info", {}),
    ("获取商品列表", "https://api.weixin.qq.com/channels/ec/product/list/get", {"page": 0, "page_size": 1}),
    ("获取所有类目", "https://api.weixin.qq.com/channels/ec/category/list/get", {}),
]
for name, url, body in candidates:
    try:
        resp = requests.post(url + f"?access_token={token}", json=body, timeout=15)
        data = resp.json()
        errcode = data.get("errcode", "ok")
        # 脱敏输出：只显示 errcode 和关键结构，不打印敏感数据
        if errcode == 0:
            keys = list(data.keys())[:5]
            print(f"✅ {name}: errcode=0 keys={keys}")
            # 店铺基本信息：只读打印非敏感结构
            if "merchant" in data and isinstance(data["merchant"], dict):
                m = data["merchant"]
                print(f"   主体类型字段存在: {'subject_type' in m or 'merchant_type' in m}")
        else:
            print(f"⏳ {name}: errcode={errcode} ({data.get('errmsg','')[:50]})")
    except Exception as e:
        print(f"⚠️ {name}: {type(e).__name__}: {str(e)[:60]}")
