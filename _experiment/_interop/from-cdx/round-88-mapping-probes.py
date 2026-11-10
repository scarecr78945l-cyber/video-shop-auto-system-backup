"""Mapping checks on real PostgreSQL, with an injected directory; rollback only."""
import importlib.util
import os
import uuid
from pathlib import Path
from sqlalchemy import create_engine, text

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r84", HERE / "round-84-probes.py")
r84 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r84)


def main():
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text('SET LOCAL ROLE dsh_migrator'))
            conn.execute(text('SET LOCAL search_path TO app, pg_catalog'))
            print("MIGRATION_SEARCH_PATH=" + conn.execute(text("SHOW search_path")).scalar())
            print("UNQUALIFIED_TARGET_SCHEMA=" + conn.execute(text("SELECT current_schema()")).scalar())
            tenant = str(conn.execute(text("INSERT INTO app.tenants(name,scope) VALUES(:n,'internal') RETURNING public_id"),
                {"n":"cdx-r88-" + uuid.uuid4().hex}).scalar())
            user = str(uuid.uuid4())
            resolver = r84.ActorResolver(conn, r84.Directory(user,tenant))
            print("USER_BEFORE_REGISTRY_STATUS=" + r84.result(lambda: resolver.assert_can_act(user,tenant)))
            for role in ["owner", "member", "admin", "operator", "viewer"]:
                print("BUSINESS_ROLE_"+role+"="+r84.result(lambda: r84.ActorResolver(conn,r84.Directory(user,tenant,role)).assert_can_act(user,tenant)))
            conn.execute(text("INSERT INTO app.actor_registry(actor_id,actor_kind,name,status) VALUES(:u,'service','cdx-r88-status','disabled')"),{"u":user})
            print("USER_WITH_REGISTRY_STATUS=" + r84.result(lambda: resolver.assert_can_act(user,tenant)))
        finally:
            tx.rollback()
            print("ROLLED_BACK=true")
    engine.dispose()


if __name__ == "__main__":
    main()
