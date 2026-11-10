"""Inject a subprocess failure after a real KEEP_USER run; clean our UUID."""
import importlib.util
import json
import os
from pathlib import Path
from sqlalchemy import create_engine, text

root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("r98_test", root / "backend/tests/test_auth_idp_chain.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
engine = create_engine(os.environ["DATABASE_URL"])
uid = None
original = module._run_chain
try:
    result, out, err = original(keep_user=True)
    assert result.returncode == 0
    parsed = module._parse(out)
    uid = parsed.get("KEPT_USER_ID") or parsed.get("USER_ID")
    assert uid
    result.returncode = 1
    module._run_chain = lambda **kwargs: (result, out, "r98 injected failure after real IdP write")
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            module.test_idp_chain_real_write(conn)
        except AssertionError:
            print("INJECTED_ASSERTION_REACHED=true")
        finally:
            tx.rollback()
    with engine.connect() as fresh:
        counts = [fresh.execute(text(f"SELECT count(*) FROM auth.{table} WHERE {column}=:i"), {"i": uid}).scalar_one()
                  for table, column in [("user", "id"), ("session", "user_id"), ("account", "user_id")]]
        print("FAILURE_PATH_REMAINING=" + json.dumps(counts))
finally:
    module._run_chain = original
    if uid:
        module._cleanup_user_committed(uid)
        module._assert_no_remaining(uid)
        print("FAULT_PROBE_CLEANED=true")
    engine.dispose()
