"""Replay actual cleanup branches after a real IdP write; preserve original files."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location("idp_under_review", ROOT / "backend/tests/test_auth_idp_chain.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
original = mod._run_chain
engine = create_engine(os.environ["DATABASE_URL"])

for mode in ("nonzero", "partial", "timeout"):
    owned = {}

    def injected(*, keep_user=False, fixture_email=None):
        owned["email"] = fixture_email
        result, out, err = original(keep_user=True, fixture_email=fixture_email)
        assert result.returncode == 0, err
        owned["id"] = mod._parse(out)["USER_ID"]
        with engine.connect() as c:
            owned["before"] = [c.execute(text(q), {"i": owned["id"]}).scalar() for q in (
                "SELECT count(*) FROM auth.user WHERE id=:i",
                "SELECT count(*) FROM auth.session WHERE user_id=:i",
                "SELECT count(*) FROM auth.account WHERE user_id=:i")]
        if mode == "timeout":
            raise subprocess.TimeoutExpired("cdx-injected-after-real-write", 180)
        if mode == "nonzero":
            result.returncode = 17
            return result, "", "cdx injected nonzero exit"
        return result, "SIGNUP_OK=true\n", ""

    mod._run_chain = injected
    try:
        with engine.connect() as c:
            tx = c.begin()
            try:
                mod.test_idp_chain_real_write(c)
            except Exception as exc:
                print("FAULT=" + json.dumps({"mode": mode, "type": type(exc).__name__,
                    "sqlstate": getattr(getattr(exc, "orig", None), "pgcode", None),
                    "original_context": type(exc.__context__).__name__, "before": owned.get("before")}))
            else:
                raise AssertionError("fault must surface")
            finally:
                tx.rollback()
        with engine.connect() as c:
            counts = [c.execute(text(q), {"i": owned["id"]}).scalar() for q in (
                "SELECT count(*) FROM auth.user WHERE id=:i",
                "SELECT count(*) FROM auth.session WHERE user_id=:i",
                "SELECT count(*) FROM auth.account WHERE user_id=:i")]
            assert counts == [0, 0, 0], counts
            print("AFTER=" + json.dumps({"mode": mode, "rows": counts}))
    finally:
        mod._run_chain = original
        if owned.get("email"):
            mod._cleanup_user_by_email(owned["email"])
# The submitted failure test also accepts a seed that never succeeds.
saved_run = mod.subprocess.run
try:
    mod.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 17, b"", b"injected seed failure")
    mod.test_idp_chain_failure_path_cleans_up()
    print("FAILURE_TEST_ACCEPTED_FAILED_SEED=true")
finally:
    mod.subprocess.run = saved_run
engine.dispose()
