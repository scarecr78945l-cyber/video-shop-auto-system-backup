# -*- coding: utf-8 -*-
"""M4 素材达标复核：对 65 个 pending 上架任务的当前素材（main_0..4.png + detail_0.png）
重跑 ListingGate，输出通过率。只读，不建任务、不改库（P-041 纪律：演练不得污染正式库）。"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from services.listing_gate import ListingGate, ListingCandidate, PurchaseSettings, SkuInput  # noqa: E402

LISTING = ROOT / "backend" / "data" / "images" / "listing"
DB_M4 = ROOT / "backend" / "data" / "db" / "m4-listing.db"
DB_M1 = ROOT / "backend" / "data" / "db" / "m1-sourcing.db"

con = sqlite3.connect(str(DB_M4))
pids = [r[0] for r in con.execute(
    "SELECT product_id FROM listing_tasks WHERE status='pending' ORDER BY product_id").fetchall()]
con.close()
con1 = sqlite3.connect(str(DB_M1))
meta = {r[0]: (r[1], r[2], r[3], r[4]) for r in con1.execute(
    "SELECT id, title, category, real_cost, suggested_price FROM products").fetchall()}
con1.close()

gate = ListingGate()
passed = []
failed = []
for pid in pids:
    title, category, cost, price = meta.get(pid, ("", "家居日用", 1.0, 9.9))
    d = LISTING / str(pid)
    mains = [str(d / f"main_{i}.png") for i in range(5) if (d / f"main_{i}.png").exists()]
    details = [str(d / "detail_0.png")] if (d / "detail_0.png").exists() else []
    if len(mains) < 5 or not details:
        # 无素材 → 模拟 intake 占位（与门禁口径一致），并标记缺真实素材
        failed.append((pid, "素材不足", len(mains), len(details)))
        continue
    cand = ListingCandidate(
        product_id=pid,
        title=(title or "")[:35],
        category_id=0,
        category_name=category or "家居日用",
        qualification={"qualification_id": f"SIM-{pid}", "expires_at": "2026-12-31"},
        main_images=mains,
        detail_images=details,
        skus=[SkuInput(code=f"P{pid}-S1",
                       cost_cents=int(round(float(cost or 1) * 100)),
                       price_cents=int(round(float(price or 9.9) * 100)))],
        purchase_settings=PurchaseSettings(purchase_limit={"per_user": 2, "period": "month"},
                                           freight_template_id="1",
                                           after_sale="支持7天无理由退换货"),
        missing_attrs=None,
    )
    gr = gate.evaluate(cand)
    if gr.passed:
        passed.append(pid)
    else:
        codes = gr.rejected_reason_codes
        failed.append((pid, codes, len(mains), len(details)))

print(f"pending 任务 {len(pids)}")
print(f"门禁通过: {len(passed)} → {passed}")
print(f"未通过/缺素材: {len(failed)}")
for f in failed:
    print(" ", f)
