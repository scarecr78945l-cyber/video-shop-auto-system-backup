# -*- coding: utf-8 -*-
import os
import sys
import uuid
sys.path.insert(0, "backend")
sys.path.insert(0, "backend/tests")
from sqlalchemy import create_engine, text
from domain.report import ReportObservation, SnapshotCollector, SnapshotRepository

DB_URL = os.environ["DATABASE_URL"]
eng = create_engine(DB_URL)

with eng.begin() as c:
    t1 = int(c.execute(text("INSERT INTO app.tenants (name, scope) VALUES ('p1','internal') RETURNING id"), {}).scalar())
    t2 = int(c.execute(text("INSERT INTO app.tenants (name, scope) VALUES ('p2','internal') RETURNING id"), {}).scalar())
    a1 = int(c.execute(text("INSERT INTO app.platform_accounts (public_id, tenant_id, platform, account_key) VALUES (gen_random_uuid(), :t, 'wechat_channels', :k) RETURNING id"), {"t": t1, "k": "a1"}).scalar())
    print("t1", t1, "t2", t2, "a1", a1)

    bad = ReportObservation(
        tenant_id=t2, account_id=a1, shop_id=1, shop_listing_id=1,
        shop_listing_sku_id=None, product_id=1, campaign_id=1,
        asset_binding_id=None, granularity="campaign",
        window_start=__import__("datetime").datetime(2026,1,1,tzinfo=__import__("datetime").timezone.utc),
        window_end=__import__("datetime").datetime(2026,1,2,tzinfo=__import__("datetime").timezone.utc),
        attribution_mode="last_click", platform_version_id="x1",
        platform_updated_at=None,
        captured_at=__import__("datetime").datetime(2026,1,1,12,tzinfo=__import__("datetime").timezone.utc),
        raw_evidence=b"raw-x1")
    try:
        with c.begin_nested():
            repo = SnapshotRepository(c)
            draft = SnapshotCollector(c)._build_draft(bad)
            print("draft built ok, version_key=", draft.report_version_key)
            r = repo.write(draft)
            print("write ok?", r)
    except Exception as exc:
        print("caught:", type(exc).__name__, str(exc)[:200])
    # 事务仍可用？
    try:
        n = c.execute(text("SELECT 1")).scalar()
        print("outer tx alive, select=1 ok")
    except Exception as exc:
        print("outer tx DEAD:", type(exc).__name__, str(exc)[:150])
    c.execute(text("DELETE FROM app.platform_accounts WHERE tenant_id IN (:a,:b)"), {"a": t1, "b": t2})
    c.execute(text("DELETE FROM app.tenants WHERE id IN (:a,:b)"), {"a": t1, "b": t2})
print("done")
eng.dispose()
