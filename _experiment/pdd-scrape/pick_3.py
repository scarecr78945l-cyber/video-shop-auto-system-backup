# -*- coding: utf-8 -*-
"""选 3 个不同类目代表商品（用后即删）"""
import sqlite3

con = sqlite3.connect("../../backend/data/db/m1-sourcing.db")
cur = con.cursor()
cur.execute(
    "SELECT p.id, p.title, p.category FROM products p "
    "WHERE p.state='pool' AND p.real_cost IS NOT NULL "
    "AND p.category IN ('厨房用品','个护清洁','办公文具') ORDER BY p.id"
)
for r in cur.fetchall():
    print(f"#{r[0]} [{r[2]}] {r[1][:40]}")
con.close()
