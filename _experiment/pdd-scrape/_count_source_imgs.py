# -*- coding: utf-8 -*-
"""Count real source images per product across all evidence sources."""
import json, sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
# get pending pids first
con4 = sqlite3.connect(str(ROOT / "backend/data/db/m4-listing.db"))
pids = [r[0] for r in con4.execute("SELECT product_id FROM listing_tasks WHERE status='pending'").fetchall()]
con4.close()
pid_set = set(pids)

con = sqlite3.connect(str(ROOT / "backend/data/db/m1-sourcing.db"))
con.row_factory = sqlite3.Row

rows = con.execute("""SELECT product_id, source, image_urls FROM product_source_evidence
                      WHERE product_id IN (%s)
                      ORDER BY product_id""" % ",".join("?" * len(pids)), tuple(pids)).fetchall()
con.close()

by_pid = {}
src_count = Counter()
for r in rows:
    if r["product_id"] not in pid_set:
        continue
    urls = json.loads(r["image_urls"]) if r["image_urls"] else []
    by_pid.setdefault(r["product_id"], {})
    n = len(urls)
    by_pid[r["product_id"]][r["source"]] = max(by_pid[r["product_id"]].get(r["source"], 0), n)
    src_count[r["source"]] += 1

print("pending pids:", len(pid_set))
print("evidence sources coverage:", dict(src_count))
print()
print("per-pid max source images (source -> count):")
for pid in sorted(pid_set):
    d = by_pid.get(pid, {})
    if d:
        total = max(d.values())
        print(f"  #{pid}: {d}  (max {total})")
    else:
        print(f"  #{pid}: NO EVIDENCE")
