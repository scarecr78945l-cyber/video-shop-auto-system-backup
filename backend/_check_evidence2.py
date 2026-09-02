# -*- coding: utf-8 -*-
"""查 #1 的证据图（多张？是否含单品图）+ 1688 详情页主图探测（用后即删）"""
import json
import sqlite3
import urllib.request

con = sqlite3.connect("data/db/m1-sourcing.db")
cur = con.cursor()
cur.execute("SELECT image_urls FROM product_source_evidence WHERE product_id=1 LIMIT 1")
row = cur.fetchone()
urls = json.loads(row[0]) if row and row[0] else []
print(f"#1 证据图 {len(urls)} 张:")
for i, u in enumerate(urls):
    print(f"  [{i}] {str(u)[:100]}")
con.close()

# 1688 详情页主图（仅探测第一张图 URL，不下单不操作——只读，风控期谨慎）
print("\n1688 detail 主图探测（只读）：")
url = "https://detail.1688.com/offer/730810156511.html"
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", "ignore")
    # 找 og:image 或首个 cbu01 图
    import re
    og = re.search(r'property="og:image" content="([^"]+)"', html)
    print("og:image:", og.group(1)[:120] if og else "无")
    imgs = re.findall(r'https://cbu01\.alicdn\.com[^"\s\\]+', html)[:3]
    print("cbu01 图:", [i[:100] for i in imgs])
except Exception as e:
    print("ERR:", str(e)[:100])
