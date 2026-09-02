# -*- coding: utf-8 -*-
"""查 #1 的 1688 详情链接（用于取单品主图作参考）（用后即删）"""
import sqlite3

con = sqlite3.connect("data/db/m1-sourcing.db")
cur = con.cursor()
cur.execute("SELECT id, raw_url FROM sku WHERE product_id=1 LIMIT 5")
rows = cur.fetchall()
print("sku raw_url for product 1:")
for r in rows:
    print(" ", r)
con.close()
