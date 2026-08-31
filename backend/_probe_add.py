"""M4 真实上架→草稿：探测「添加商品」接口路径（最小 body，不创建有效商品）。"""
import sys

import requests

sys.path.insert(0, ".")
from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig

adapter = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
token = adapter._get_token()

# 候选路径（推断命名模式；错误响应不创建任何东西）
candidates = [
    "channels/ec/product/add",
    "channels/ec/product/add_post",
    "channels/ec/product/addproduct",
    "channels/ec/product/create",
]
minimal = {"title": "探"}  # 最小 body（必然参数错误，用于判定路径是否存在）
for path in candidates:
    url = f"https://api.weixin.qq.com/{path}?access_token={token}"
    try:
        resp = requests.post(url, json=minimal, timeout=15)
        data = resp.json()
        errcode = data.get("errcode", "?")
        errmsg = str(data.get("errmsg", ""))[:60]
        # 47001/10002 等=参数/请求错误（路径存在）；接口不存在一般返回 404 或特殊 errcode
        print(f"{path}: errcode={errcode} ({errmsg})")
    except Exception as e:
        print(f"{path}: {type(e).__name__} {str(e)[:50]}")
