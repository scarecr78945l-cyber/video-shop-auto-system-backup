"""Focused helper and migration checks; every mutation rolls back."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from infra.auth import (ActorDirectoryMismatchError, PgUserDirectory, OrganizationError,
                        bind_tenant_organization, set_member_role, unbind_tenant_organization)

WORKER = "a9a79363-609b-5848-a4b3-33982797cfb8"
engine = create_engine(os.environ["DATABASE_URL"])
def emit(k, v):
    print(k + "=" + json.dumps(v, default=str))

with engine.connect() as conn:
    tx = conn.begin()
    try:
        directory = PgUserDirectory(conn)
        tid = str(conn.execute(text("INSERT INTO app.tenants(name,scope) VALUES ('cdx-r94','internal') RETURNING public_id")).scalar_one())
        uid = str(conn.execute(text("INSERT INTO auth.user(name,email) VALUES ('cdx-r94',:e) RETURNING id"), {"e": str(uuid.uuid4()) + "@example.invalid"}).scalar_one())
        rid = "cdx-r94-" + uuid.uuid4().hex
        oid = bind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=tid.upper(),
            organization_name="r94", first_admin_user_id=uid, request_id=rid,
            worker_scope_tenant_public_id=tid.replace("-", ""), user_directory=directory)
        emit("CANONICAL_SLUG", conn.execute(text("SELECT slug=:t FROM auth.organization WHERE id=:o"), {"t": tid, "o": oid}).scalar_one())
        variants = [tid, tid.upper(), tid.replace("-", "")]
        emit("MEMBERSHIP_EQUIVALENCE", [directory.membership(uid, x) for x in variants])
        denied = 0
        for value in variants:
            try:
                bind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=value,
                    organization_name="duplicate", worker_scope_tenant_public_id=tid, user_directory=directory)
            except OrganizationError:
                denied += 1
        emit("DUP_BIND_DENIED", denied)
        set_member_role(conn, operator_actor_id=WORKER, tenant_public_id=tid.replace("-", ""), target_actor_id=uid.upper(),
            new_role="viewer", request_id=rid, operator_scope_tenant_public_id=tid, user_directory=directory)
        emit("ROLE_AFTER_CANONICAL_WRITE", directory.membership(uid, tid))
        emit("HELPER_AUDIT", [tuple(row) for row in conn.execute(text("SELECT action,request_id FROM app.audit_events WHERE request_id=:r ORDER BY id"), {"r": rid})])
        try:
            with conn.begin_nested():
                conn.execute(text("INSERT INTO auth.member(organization_id,user_id,role,created_at) VALUES (:o,:u,'admin',now())"), {"o": oid, "u": uid})
        except IntegrityError as exc:
            emit("DUP_MEMBER_SQLSTATE", exc.orig.pgcode)
        try:
            unbind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=tid, worker_scope_tenant_public_id=tid, user_directory=directory)
        except OrganizationError:
            emit("MEMBER_UNBIND_DENIED", True)
        savepoint = conn.begin_nested()
        try:
            conn.execute(text('ALTER TABLE auth.member DROP CONSTRAINT member_organization_id_user_id_uidx'))
            conn.execute(text("INSERT INTO auth.member(organization_id,user_id,role,created_at) VALUES (:o,:u,'admin',now())"), {"o": oid, "u": uid})
            try:
                directory.membership(uid, tid)
            except ActorDirectoryMismatchError:
                emit("AMBIGUOUS_MEMBERSHIP_DENIED", True)
        finally:
            savepoint.rollback()
        conn.execute(text("DELETE FROM auth.member WHERE organization_id=:o"), {"o": oid})
        conn.execute(text("INSERT INTO auth.invitation(organization_id,email,role,expires_at,inviter_id) VALUES (:o,:e,'viewer',now()+interval '1 day',:u)"), {"o": oid, "u": uid, "e": str(uuid.uuid4()) + "@example.invalid"})
        try:
            unbind_tenant_organization(conn, actor_id=WORKER, tenant_public_id=tid, request_id=rid, worker_scope_tenant_public_id=tid, user_directory=directory)
            emit("INVITATION_ONLY_UNBIND", "accepted")
        except OrganizationError:
            emit("INVITATION_ONLY_UNBIND", "denied")
        emit("INVITATIONS_AFTER_UNBIND", conn.execute(text("SELECT count(*) FROM auth.invitation WHERE organization_id=:o"), {"o": oid}).scalar_one())
    finally:
        tx.rollback()
        emit("HELPERS_ROLLED_BACK", True)

def snapshot(conn, schema):
    return list(conn.execute(text("SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema=:s ORDER BY table_name,ordinal_position"), {"s": schema}).all())
def constraint(conn):
    return conn.execute(text("SELECT count(*) FROM pg_constraint WHERE conname='member_organization_id_user_id_uidx' AND conrelid='auth.member'::regclass")).scalar_one()
def defaults(conn):
    return [tuple(r) for r in conn.execute(text("SELECT table_name,column_default FROM information_schema.columns WHERE table_schema='auth' AND table_name IN ('session','account') AND column_name='updated_at' ORDER BY table_name"))]

spec = importlib.util.spec_from_file_location("r94_migration", ROOT / "project/migrations/versions/auth000002_auth_schema_fixes.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with engine.connect() as conn:
    tx = conn.begin()
    try:
        conn.execute(text("SET LOCAL ROLE dsh_migrator"))
        conn.execute(text("SET LOCAL search_path TO app,pg_catalog"))
        before_app, before_auth = snapshot(conn, "app"), snapshot(conn, "auth")
        emit("UP_DEFAULTS", defaults(conn))
        emit("UP_MEMBER_UNIQUE", constraint(conn))
        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()
            emit("DOWN_DEFAULTS", defaults(conn))
            emit("DOWN_MEMBER_UNIQUE", constraint(conn))
            module.upgrade()
        emit("ROUNDTRIP_APP_COLUMNS_EQUAL", before_app == snapshot(conn, "app"))
        emit("ROUNDTRIP_AUTH_COLUMNS_EQUAL", before_auth == snapshot(conn, "auth"))
        emit("ROUNDTRIP_MEMBER_UNIQUE", constraint(conn))
        emit("REVISION", conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar_one())
    finally:
        tx.rollback()
        emit("MIGRATION_BODY_ROLLED_BACK", True)
