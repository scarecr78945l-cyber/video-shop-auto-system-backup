"""Round-122: prove whether the cleanup mutation reaches a DELETE statement."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("r122_workflow_tests", ROOT / "backend/tests/test_workflow_queue.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

statements = []


def trace(frame, event, arg):
    if frame.f_code.co_name == "poisoned_delete" and event == "call":
        statements.append(str(frame.f_locals.get("statement")))
    return trace


prior = sys.gettrace()
try:
    sys.settrace(trace)
    module.test_ensure_run_worker_fault_cleanup_failure_fails(None)
finally:
    sys.settrace(prior)

target_deletes = [s for s in statements if s.startswith("DELETE FROM app.tenants")]
print("POISONED_EXECUTE_STATEMENTS=" + repr(statements), flush=True)
print("TARGET_DELETE_CALLS=" + str(len(target_deletes)), flush=True)
assert len(target_deletes) == 0

module.test_ensure_run_worker_seed_failure_propagates(None)
print("SEED_FAILURE_TEST_RETURNED_NORMALLY=true", flush=True)
