"""Assert round-109 corrections; old observation probes remain unchanged."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from unittest import mock

from sqlalchemy import create_engine, text

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from domain.workflow import WorkflowQueue, WorkflowQueueError, compute_run_key, compute_step_action_key
engine=create_engine(os.environ['DATABASE_URL'])
owned=[]
def emit(k,v): print(k+'='+json.dumps(v,default=str))
def new_fixture():
    with engine.begin() as c:
        tid,tp=c.execute(text("INSERT INTO app.tenants(name,scope) VALUES (:n,'internal') RETURNING id,public_id"),{'n':'cdx-r110-'+uuid.uuid4().hex}).one()
        owned.append((tid,tp))
        trigger=str(uuid.uuid4()); q=WorkflowQueue(c)
        rid,_=q.ensure_run(tenant_id=tid,tenant_public_id=str(tp),run_type='listing_flow',idempotency_key=compute_run_key(str(tp),'manual',trigger,'w1','p1'),trigger_type='manual',trigger_public_id=trigger,schedule_window='w1',policy_version_id='p1')
        rp=str(c.execute(text('SELECT public_id FROM app.workflow_runs WHERE id=:r'),{'r':rid}).scalar())
        key=compute_step_action_key(str(tp),rp,'listing_submit','slot-a')
        sid=q.enqueue_step(tenant_id=tid,run_id=rid,step_type='listing_submit',action_idempotency_key=key)
    return tid,str(tp),rid,rp,sid,key
def clean(tid,tp):
    with engine.begin() as c:
        c.execute(text('DELETE FROM app.workflow_runs WHERE tenant_id=:t'),{'t':tid})
        c.execute(text('DELETE FROM app.tenants WHERE id=:t AND public_id=:p'),{'t':tid,'p':tp})
def row(sid):
    with engine.connect() as c:
        return c.execute(text('SELECT r.status,s.status,s.attempt FROM app.workflow_runs r JOIN app.workflow_steps s ON s.run_id=r.id WHERE s.id=:s'),{'s':sid}).one()
def wait_blocked(pid):
    for _ in range(100):
        with engine.connect() as c:
            if c.execute(text('SELECT cardinality(pg_blocking_pids(:p))'),{'p':pid}).scalar(): return
        time.sleep(.02)
    raise AssertionError('expected PostgreSQL lock wait')

try:
    u='abcdefab-cdef-4abc-8abc-abcdefabcdef'
    assert compute_step_action_key(u,u,'listing_submit','slot')==compute_step_action_key(u.upper(),u.replace('-',''),'listing_submit','slot')
    assert compute_run_key(u,'manual',u,'2026-09-06T00:00:00Z','p1')==compute_run_key(u,'manual',u.upper(),'2026-09-06T08:00:00+08:00','p1')
    emit('UUID_UTC_NORMALIZATION_PASS',True)
    tid,tp,rid,rp,sid,key=new_fixture()
    with engine.begin() as c:
        q=WorkflowQueue(c)
        try: q.enqueue_step(tenant_id=tid,run_id=rid,step_type='listing_submit',action_idempotency_key=compute_step_action_key(tp,rp,'listing_submit','slot-b'))
        except WorkflowQueueError: pass
        else: raise AssertionError('different action merged')
        assert c.execute(text('SELECT action_idempotency_key FROM app.workflow_steps WHERE id=:s'),{'s':sid}).scalar()==key
        assert c.execute(text('SELECT count(*) FROM app.workflow_steps WHERE run_id=:r'),{'r':rid}).scalar()==1
        assert q.enqueue_step(tenant_id=tid,run_id=rid,step_type='listing_submit',action_idempotency_key=key)==sid
    emit('DISTINCT_REJECT_SAME_REPLAY_TRANSACTION_PASS',True)

    for code,budget in [('RATE_LIMIT',3),('TIMEOUT',3),('UNEXPECTED',3),('INSUFFICIENT_REFERENCES',2),('NO_MATCH',2)]:
        tid,tp,rid,rp,sid,key=new_fixture()
        results=[]
        for attempt in range(1,budget+1):
            with engine.begin() as c:
                q=WorkflowQueue(c)
                assert q.claim(run_id=rid)==(sid,attempt)
                got=q.handle_error(step_id=sid,attempt=attempt,error_code=code)
                expected='failed' if attempt==budget else 'gate_retry'
                assert got==expected
            assert row(sid)[1]==got
            results.append(got)
            if attempt<budget:
                # Controlled due-time fixture; not a wall-clock waiting claim.
                with engine.begin() as c:
                    c.execute(text("UPDATE app.workflow_steps SET gate_result=jsonb_set(gate_result,'{retry_at}',to_jsonb('2000-01-01T00:00:00Z'::text)) WHERE id=:s"),{'s':sid})
        emit('ALL_ATTEMPTS_RETURN_PERSISTED_PASS',{'code':code,'results':results})

    for order in ['cancel_first','recover_first']:
        tid,tp,rid,rp,sid,key=new_fixture()
        with engine.begin() as c:
            assert WorkflowQueue(c).claim(run_id=rid)==(sid,1)
            c.execute(text("UPDATE app.workflow_steps SET updated_at=now()-interval '46 minutes' WHERE id=:s"),{'s':sid})
        holder=engine.connect(); tx=holder.begin()
        result={}; ready=threading.Event(); cancel_ready=threading.Event()
        if order=='cancel_first': WorkflowQueue(holder).set_run_status(run_id=rid,status='cancelled')
        else: holder.execute(text('SELECT id FROM app.workflow_steps WHERE id=:s FOR UPDATE'),{'s':sid})
        def recover():
            try:
                with engine.begin() as c:
                    c.execute(text("SET LOCAL statement_timeout='10s'"))
                    result['recover_pid']=c.execute(text('SELECT pg_backend_pid()')).scalar();ready.set()
                    result['count']=WorkflowQueue(c).recover_stale_attempts()
            except Exception as exc: result['recover_error']=repr(exc)
        def cancel():
            try:
                with engine.begin() as c:
                    c.execute(text("SET LOCAL statement_timeout='10s'"))
                    result['cancel_pid']=c.execute(text('SELECT pg_backend_pid()')).scalar();cancel_ready.set()
                    WorkflowQueue(c).set_run_status(run_id=rid,status='cancelled')
            except Exception as exc: result['cancel_error']=repr(exc)
        rw=threading.Thread(target=recover);cw=None
        try:
            rw.start();assert ready.wait(5);wait_blocked(result['recover_pid'])
            if order=='recover_first':
                cw=threading.Thread(target=cancel);cw.start();assert cancel_ready.wait(5);wait_blocked(result['cancel_pid'])
            tx.commit();rw.join(12)
            if cw: cw.join(12)
            assert not rw.is_alive() and not (cw and cw.is_alive())
            assert 'recover_error' not in result and 'cancel_error' not in result,result
            expected=('cancelled','running',1) if order=='cancel_first' else ('cancelled','pending',2)
            actual=tuple(row(sid));assert actual==expected,(result,actual)
            assert result['count']==(0 if order=='cancel_first' else 1)
            emit('REAL_LOCK_ORDER_PASS',{'order':order,'recovered':result['count'],'row':actual})
        finally:
            if tx.is_active: tx.rollback()
            holder.close();rw.join(12)
            if cw: cw.join(12)

    spec=importlib.util.spec_from_file_location('r110_tests',ROOT/'backend/tests/test_workflow_queue.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    tracked=[];original=m._new_tenant
    def tracking(c):
        pair=original(c);tracked.append(pair);owned.append(pair);return pair
    with engine.connect() as c, mock.patch.object(m,'_new_tenant',tracking), mock.patch.object(m.WorkflowQueue,'ensure_run',side_effect=RuntimeError('r110 worker fault')):
        try: m.test_concurrent_ensure_run_same_key(c)
        except AssertionError: pass
        else: raise AssertionError('fault must fail test')
    assert len(tracked)==1
    with engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM app.tenants WHERE id=:t'),{'t':tracked[0][0]}).scalar()==0
    emit('ACTUAL_TEST_WORKER_FAULT_CLEANUP_PASS',True)
finally:
    for tid,tp in owned: clean(tid,tp)
    engine.dispose()
emit('R110_FOCUSED_PROBE','PASS')
