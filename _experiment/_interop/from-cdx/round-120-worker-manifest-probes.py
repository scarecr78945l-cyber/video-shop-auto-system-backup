"""Round-120: verify the negative cleanup gate and sample-manifest mappings."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("r120_workflow_tests", ROOT / "backend/tests/test_workflow_queue.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# The delivered negative test remains independent from the actual positive test.
with patch.object(module, "test_ensure_run_worker_fault_cleans_fixture", return_value=None) as positive:
    module.test_ensure_run_worker_fault_cleanup_failure_fails(None)
    print("NEGATIVE_GATE_PASSED_WITH_POSITIVE_ENTRY_DISABLED=true", flush=True)
    print("POSITIVE_ENTRY_CALL_COUNT=" + str(positive.call_count), flush=True)
    assert positive.call_count == 0

manifest_claims = {
    "backend/fixtures/ad_snapshots.json": "backend/tests/test_ads_fixtures.py",
    "backend/fixtures/ads/campaign_report_sample.json": "backend/tests/test_ads_fixtures.py",
    "backend/fixtures/alibaba_quotes.json": "backend/tests/test_p2_fixtures.py",
    "backend/fixtures/youmi.json": "backend/tests/test_p2_fixtures.py",
    "backend/fixtures/taobao_references.json": "backend/tests/test_p2_fixtures.py",
    "backend/fixtures/opportunities.json": "backend/tests/test_p2_fixtures.py",
    "backend/fixtures/doudian.json": "backend/tests/test_p2_fixtures.py",
}
for fixture, test_file in manifest_claims.items():
    fixture_path = ROOT / fixture
    test_source = (ROOT / test_file).read_text(encoding="utf-8")
    mentioned = fixture_path.name in test_source or str(fixture_path.parent).replace("\\", "/") in test_source.replace("\\", "/")
    print(f"MANIFEST_MAPPING={fixture} TEST={test_file} MENTIONED={str(mentioned).lower()}", flush=True)
