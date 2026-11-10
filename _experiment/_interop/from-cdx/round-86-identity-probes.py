"""R84-2 regression: real PostgreSQL, injected directory, rollback-only writes."""
import importlib.util
import os
import uuid
from pathlib import Path
from sqlalchemy import create_engine, text

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r84", HERE / "round-84-probes.py")
r84 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r84)
from infra.auth.actor import ActorDirectoryMismatchError, TenantForbiddenError


def main():
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            tenant = str(conn.execute(text("INSERT INTO app.tenants(name,scope) VALUES(:n,'internal') RETURNING public_id"),
                {"n":"cdx-r86-"+uuid.uuid4().hex}).scalar())
            user = str(uuid.uuid4())
            directory = r84.Directory(user, tenant)
            variants = lambda v: [v, v.upper(), v.replace("-", ""), uuid.UUID(v)]
            for aid in variants(user):
                for tid in variants(tenant):
                    rec = r84.ActorResolver(conn,directory).assert_can_act(aid,tid)
                    assert rec.actor_id == user
            print("MEMBERSHIP_POSITIVE_MATRIX=16/16")
            for aid in variants(user):
                try:
                    r84.ActorResolver(conn,r84.Directory(user,str(uuid.uuid4()))).assert_can_act(aid,tenant)
                    raise AssertionError("membership accepted")
                except TenantForbiddenError:
                    pass
            print("MEMBERSHIP_NEGATIVE=4/4")
            for scope in variants(tenant):
                assert r84.ActorResolver(conn,r84.Directory()).assert_can_act(r84.WORKER,tenant,
                    worker_scope_tenant_public_id=scope).kind == "worker"
            print("WORKER_EQUIVALENT_SCOPE=4/4")
            for returned in [str(uuid.uuid4()),"invalid-uuid"]:
                before = conn.execute(text("SELECT count(*) FROM app.audit_events")).scalar()
                try:
                    r84.write_audit_event(conn, actor_id=user, tenant_public_id=tenant, action="cdx.r86",
                        target_type="tenant",target_public_id=tenant,request_id="r86",
                        user_directory=r84.Directory(user,tenant,returned=returned))
                    raise AssertionError("wrong identity accepted")
                except ActorDirectoryMismatchError:
                    pass
                assert before == conn.execute(text("SELECT count(*) FROM app.audit_events")).scalar()
            print("DIRECTORY_MISMATCH_INVALID_ZERO_INSERT=2/2")
        finally:
            tx.rollback()
            print("ROLLED_BACK=true")
    engine.dispose()


if __name__ == "__main__":
    main()
