"""Review actual worker fault-test gates; historical cleanup probe remains read-only."""
import importlib.util
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
old = Path(__file__).with_name("round-116-worker-gate-probe.py")
try:
    runpy.run_path(str(old), run_name="__main__")
except AssertionError as exc:
    tb = exc.__traceback__
    names = []
    while tb:
        names.append(tb.tb_frame.f_code.co_name)
        tb = tb.tb_next
    assert "test_ensure_run_worker_fault_cleans_fixture" in names, names
    print("POSITIVE_FAULT_TEST_REJECTS_SKIPPED_TENANT_DELETE=true", flush=True)
else:
    raise AssertionError("cleanup regression not detected")

spec = importlib.util.spec_from_file_location("r118_worker_test", ROOT / "backend/tests/test_workflow_queue.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
events = []


def trace(frame, event, arg):
    if frame.f_code.co_name == "poisoned_delete" and event == "exception":
        kind, exc, tb = arg
        events.append((kind.__name__, str(exc), str(frame.f_locals.get("statement"))))
    return trace


prior = sys.gettrace()
try:
    sys.settrace(trace)
    m.test_ensure_run_worker_fault_cleanup_failure_fails(None)
finally:
    sys.settrace(prior)
print("NEGATIVE_TEST_RETURNED_PASS_WITH_EXCEPTIONS=" + repr(events), flush=True)
assert any(k == "TypeError" and "NoneType" in message for k, message, stmt in events)

with patch.object(m.WorkflowQueue, "ensure_run", side_effect=RuntimeError("R118_SEED_FAILED")) as seed:
    m.test_ensure_run_worker_fault_cleanup_failure_fails(None)
    print("NEGATIVE_TEST_ACCEPTED_SEED_FAILURE=true SEED_CALLS=" + str(seed.call_count), flush=True)
    assert seed.call_count == 1
