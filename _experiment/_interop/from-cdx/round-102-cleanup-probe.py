"""Independent R100-1 replay against the actual submitted test entry points."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import mock

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("r102_idp", ROOT / "backend/tests/test_auth_idp_chain.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
engine = create_engine(os.environ["DATABASE_URL"])
original = m._run_chain

def counts(uid):
    with engine.connect() as c:
        return [c.execute(text(q), {"i": uid}).scalar() for q in (
            "SELECT count(*) FROM auth.user WHERE id=:i",
            "SELECT count(*) FROM auth.session WHERE user_id=:i",
            "SELECT count(*) FROM auth.account WHERE user_id=:i")]

for mode in ("nonzero", "partial", "timeout"):
    owned = {}

    def injected(*, keep_user=False, fixture_email=None):
        owned["email"] = fixture_email
        r, out, err = original(keep_user=True, fixture_email=fixture_email)
        assert r.returncode == 0, err
        owned["id"] = m._parse(out)["USER_ID"]
        owned["before"] = counts(owned["id"])
        assert owned["before"] == [1, 2, 1]
        if mode == "timeout":
            raise subprocess.TimeoutExpired("r102-injected", 180)
        if mode == "nonzero":
            r.returncode = 17
            return r, "", "r102 injected nonzero"
        return r, "SIGNUP_OK=true\n", ""

    try:
        with mock.patch.object(m, "_run_chain", injected), engine.connect() as c:
            tx = c.begin()
            try:
                m.test_idp_chain_real_write(c)
            except (AssertionError, subprocess.TimeoutExpired) as exc:
                assert isinstance(exc, subprocess.TimeoutExpired if mode == "timeout" else AssertionError)
                if mode == "nonzero":
                    assert "rc=17" in str(exc)
                print("ACTUAL_BRANCH=" + json.dumps({"mode": mode, "error": type(exc).__name__, "before": owned["before"]}))
            else:
                raise AssertionError("Expected original fault")
            finally:
                tx.rollback()
        after = counts(owned["id"])
        assert after == [0, 0, 0], after
        print("AFTER=" + json.dumps({"mode": mode, "rows": after}))
    finally:
        if owned.get("email"):
            m._cleanup_user_by_email(owned["email"])

# These calls exercise the submitted parameterized test, not its helper alone.
for mode in ("nonzero", "partial", "timeout"):
    with mock.patch.object(m, "_run_chain", return_value=(subprocess.CompletedProcess([], 17), "", "r102 seed failed")):
        try:
            m.test_idp_chain_failure_path_cleans_up(mode)
        except AssertionError:
            accepted = False
        else:
            accepted = True
        print("FAILED_SEED_ACCEPTED=" + json.dumps({"mode": mode, "accepted": accepted}))

# A mutation checks whether the fault test depends on the real test entry.
called = []
def sentinel(conn):
    called.append(True)
    raise RuntimeError("real entry sentinel")
with mock.patch.object(m, "test_idp_chain_real_write", sentinel), mock.patch.object(m, "_run_chain", return_value=(subprocess.CompletedProcess([], 17), "", "seed failed")):
    m.test_idp_chain_failure_path_cleans_up("nonzero")
print("REAL_ENTRY_CALLED=" + json.dumps(bool(called)))
engine.dispose()
