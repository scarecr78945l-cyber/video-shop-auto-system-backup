# -*- coding: utf-8 -*-
"""临时核查 v2：products 与证据表联查店铺名来源（用后即删）"""
import sqlite3

con = sqlite3.connect("data/db/m1-sourcing.db")
cur = con.cursor()

cur.execute("PRAGMA table_info(products)")
print("products cols:", [r[1] for r in cur.fetchall()])
cur.execute("PRAGMA table_info(product_source_evidence)")
print("evidence cols:", [r[1] for r in cur.fetchall()])

# products + 证据（来源）
cur.execute("""
    SELECT p.id, p.title, p.score, p.state,
           (SELECT GROUP_CONCAT(e.source || ':' || e.board) FROM product_source_evidence e WHERE e.product_id = p.id) AS src
    FROM products p ORDER BY p.score DESC LIMIT 25
""")
cols = [d[0] for d in cur.description]
for r in cur.fetchall():
    d = dict(zip(cols, r))
    print(f"  #{d['id']:>4} [{d['score']}] {str(d['title'])[:45]} | {d['src']}")
con.close()
