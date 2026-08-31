# -*- coding: utf-8 -*-
"""P-030 一次性清理：删除抖店飙升榜（店铺维度）污染的 products/evidence/events/runs（用后即删）"""
import sqlite3

con = sqlite3.connect("data/db/m1-sourcing.db")
cur = con.cursor()

# 1) 找飙升榜证据对应的商品
cur.execute("""
    SELECT DISTINCT product_id FROM product_source_evidence
    WHERE source = 'doudian' AND board = '飙升榜'
""")
shop_product_ids = [r[0] for r in cur.fetchall()]
print(f"飙升榜污染商品: {len(shop_product_ids)} 个 (ids: {shop_product_ids[:10]}...)")

if shop_product_ids:
    ph = ",".join("?" * len(shop_product_ids))
    # 2) 删除这些商品的 evidence
    cur.execute(f"DELETE FROM product_source_evidence WHERE product_id IN ({ph})", shop_product_ids)
    print(f"  删除 evidence: {cur.rowcount}")
    # 3) 删除这些商品（fingerprint claims 级联；library 为全局指纹库按指纹去重，不删）
    cur.execute(f"DELETE FROM product_fingerprint_claims WHERE product_id IN ({ph})", shop_product_ids)
    cur.execute(f"DELETE FROM products WHERE id IN ({ph})", shop_product_ids)
    print(f"  删除 products: {cur.rowcount}")

# 4) 删除飙升榜的 collection_events（board='飙升榜'）
cur.execute("DELETE FROM source_collection_events WHERE board = '飙升榜'")
print(f"  删除飙升榜 events: {cur.rowcount}")

# 5) 删除 source_runs 中 board='飙升榜' 的记录（注意 board 字段可能是 'pipeline'，用 evidence 反查）
cur.execute("SELECT id FROM source_runs WHERE source='doudian' AND board='pipeline'")
pipeline_run_ids = [r[0] for r in cur.fetchall()]
# 看 runs 里 board 取值
cur.execute("SELECT id, source, board, item_count FROM source_runs ORDER BY id DESC LIMIT 12")
for r in cur.fetchall():
    print("  run:", r)

con.commit()

# 6) 最终统计
cur.execute("SELECT COUNT(*) FROM products")
print(f"\n剩余 products: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM product_source_evidence")
print(f"剩余 evidence: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM source_collection_events")
print(f"剩余 events: {cur.fetchone()[0]}")
cur.execute("""
    SELECT p.id, p.title, p.score, p.state,
           (SELECT GROUP_CONCAT(e.source || ':' || e.board) FROM product_source_evidence e WHERE e.product_id = p.id) AS src
    FROM products p ORDER BY p.score DESC LIMIT 12
""")
for r in cur.fetchall():
    print(f"  #{r[0]:>4} [{r[2]}] {str(r[1])[:45]} | {r[3]} | {r[4]}")
con.close()
