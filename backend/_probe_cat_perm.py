"""M4：从 product 字段读取现有商品真实类目（已开通）。"""
import json
import sys

import requests

sys.path.insert(0, ".")
from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig

a = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
token = a._get_token()


def call(path, body):
    return requests.post(f"https://api.weixin.qq.com/{path}?access_token={token}", json=body, timeout=20).json()


r = call("channels/ec/product/list/get", {"page": 0, "page_size": 5})
pids = r["product_ids"]
print("商品:", pids)
cats_set = set()
for pid in pids:
    p = call("channels/ec/product/get", {"product_id": pid})
    prod = p.get("product", {})
    cats = prod.get("cats")
    print(f"  {pid}: cats={json.dumps(cats, ensure_ascii=False)[:120]} | audit={json.dumps(p.get('audit_info'), ensure_ascii=False)[:80]}")
    if isinstance(cats, list):
        for c in cats:
            if isinstance(c, dict):
                cats_set.add(str(c.get("cat_id")))
            else:
                cats_set.add(str(c))
    elif isinstance(cats, dict):
        cats_set.add(str(cats.get("cat_id")))
print("出现过的类目 cat_id:", cats_set)
