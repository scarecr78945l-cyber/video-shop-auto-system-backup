"""Independent focused probes for the round-107 queue; exact owned cleanup."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from domain.workflow import WorkflowQueue, compute_run_key, compute_step_action_key
engine=create_engine(os.environ['DATABASE_URL'])
def emit(k,v): print(k+'='+json.dumps(v,default=str))
def tenant(c):
    return c.execute(text("INSERT INTO app.tenants(name,scope) VALUES (:n,'internal') RETURNING id,public_id"),{'n':'cdx-r108-'+uuid.uuid4().hex}).one()
def run(c,tid,tp,key=None):
    trigger=str(uuid.uuid4())
    return WorkflowQueue(c).ensure_run(tenant_id=tid,tenant_public_id=str(tp),run_type='listing_flow',
        idempotency_key=key or compute_run_key(str(tp),'manual',trigger,'w1','p1'),
        trigger_type='manual',trigger_public_id=trigger,schedule_window='w1',policy_version_id='p1')[0]
def enqueue(c,tid,tp,rid,slot):
    rp=str(c.execute(text('SELECT public_id FROM app.workflow_runs WHERE id=:r'),{'r':rid}).scalar())
    key=compute_step_action_key(str(tp),rp,'listing_submit',slot)
    sid=WorkflowQueue(c).enqueue_step(tenant_id=tid,run_id=rid,step_type='listing_submit',action_idempotency_key=key)
    return sid,key
def cleanup(tid,tp):
    with engine.begin() as c:
        c.execute(text('DELETE FROM app.workflow_runs WHERE tenant_id=:t'),{'t':tid})
        c.execute(text('DELETE FROM app.tenants WHERE id=:t AND public_id=:p'),{'t':tid,'p':tp})

uid='abcdefab-cdef-4abc-8abc-abcdefabcdef'
emit('UUID_CASE_STEP_EQUAL',compute_step_action_key(uid,uid,'listing_submit','slot')==compute_step_action_key(uid.upper(),uid,'listing_submit','slot'))
emit('UUID_CASE_RUN_EQUAL',compute_run_key(uid,'manual',uid,'w1','p1')==compute_run_key(uid,'manual',uid.upper(),'w1','p1'))
emit('UTC_INSTANT_RUN_EQUAL',compute_run_key(uid,'manual',uid,'2026-09-06T00:00:00Z','p1')==compute_run_key(uid,'manual',uid,'2026-09-06T08:00:00+08:00','p1'))
with engine.connect() as c:
    tx=c.begin()
    try:
        tid,tp=tenant(c); q=WorkflowQueue(c); rid=run(c,tid,tp)
        a,ka=enqueue(c,tid,tp,rid,'slot-a'); b,kb=enqueue(c,tid,tp,rid,'slot-b')
        stored=c.execute(text('SELECT action_idempotency_key FROM app.workflow_steps WHERE id=:s'),{'s':b}).scalar()
        emit('DISTINCT_ACTION_ALIAS',{'keys_differ':ka!=kb,'same_id':a==b,'requested_key_stored':stored==kb})
        sid,attempt=q.claim(run_id=rid)
        q.handle_error(step_id=sid,attempt=attempt,error_code='NO_MATCH')
        c.execute(text("UPDATE app.workflow_steps SET gate_result=jsonb_set(gate_result,'{retry_at}',to_jsonb('2000-01-01T00:00:00Z'::text)) WHERE id=:s"),{'s':sid})
        sid,attempt=q.claim(run_id=rid)
        result=q.handle_error(step_id=sid,attempt=attempt,error_code='NO_MATCH')
        status=c.execute(text('SELECT status FROM app.workflow_steps WHERE id=:s'),{'s':sid}).scalar()
        emit('EXHAUSTED_ERROR_RESULT',{'attempt':attempt,'returned':result,'persisted':status})
    finally:
        tx.rollback()
emit('VALUE_PROBES_ROLLED_BACK',True)

# Only synchronize the first SELECT of each connection, not post-conflict lookup.
with engine.begin() as c: tid,tp=tenant(c)
barrier=threading.Barrier(2)
shared='run:v1:'+uuid.uuid4().hex
class FirstSelectBarrier:
    def __init__(self,c): self.c=c; self.used=False
    def execute(self,stmt,params):
        res=self.c.execute(stmt,params)
        if not self.used and str(stmt).startswith('SELECT id FROM app.workflow_runs'):
            self.used=True; row=res.first(); barrier.wait(timeout=10)
            class Result:
                def first(self): return row
            return Result()
        return res
def racer(_):
    with engine.begin() as c:
        result=WorkflowQueue(FirstSelectBarrier(c)).ensure_run(tenant_id=tid,tenant_public_id=str(tp),run_type='listing_flow',idempotency_key=shared,trigger_type='manual',trigger_public_id=uid,schedule_window='w1',policy_version_id='p1')
        assert c.execute(text('SELECT 1')).scalar()==1
        return result
try:
    with ThreadPoolExecutor(max_workers=2) as workers: result=list(workers.map(racer,range(2)))
    assert result[0][0]==result[1][0] and sum(x[1] for x in result)==1
    emit('ATOMIC_ENSURE_RUN_PASS',result)
finally: cleanup(tid,tp)

# A blocked UPDATE retains its statement snapshot of the joined parent run.
with engine.begin() as c:
    tid,tp=tenant(c); rid=run(c,tid,tp); sid,_=enqueue(c,tid,tp,rid,'race')
    WorkflowQueue(c).claim(run_id=rid)
    c.execute(text("UPDATE app.workflow_steps SET updated_at=now()-interval '46 minutes' WHERE id=:s"),{'s':sid})
holder=engine.connect(); hold_tx=holder.begin()
holder.execute(text('SELECT id FROM app.workflow_steps WHERE id=:s FOR UPDATE'),{'s':sid})
started=threading.Event(); result={}
def recover_worker():
    with engine.begin() as c:
        c.execute(text("SET LOCAL statement_timeout='10s'"))
        result['pid']=c.execute(text('SELECT pg_backend_pid()')).scalar(); started.set()
        try: result['recovered']=WorkflowQueue(c).recover_stale_attempts()
        except Exception as exc: result['error']=type(exc).__name__
worker=threading.Thread(target=recover_worker)
try:
    worker.start(); assert started.wait(5)
    blocked=False
    for _ in range(50):
        with engine.connect() as c:
            blocked=bool(c.execute(text('SELECT cardinality(pg_blocking_pids(:p))'),{'p':result['pid']}).scalar())
        if blocked: break
        time.sleep(.05)
    assert blocked,'recover did not reach step lock'
    with engine.begin() as c: WorkflowQueue(c).set_run_status(run_id=rid,status='cancelled')
    hold_tx.commit(); worker.join(12); assert not worker.is_alive()
    with engine.connect() as c:
        row=c.execute(text('SELECT r.status,s.status,s.attempt FROM app.workflow_runs r JOIN app.workflow_steps s ON s.run_id=r.id WHERE s.id=:s'),{'s':sid}).one()
    emit('CANCEL_RECOVER_RACE',{'recovered':result.get('recovered'),'error':result.get('error'),'row':list(row)})
finally:
    if hold_tx.is_active: hold_tx.rollback()
    holder.close(); worker.join(12)
    cleanup(tid,tp)

# Test-owned committed fixtures must be cleaned even if the worker fails.
spec=importlib.util.spec_from_file_location('r108_tests',ROOT/'backend/tests/test_workflow_queue.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
created=[];original=m._new_tenant
def tracked(c):
    pair=original(c);created.append(pair);return pair
try:
    with engine.connect() as c, mock.patch.object(m,'_new_tenant',tracked), mock.patch.object(m.WorkflowQueue,'ensure_run',side_effect=RuntimeError('r108 worker fault')):
        try: m.test_concurrent_ensure_run_same_key(c)
        except AssertionError: pass
        else: raise AssertionError('worker failure must fail test')
    assert len(created)==1
    tid,tp=created[0]
    with engine.connect() as c: remaining=c.execute(text('SELECT count(*) FROM app.tenants WHERE id=:t'),{'t':tid}).scalar()
    emit('CONCURRENT_TEST_FAULT_TENANT_REMAINING',remaining)
finally:
    for tid,tp in created: cleanup(tid,tp)
emit('OWN_FIXTURES_CLEANED',True)
engine.dispose()
