"""Check whether the delivered fault test notices its own tenant cleanup failing."""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import sqlalchemy
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
URL = os.environ["DATABASE_URL"]
spec = importlib.util.spec_from_file_location("r116_test", ROOT / "backend/tests/test_workflow_queue.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
real_create_engine = sqlalchemy.create_engine
real_new_tenant = m._new_tenant
ids = []


def track(c):
    result = real_new_tenant(c)
    ids.append(result[0])
    return result


class Connection:
    def __init__(self, inner):
        self.inner = inner

    def execute(self, statement, params=None):
        if str(statement).startswith("DELETE FROM app.tenants") and params["t"] in ids:
            return self.inner.execute(text("SELECT 1"))
        return self.inner.execute(statement, params or {})

    def __getattr__(self, name):
        return getattr(self.inner, name)


class Engine:
    def __init__(self, *a, **kw):
        self.inner = real_create_engine(*a, **kw)

    @contextmanager
    def begin(self):
        with self.inner.begin() as c:
            yield Connection(c)

    def __getattr__(self, name):
        return getattr(self.inner, name)


verify = real_create_engine(URL)
try:
    with patch.object(m, "_new_tenant", track), patch.object(sqlalchemy, "create_engine", Engine):
        m.test_ensure_run_worker_fault_cleans_fixture(None)
    with verify.connect() as c:
        remains = sum(c.execute(text("SELECT count(*) FROM app.tenants WHERE id=:t"), {"t": tid}).scalar() for tid in ids)
    print(f"DELIVERED_FAULT_TEST_PASSED=true OWNED_TENANTS_BEFORE_REVIEWER_CLEANUP={remains}")
    assert remains == 1
finally:
    with verify.begin() as c:
        for tid in ids:
            c.execute(text("DELETE FROM app.workflow_steps WHERE run_id IN (SELECT id FROM app.workflow_runs WHERE tenant_id=:t)"), {"t": tid})
            c.execute(text("DELETE FROM app.workflow_runs WHERE tenant_id=:t"), {"t": tid})
            c.execute(text("DELETE FROM app.tenants WHERE id=:t"), {"t": tid})
    with verify.connect() as c:
        remains = sum(c.execute(text("SELECT count(*) FROM app.tenants WHERE id=:t"), {"t": tid}).scalar() for tid in ids)
    print(f"OWNED_TENANTS_AFTER_REVIEWER_CLEANUP={remains}")
    assert remains == 0
    verify.dispose()
