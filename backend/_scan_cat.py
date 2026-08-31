"""M4 草稿：并发扫描类目名找家居/收纳/日用/厨房/宠物（detail 接口）。"""
import asyncio
import sys

import requests

sys.path.insert(0, ".")
from adapters.wechat_openapi import WechatOpenApiAdapter, WechatOpenApiConfig

a = WechatOpenApiAdapter(WechatOpenApiConfig(mode="live"))
token = a._get_token()

# 全部类目 ID
r = requests.post(f"https://api.weixin.qq.com/channels/ec/category/list/get?access_token={token}", json={}, timeout=15).json()
cat_ids = [str(c["cat_id"]) for c in r.get("list", [])]
print("类目总数:", len(cat_ids))

TARGET = ["收纳", "家居", "日用", "厨房", "宠物", "清洁", "整理", "家清", "生活", "挂", "架"]
hits = []


async def probe(cid):
    try:
        rr = await asyncio.to_thread(
            requests.post,
            f"https://api.weixin.qq.com/channels/ec/category/detail?access_token={token}",
            json={"cat_id": cid}, timeout=10,
        )
        d = rr.json()
        if d.get("errcode") == 0:
            name = d.get("info", {}).get("name", "")
            if any(k in name for k in TARGET):
                hits.append((cid, name))
    except Exception:
        pass


async def main():
    # 并发 20 个
    sem = asyncio.Semaphore(20)

    async def bounded(cid):
        async with sem:
            await probe(cid)

    await asyncio.gather(*[bounded(cid) for cid in cat_ids])
    print(f"\n命中 {len(hits)} 个:")
    for cid, name in hits[:30]:
        print(f"  {cid}: {name}")


asyncio.run(main())
