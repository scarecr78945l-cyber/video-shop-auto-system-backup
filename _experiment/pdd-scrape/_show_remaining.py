# -*- coding: utf-8 -*-
"""Show remaining products for taobao_v4 resume + which lack query images."""
import json, os, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LOG = Path(__file__).resolve().parent / "taobao_v4_results.jsonl"

con = sqlite3.connect(str(ROOT / "backend/data/db/m4-listing.db"))
pids = [r[0] for r in con.execute(
    "SELECT product_id FROM listing_tasks WHERE status='pending' ORDER BY product_id").fetchall()]
con.close()

done_ok = set()
if LOG.exists():
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r.get("ok"):
                done_ok.add(r["pid"])
        except Exception:
            pass

listing = {int(d) for d in os.listdir(str(ROOT / "backend/data/images/listing")) if d.isdigit()}
remaining = [p for p in pids if p not in done_ok]
no_query = [p for p in remaining if p not in listing]
with_query = [p for p in remaining if p in listing]
print("pending:", len(pids))
print("done ok:", len(done_ok))
print("remaining:", len(remaining))
print("  no query image (skip):", no_query)
print("  with query image (resume):", with_query)
