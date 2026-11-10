"""Assert the submitted fault gate uses the real entry and rejects seed failure."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import mock
import uuid

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("r104_idp", ROOT / "backend/tests/test_auth_idp_chain.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
engine = create_engine(os.environ["DATABASE_URL"])
real_run, real_entry = m._run_chain, m.test_idp_chain_real_write

def counts(uid):
    with engine.connect() as c:
        return [c.execute(text(q), {"i": uid}).scalar() for q in (
            "SELECT count(*) FROM auth.user WHERE id=:i",
            "SELECT count(*) FROM auth.session WHERE user_id=:i",
            "SELECT count(*) FROM auth.account WHERE user_id=:i")]

for mode in ("nonzero", "partial", "timeout"):
    owned = {}

    def observe_seed(**kwargs):
        owned["email"] = kwargs["fixture_email"]
        r, out, err = real_run(**kwargs)
        assert r.returncode == 0, err
        owned["id"] = m._parse(out)["USER_ID"]
        uuid.UUID(owned["id"])
        owned["before"] = counts(owned["id"])
        assert owned["before"] == [1, 2, 1]
        return r, out, err

    def observe_entry(conn):
        owned["called"] = True
        try:
            return real_entry(conn)
        except Exception as exc:
            owned["error"] = type(exc).__name__
            owned["message"] = str(exc)
            raise

    try:
        with engine.connect() as c:
            tx = c.begin()
            try:
                with mock.patch.object(m, "_run_chain", observe_seed), mock.patch.object(m, "test_idp_chain_real_write", observe_entry):
                    m.test_idp_chain_failure_path_cleans_up(c, mode)
            finally:
                tx.rollback()
        assert owned["called"]
        assert owned["error"] == ("TimeoutExpired" if mode == "timeout" else "AssertionError")
        if mode == "nonzero":
            assert "rc=17" in owned["message"]
        after = counts(owned["id"])
        assert after == [0, 0, 0]
        print("REAL_GATE_PASS=" + json.dumps({"mode": mode, "entry_called": True, "before": owned["before"], "after": after, "error": owned["error"]}))
    finally:
        if owned.get("email"):
            m._cleanup_user_by_email(owned["email"])

for seed in ("rc17", "exception", "missing_id"):
    def failed_seed(**kwargs):
        if seed == "exception":
            raise AssertionError("r104 seed failed")
        return subprocess.CompletedProcess([], 17 if seed == "rc17" else 0), "", "r104 seed failed"

    for mode in ("nonzero", "partial", "timeout"):
        with engine.connect() as c, mock.patch.object(m, "_run_chain", failed_seed):
            try:
                m.test_idp_chain_failure_path_cleans_up(c, mode)
            except AssertionError:
                print("SEED_REJECTED=" + json.dumps({"seed": seed, "mode": mode}))
            else:
                raise AssertionError(f"seed accepted: {seed}/{mode}")

for mode in ("nonzero", "partial", "timeout"):
    def sentinel(conn):
        raise RuntimeError("r104 real entry sentinel")
    with engine.connect() as c, mock.patch.object(m, "test_idp_chain_real_write", sentinel):
        try:
            m.test_idp_chain_failure_path_cleans_up(c, mode)
        except RuntimeError as exc:
            assert str(exc) == "r104 real entry sentinel"
            print("SENTINEL_PROPAGATED=" + mode)
        else:
            raise AssertionError("real entry not used")
engine.dispose()
print("R104_GATE_PROBE=PASS")
