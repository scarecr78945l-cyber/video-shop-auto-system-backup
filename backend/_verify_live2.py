"""M4 live 只读验证 v2：商品/类目数量（脱敏统计）。"""
import sys

import requests

sys.path.insert(0, ".")
from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig

adapter = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
token = adapter._get_token()

r = requests.post("https://api.weixin.qq.com/channels/ec/product/list/get" + f"?access_token={token}", json={"page": 0, "page_size": 1}, timeout=15)
d = r.json()
print("商品总数 total_num:", d.get("total_num"), "(只读统计，不打印商品 ID)")
if d.get("total_num", 0) > 0:
    print("✅ 店铺存在真实商品——M4 live 可读已验证")

r2 = requests.post("https://api.weixin.qq.com/channels/ec/category/list/get" + f"?access_token={token}", json={}, timeout=15)
d2 = r2.json()
cats = d2.get("list", [])
print("类目总数:", len(cats))
# 类目名脱敏抽样（前 8 个，用于核对白名单）
for c in cats[:8]:
    if isinstance(c, dict):
        print("  类目:", str(c.get("name", c.get("category_name", "?")))[:30])
