# -*- coding: utf-8 -*-
"""只读采样旧系统备份库 AI 生成物：文案 + 生图 prompt/plan。零写入、零密钥。"""
import sqlite3, json

DB = r"E:\视频号上架系统\视频号上架系统\backend_backup_20260816_214116.db"
con = sqlite3.connect(DB)
con.text_factory = lambda b: b.decode("utf-8", "replace")
cur = con.cursor()

print("===== 文案样本（products.ai_title / ai_detail）=====")
rows = cur.execute(
    "SELECT id, name, opportunity_category, material_result, sku_result, ai_title, ai_detail "
    "FROM products WHERE ai_title IS NOT NULL AND ai_title != '' AND ai_detail IS NOT NULL AND ai_detail != '' "
    "ORDER BY updated_at DESC LIMIT 6"
).fetchall()
for r in rows:
    pid, name, cat, mat, sku, title, detail = r
    print("-" * 60)
    print(f"id={pid} cat={cat}")
    print(f"name={str(name)[:120]}")
    print(f"material={str(mat)[:80]}")
    print(f"sku={str(sku)[:150]}")
    print(f"ai_title={str(title)[:200]}")
    print(f"ai_detail={str(detail)[:500]}")

print()
print("===== 生图样本（image_assets.prompt / plan_json / file_path）=====")
rows = cur.execute(
    "SELECT id, batch_id, kind, position, prompt, plan_json, file_path, status "
    "FROM image_assets WHERE prompt IS NOT NULL AND prompt != '' "
    "ORDER BY updated_at DESC LIMIT 8"
).fetchall()
for r in rows:
    aid, bid, kind, pos, prompt, plan, fp, st = r
    print("-" * 60)
    print(f"asset={aid} batch={bid} kind={kind} pos={pos} status={st}")
    print(f"prompt={str(prompt)[:260]}")
    print(f"file_path={str(fp)[:200]}")
    try:
        plan_obj = json.loads(plan) if plan else {}
        print(f"plan_keys={list(plan_obj.keys())[:12]}")
        print(f"plan={json.dumps(plan_obj, ensure_ascii=False)[:400]}")
    except Exception as e:
        print(f"plan_err={e}")

print()
print("===== image_assets status 分布 =====")
for row in cur.execute("SELECT status, COUNT(*) FROM image_assets GROUP BY status ORDER BY 2 DESC").fetchall():
    print(row)
print("===== image_batches mode/status 分布 =====")
for row in cur.execute("SELECT mode, status, COUNT(*) FROM image_batches GROUP BY mode, status ORDER BY 3 DESC").fetchall():
    print(row)
con.close()
