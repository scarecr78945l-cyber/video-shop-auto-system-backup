"""T7 focused probes. Database writes are rolled back; no schema deployment."""
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from infra.auth.actor import ActorResolver, UserDirectory, UserRecord
from domain.audit import write_audit_event

SYSTEM = "699f543a-2540-5127-913e-8cca0148db9b"
WORKER = "a9a79363-609b-5848-a4b3-33982797cfb8"


class Directory(UserDirectory):
    def __init__(self, actor=None, tenant=None, role="admin", returned=None, fail=False):
        self.actor, self.tenant, self.role = actor, tenant, role
        self.returned, self.fail = returned or actor, fail

    def lookup(self, actor):
        if self.fail:
            raise RuntimeError("directory-fixture-down")
        if actor == self.actor:
            return UserRecord(self.returned, "fixture@example.invalid", "active")
        return None

    def membership(self, actor, tenant):
        return self.role if (actor, tenant) == (self.actor, self.tenant) else None


def result(fn):
    try:
        rec = fn()
        return "ACCEPTED:" + str(getattr(rec, "kind", rec))
    except Exception as exc:
        return "REJECTED:" + type(exc).__name__


def main():
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as conn:
        tx = conn.begin()
        try:
            tenant = str(conn.execute(text("INSERT INTO app.tenants(name,scope) VALUES (:n,'internal') RETURNING public_id"),
                {"n": "cdx-r84-" + uuid.uuid4().hex}).scalar())
            user = str(uuid.uuid4())
            directory = Directory(user, tenant)
            resolver = ActorResolver(conn, directory)
            for label, actor, target in [("CANONICAL", user, tenant), ("UPPER_ACTOR", user.upper(), tenant),
                                          ("COMPACT_ACTOR", user.replace("-", ""), tenant), ("UPPER_TENANT", user, tenant.upper())]:
                print("MEMBERSHIP_" + label + "=" + result(lambda: resolver.assert_can_act(actor, target)))
            for actor in [SYSTEM, SYSTEM.upper(), SYSTEM.replace("-", "")]:
                print("DUAL=" + result(lambda: ActorResolver(conn, Directory(SYSTEM,tenant)).resolve(actor)))
            audit_args = dict(actor_id=WORKER, tenant_public_id=tenant, action="cdx.r84", target_type="tenant",
                              target_public_id=tenant, request_id="cdx-r84", worker_scope_tenant_public_id=tenant)
            for label, d in [("MISSING", None), ("ERROR", Directory(fail=True))]:
                before = conn.execute(text("SELECT count(*) FROM app.audit_events")).scalar()
                print("DIRECTORY_"+label+"=" + result(lambda: write_audit_event(conn, **audit_args, user_directory=d)))
                assert before == conn.execute(text("SELECT count(*) FROM app.audit_events")).scalar()
            for role in ["unknown", ""]:
                print("ROLE_"+repr(role)+"=" + result(lambda: ActorResolver(conn,Directory(user,tenant,role)).assert_can_act(user,tenant)))
            for label, scope in [("MATCH",tenant),("MISSING",None),("OTHER",str(uuid.uuid4()))]:
                args = dict(audit_args, worker_scope_tenant_public_id=scope)
                print("WORKER_AUDIT_"+label+"=" + result(lambda: write_audit_event(conn, **args, user_directory=Directory())))
            wrong = Directory(user,tenant,returned=str(uuid.uuid4()))
            wrong_args = dict(audit_args, actor_id=user)
            print("WRONG_DIRECTORY_RECORD=" + result(lambda: write_audit_event(conn, **wrong_args, user_directory=wrong)))
            print("WRONG_RECORD_REQUESTED="+user+" RETURNED="+wrong.returned)
            persisted = conn.execute(text("SELECT actor_id FROM app.audit_events WHERE request_id='cdx-r84' ORDER BY id DESC LIMIT 1")).scalar()
            print("WRONG_RECORD_PERSISTED_REQUESTED_ID=" + str(str(persisted) == user))
            spec = importlib.util.spec_from_file_location("seed",ROOT/"project/migrations/versions/t7seed000001_actor_registry_seed.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for pos in range(3):
                for same in [True, False]:
                    case = conn.begin_nested()
                    with Operations.context(MigrationContext.configure(conn)):
                        mod.downgrade()
                        aid,kind,name,status = mod.ACTOR_SEEDS[pos]
                        if not same:
                            kind,name,status="service","PREEXISTING","disabled"
                        conn.execute(text("INSERT INTO app.actor_registry(actor_id,actor_kind,name,status) VALUES(:a,:k,:n,:s)"),
                            dict(a=aid,k=kind,n=name,s=status))
                        expected = list(conn.execute(text("SELECT actor_id,actor_kind,name,status FROM app.actor_registry ORDER BY actor_id")))
                        attempt = conn.begin_nested()
                        try:
                            mod.upgrade()
                            raise AssertionError("conflict accepted")
                        except RuntimeError:
                            attempt.rollback()
                        observed = list(conn.execute(text("SELECT actor_id,actor_kind,name,status FROM app.actor_registry ORDER BY actor_id")))
                        assert observed == expected
                        print(f"SEED_CONFLICT_POSITION={pos+1} SAME={same} ROLLBACK_EXACT=True")
                    case.rollback()
        finally:
            tx.rollback()
            print("PROBE_TRANSACTION_ROLLED_BACK=true")
    eng.dispose()


if __name__ == "__main__":
    main()
