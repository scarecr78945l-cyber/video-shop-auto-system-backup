"""M4 草稿前置：检查现有商品结构找类目（脱敏打印 key）。"""
import json
import sys

import requests

sys.path.insert(0, ".")
from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig

a = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
token = a._get_token()


def call(path, body):
    return requests.post(f"https://api.weixin.qq.com/{path}?access_token={token}", json=body, timeout=20).json()


r = call("channels/ec/product/list/get", {"page": 0, "page_size": 1})
pid = r["product_ids"][0]
p = call("channels/ec/product/get", {"product_id": pid})
info = p.get("info", {})
# 脱敏：打印非敏感字段的结构（值截断）
for k, v in info.items():
    if isinstance(v, (dict, list)):
        print(f"{k}: {type(v).__name__} len={len(v)} 样例={json.dumps(v, ensure_ascii=False)[:120]}")
    elif k in ("title", "sub_title"):
        print(f"{k}: {str(v)[:40]}")
    else:
        print(f"{k}: {str(v)[:40]}")
