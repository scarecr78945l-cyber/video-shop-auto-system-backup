"""Read actual catalog and probe T7 helpers; all mutations roll back."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from infra.auth import ActorResolver, PgUserDirectory, bind_tenant_organization, set_member_role

WORKER = "a9a79363-609b-5848-a4b3-33982797cfb8"
engine = create_engine(os.environ["DATABASE_URL"])


def emit(key, value):
    print(key + "=" + json.dumps(value, ensure_ascii=True, default=str))


def tenant(conn):
    return str(conn.execute(text("INSERT INTO app.tenants (name, scope) VALUES (:n, 'internal') RETURNING public_id"), {"n": "r92-" + uuid.uuid4().hex}).scalar_one())


def user(conn):
    return str(conn.execute(text('INSERT INTO auth."user" (name,email) VALUES (:n,:e) RETURNING id'), {"n": "r92", "e": uuid.uuid4().hex + "@example.invalid"}).scalar_one())


with engine.connect() as conn:
    tx = conn.begin()
    try:
        directory = PgUserDirectory(conn)
        tid = tenant(conn)
        uid = user(conn)
        upper_org = bind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=tid.upper(), organization_name="uppercase", worker_scope_tenant_public_id=tid, user_directory=directory)
        set_member_role(conn, operator_actor_id=WORKER, tenant_public_id=tid.upper(), target_actor_id=uid, new_role="admin", operator_scope_tenant_public_id=tid, user_directory=directory)
        emit("UPPERCASE_STORED_SLUG", conn.execute(text("SELECT slug FROM auth.organization WHERE id=:o"), {"o": upper_org}).scalar_one())
        emit("CANONICAL_MEMBERSHIP", directory.membership(uid, tid))
        try:
            ActorResolver(conn, user_directory=directory).assert_can_act(uid, tid.upper(), required_role="admin")
            emit("UPPERCASE_USER_AUTH", "accepted")
        except Exception as exc:
            emit("UPPERCASE_USER_AUTH", type(exc).__name__)
        lower_org = bind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=tid, organization_name="lowercase", worker_scope_tenant_public_id=tid, user_directory=directory)
        emit("SAME_TENANT_ORGANIZATIONS", conn.execute(text("SELECT count(*) FROM auth.organization WHERE lower(slug)=:t"), {"t": tid}).scalar_one())
        set_member_role(conn, operator_actor_id=WORKER, tenant_public_id=tid, target_actor_id=uid, new_role="admin", operator_scope_tenant_public_id=tid, user_directory=directory)
        conn.execute(text("INSERT INTO auth.member(organization_id,user_id,role,created_at) VALUES (:o,:u,'viewer',now())"), {"o": lower_org, "u": uid})
        emit("DUPLICATE_MEMBERSHIP_ROLES", conn.execute(text("SELECT role FROM auth.member WHERE organization_id=:o AND user_id=:u ORDER BY role"), {"o": lower_org, "u": uid}).scalars().all())
        emit("DUPLICATE_DIRECTORY_ROLE", directory.membership(uid, tid))
        try:
            ActorResolver(conn, user_directory=directory).assert_can_act(uid, tid, required_role="admin")
            emit("DUPLICATE_ADMIN_AUTH", "accepted")
        except Exception as exc:
            emit("DUPLICATE_ADMIN_AUTH", type(exc).__name__)
        emit("BIND_AND_ROLE_AUDIT_ROWS", conn.execute(text("SELECT count(*) FROM app.audit_events a JOIN app.tenants t ON t.id=a.tenant_id WHERE t.public_id=:t"), {"t": tid}).scalar_one())
    finally:
        tx.rollback()
        emit("HELPER_PROBE_ROLLED_BACK", True)


def catalog(conn, schema):
    return [tuple(r) for r in conn.execute(text("SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema=:s ORDER BY table_name,ordinal_position"), {"s": schema})]


spec = importlib.util.spec_from_file_location("r92_migration", ROOT / "project/migrations/versions/auth000001_auth_7_tables.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
with engine.connect() as conn:
    tx = conn.begin()
    try:
        # Keep role/search_path identical while comparing rendered defaults.
        conn.execute(text("SET LOCAL ROLE dsh_migrator"))
        conn.execute(text("SET LOCAL search_path TO app, pg_catalog"))
        before_app = catalog(conn, "app")
        before_auth = catalog(conn, "auth")
        emit("AUTH_UPDATED_AT_DEFAULTS", [r for r in before_auth if r[1] == "updated_at"])
        emit("AUTH_TIMESTAMP_TYPES", sorted({r[2] for r in before_auth if "timestamp" in r[2]}))
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
            emit("ROUNDTRIP_DOWN_AUTH_COLUMNS", len(catalog(conn, "auth")))
            migration.upgrade()
        emit("ROUNDTRIP_AUTH_COLUMN_CATALOG_EQUAL", before_auth == catalog(conn, "auth"))
        emit("ROUNDTRIP_APP_COLUMN_CATALOG_EQUAL", before_app == catalog(conn, "app"))
        emit("ROUNDTRIP_VERSION_UNCHANGED", conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar_one())
    finally:
        tx.rollback()
        emit("MIGRATION_BODY_PROBE_ROLLED_BACK", True)
