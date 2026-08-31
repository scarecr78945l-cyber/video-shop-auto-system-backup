"""M4 草稿：完全保留原商品（含标题）仅改价格——验证格式/类目。"""
import json
import sys

import requests

sys.path.insert(0, ".")
from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig

a = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
token = a._get_token()


def call(path, body):
    return requests.post(f"https://api.weixin.qq.com/{path}?access_token={token}", json=body, timeout=25).json()


r = call("channels/ec/product/list/get", {"page": 0, "page_size": 1})
pid = r["product_ids"][0]
p = call("channels/ec/product/get", {"product_id": pid})
prod = p.get("product", {})

# 完全保留标题/类目/结构，只改 SKU 价格 + 移除只读字段
draft_prod = json.loads(json.dumps(prod, ensure_ascii=False))
for k in ["product_id", "out_product_id", "spu_code", "total_sold_num", "edit_time", "status", "sub_status"]:
    draft_prod.pop(k, None)
skus = draft_prod.get("skus", [])
if isinstance(skus, list) and skus:
    s0 = dict(skus[0])
    for k in ["sku_id", "out_sku_id", "status"]:
        s0.pop(k, None)
    s0["sale_price"] = 1990
    s0["stock_num"] = 10
    draft_prod["skus"] = [s0]
# 打印 cats/attrs 摘要
print("标题:", draft_prod["title"][:30])
print("cats:", draft_prod.get("cats"))
print("cats_v2:", json.dumps(draft_prod.get("cats_v2"), ensure_ascii=False)[:150])

r2 = call("channels/ec/product/add", {"product": draft_prod})
print("errcode:", r2.get("errcode"), "|", str(r2.get("errmsg", ""))[:120])
if r2.get("errcode") == 0:
    new_pid = r2.get("product_id")
    print(f"✅ 草稿创建成功 product_id: {new_pid}")
    back = call("channels/ec/product/get", {"product_id": new_pid})
    print("回读 status:", back.get("product", {}).get("status"))
