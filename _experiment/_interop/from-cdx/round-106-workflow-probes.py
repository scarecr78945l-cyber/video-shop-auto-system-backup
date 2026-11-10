"""Focused queue contract probes; own fixtures only, rollback or exact cleanup."""
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from domain.workflow import WorkflowQueue, compute_run_key, compute_step_action_key

engine = create_engine(os.environ["DATABASE_URL"])
def emit(key, value):
    print(key + "=" + json.dumps(value, default=str))

def new_run(c, tid, tpub):
    return WorkflowQueue(c).ensure_run(tenant_id=tid, tenant_public_id=tpub,
        run_type="listing_flow", idempotency_key="run:v1:" + uuid.uuid4().hex,
        trigger_type="manual", trigger_public_id=str(uuid.uuid4()),
        schedule_window="w1", policy_version_id="p1")[0]

def step(c, tid, rid):
    return WorkflowQueue(c).enqueue_step(tenant_id=tid, run_id=rid,
        step_type="listing_submit", action_idempotency_key="step:v1:" + uuid.uuid4().hex)

def state(c, sid):
    return dict(c.execute(text("SELECT status,attempt,gate_result FROM app.workflow_steps WHERE id=:i"), {"i": sid}).mappings().one())

t = "00000000-0000-0000-0000-000000000001"
r = "00000000-0000-0000-0000-000000000002"
target = "00000000-0000-0000-0000-000000000003"
key = compute_step_action_key(t, r, "listing_submit", "product_submit_audit", target)
expected = "step:v1:5e47863b2530cda2957f894411abb214bbbf811e9c8ff42f274185c31954d614"
emit("GOLDEN_STEP", {"actual": key, "expected": expected, "equal": key == expected, "length": len(key)})
emit("COLON_COLLISION", compute_step_action_key(t,r,"a:b","c") == compute_step_action_key(t,r,"a","b:c"))
expected_run = "run:v1:" + hashlib.sha256(f"manual|{target}|w1|p1".encode()).hexdigest()
emit("RUN_KEY_MATCH", compute_run_key(t,"manual",target,"w1","p1") == expected_run)

with engine.connect() as c:
    tx = c.begin()
    try:
        tid, tpub = c.execute(text("INSERT INTO app.tenants(name,scope) VALUES (:n,'internal') RETURNING id,public_id"), {"n": "cdx-r106-"+uuid.uuid4().hex}).one()
        q = WorkflowQueue(c)
        rid = new_run(c, tid, str(tpub))
        with c.begin_nested() as sp:
            try:
                q.enqueue_step(tenant_id=tid,run_id=rid,step_type="listing_submit",action_idempotency_key=key)
            except Exception as exc:
                emit("GENERATED_KEY_INSERT_SQLSTATE", getattr(getattr(exc,"orig",None),"pgcode",None))
                sp.rollback()
        sid = step(c,tid,rid)
        token = q.claim(run_id=rid)
        emit("FIRST_CLAIM", token)
        q.gate_retry(step_id=sid,attempt=token[1],error_code="NO_MATCH")
        emit("NO_MATCH_AFTER_FIRST_FAILURE", state(c,sid))

        rid = new_run(c,tid,str(tpub)); sid = step(c,tid,rid)
        _, a = q.claim(run_id=rid)
        q.gate_retry(step_id=sid,attempt=a,error_code="TIMEOUT")
        emit("TIMEOUT_RETRY_STATE", state(c,sid))
        emit("TIMEOUT_IMMEDIATE_RECLAIM", q.claim(run_id=rid))

        rid = new_run(c,tid,str(tpub)); sid = step(c,tid,rid)
        _, a = q.claim(run_id=rid)
        q.gate_retry(step_id=sid,attempt=a,error_code="RATE_LIMIT",gate_result={"retry_at":"2000-01-01T00:00:00Z"})
        emit("RATE_LIMIT_PAST_OVERRIDE_RECLAIM", q.claim(run_id=rid))

        rid = new_run(c,tid,str(tpub)); sid = step(c,tid,rid)
        _, a = q.claim(run_id=rid)
        q.fail(step_id=sid,attempt=a,error_code="AUTH_REQUIRED")
        emit("AUTH_REQUIRED_STATE", state(c,sid))

        rid = new_run(c,tid,str(tpub)); sid = step(c,tid,rid)
        _, a = q.claim(run_id=rid)
        q.complete(step_id=sid,attempt=a,evidence_ref="cdx:r106")
        emit("COMPLETED_STEP_RUN_STATUS", c.execute(text("SELECT status FROM app.workflow_runs WHERE id=:r"),{"r":rid}).scalar())

        rid = new_run(c,tid,str(tpub)); sid = step(c,tid,rid)
        c.execute(text("UPDATE app.workflow_runs SET status='cancelled' WHERE id=:r"),{"r":rid})
        emit("CANCELLED_RUN_CLAIM", q.claim(run_id=rid))
    finally:
        tx.rollback()
        emit("TRANSACTION_PROBES_ROLLED_BACK", True)

# Force both SELECT-before-INSERT reads to finish before either INSERT.
with engine.begin() as c:
    tid, tpub = c.execute(text("INSERT INTO app.tenants(name,scope) VALUES (:n,'internal') RETURNING id,public_id"), {"n":"cdx-r106-race-"+uuid.uuid4().hex}).one()
barrier = threading.Barrier(2)
shared_key = "run:v1:" + uuid.uuid4().hex
class SyncedConnection:
    def __init__(self,c): self.c = c
    def execute(self,stmt,params):
        result = self.c.execute(stmt,params)
        if str(stmt).startswith("SELECT id FROM app.workflow_runs"):
            row = result.first()
            barrier.wait(timeout=10)
            class Result:
                def first(self): return row
            return Result()
        return result

def worker(_):
    with engine.connect() as c:
        tx=c.begin()
        try:
            result=WorkflowQueue(SyncedConnection(c)).ensure_run(tenant_id=tid,tenant_public_id=str(tpub),
                run_type="listing_flow",idempotency_key=shared_key,trigger_type="manual",trigger_public_id=t,
                schedule_window="w1",policy_version_id="p1")
            tx.commit()
            return {"result":result}
        except Exception as exc:
            tx.rollback()
            return {"error":type(exc).__name__,"sqlstate":getattr(getattr(exc,"orig",None),"pgcode",None)}
try:
    with ThreadPoolExecutor(max_workers=2) as pool:
        emit("CONCURRENT_ENSURE_RUN", list(pool.map(worker,range(2))))
finally:
    with engine.begin() as c:
        c.execute(text("DELETE FROM app.workflow_runs WHERE tenant_id=:t"),{"t":tid})
        c.execute(text("DELETE FROM app.tenants WHERE id=:t AND public_id=:p"),{"t":tid,"p":tpub})
    emit("RACE_FIXTURE_CLEANED", True)
engine.dispose()
