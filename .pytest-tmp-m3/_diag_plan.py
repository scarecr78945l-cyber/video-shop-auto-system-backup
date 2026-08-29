# -*- coding: utf-8 -*-
import sqlite3, json
con = sqlite3.connect(r"E:\视频号上架系统\视频号上架系统\backend_backup_20260816_214116.db")
con.text_factory = lambda b: b.decode("utf-8", "replace")
cur = con.cursor()
rows = cur.execute(
    "SELECT id, kind, position, status, file_path, plan_json FROM image_assets "
    "WHERE status IN ('approved','pending') ORDER BY updated_at DESC LIMIT 5"
).fetchall()
for r in rows:
    aid, kind, pos, st, fp, plan = r
    print("=" * 70)
    print(f"asset={aid} kind={kind} pos={pos} status={st}")
    print(f"file_path={fp}")
    try:
        p = json.loads(plan)
        print("plan top keys:", list(p.keys()) if isinstance(p, dict) else type(p))
        print("plan:", json.dumps(p, ensure_ascii=False)[:900])
    except Exception as e:
        print("plan raw:", str(plan)[:400], "| err:", e)
con.close()
