"""Read/replay T7 boundaries in one rolled-back PostgreSQL transaction."""
import importlib.util
import json
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
    def __init__(self, actors, role="viewer"):
        self.actors = actors
        self.role = role

    def lookup(self, actor_id):
        if actor_id in self.actors:
            return UserRecord(actor_id, "fixture@example.invalid", "active")
        return None

    def membership(self, actor_id, tenant_public_id):
        return self.role


def outcome(fn):
    try:
        value = fn()
        return "ACCEPTED:" + str(getattr(value, "kind", value))
    except Exception as exc:
        return "REJECTED:" + type(exc).__name__


def main():
    import os
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as conn:
        tx = conn.begin()
        try:
            tenants = [str(conn.execute(text(
                "INSERT INTO app.tenants (name,scope) VALUES (:name,'internal') RETURNING public_id"
            ), {"name": "cdx-r82-" + uuid.uuid4().hex}).scalar()) for _ in range(2)]
            directory = Directory({SYSTEM})
            print("DUAL_CANONICAL=" + outcome(lambda: ActorResolver(conn, directory).assert_can_act(SYSTEM, tenants[0])))
            print("DUAL_UPPERCASE=" + outcome(lambda: ActorResolver(conn, directory).assert_can_act(SYSTEM.upper(), tenants[0])))
            print("DIRECTORY_OMITTED=" + outcome(lambda: ActorResolver(conn).assert_can_act(SYSTEM, tenants[0])))
            user = str(uuid.uuid4())
            invalid = Directory({user}, "unregistered-role")
            print("UNKNOWN_MEMBERSHIP_ROLE=" + outcome(lambda: ActorResolver(conn, invalid).assert_can_act(user, tenants[0])))
            print("WORKER_TENANT_A=" + outcome(lambda: ActorResolver(conn).assert_can_act(WORKER, tenants[0])))
            print("WORKER_TENANT_B_NO_SCOPE=" + outcome(lambda: ActorResolver(conn).assert_can_act(WORKER, tenants[1])))
            event = write_audit_event(conn, actor_id=WORKER, tenant_public_id=tenants[0],
                action="cdx.r82", target_type="tenant", target_public_id=tenants[0],
                request_id="cdx-r82-request", before={"unicode":"中文","nested":[1,True,None]},
                after={"amount":"12.30"}, evidence_ref="ev:cdx-r82")
            row = conn.execute(text('SELECT before,after,evidence_ref,request_id FROM app.audit_events WHERE id=:i'), {"i":event}).first()
            print("AUDIT_JSONB=" + json.dumps(list(row), ensure_ascii=True))
            spec = importlib.util.spec_from_file_location("seed", ROOT / "project/migrations/versions/t7seed000001_actor_registry_seed.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            ns = uuid.UUID("a0d983f5-2f48-59d5-bf52-becf33d6a669")
            print("SEED_UUID_EXACT=" + str(all(str(uuid.uuid5(ns, kind)) == actor for actor,kind,_,_ in mod.ACTOR_SEEDS)))
            with Operations.context(MigrationContext.configure(conn)):
                mod.downgrade()
                conn.execute(text("INSERT INTO app.actor_registry (actor_id,actor_kind,name,status) VALUES (:a,'service','PREEXISTING','disabled')"), {"a":SYSTEM})
                mod.upgrade()
                conflict = conn.execute(text("SELECT actor_kind,name,status FROM app.actor_registry WHERE actor_id=:a"), {"a":SYSTEM}).first()
                print("SEED_CONFLICT_AFTER_UPGRADE=" + str(tuple(conflict)))
                mod.downgrade()
                print("PREEXISTING_AFTER_DOWNGRADE=" + str(conn.execute(text("SELECT count(*) FROM app.actor_registry WHERE actor_id=:a"), {"a":SYSTEM}).scalar()))
        finally:
            tx.rollback()
            print("PROBE_TRANSACTION_ROLLED_BACK=true")
    eng.dispose()


if __name__ == "__main__":
    main()
