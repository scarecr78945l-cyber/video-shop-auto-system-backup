# -*- coding: utf-8 -*-
import sqlite3
con = sqlite3.connect(r"E:\视频号上架系统\视频号上架系统\backend_backup_20260816_214116.db")
con.text_factory = lambda b: b.decode("utf-8", "replace")
cur = con.cursor()
print("total:", cur.execute("SELECT COUNT(*) FROM image_assets").fetchone()[0])
print("prompt non-empty:", cur.execute("SELECT COUNT(*) FROM image_assets WHERE prompt IS NOT NULL AND prompt != ''").fetchone()[0])
print("plan non-empty:", cur.execute("SELECT COUNT(*) FROM image_assets WHERE plan_json IS NOT NULL AND plan_json != ''").fetchone()[0])
print("status dist:", cur.execute("SELECT status,COUNT(*) FROM image_assets GROUP BY status").fetchall())
print("kind dist:", cur.execute("SELECT kind,COUNT(*) FROM image_assets GROUP BY kind").fetchall())
rows = cur.execute("SELECT id, kind, status, file_path, substr(prompt,1,90) FROM image_assets WHERE prompt IS NOT NULL AND prompt != '' LIMIT 6").fetchall()
for r in rows:
    print(r)
con.close()
