"""T9 focused review: owned databases/containers only, no business edits."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
BASE = "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/"
admin = create_engine(BASE + "postgres", isolation_level="AUTOCOMMIT")
owned = set()
container = None


def ddl(sql):
    with admin.connect() as c:
        c.execute(text(sql))


def call(args, url, role="dsh_migrator"):
    return subprocess.run([sys.executable, *args], cwd=ROOT / "project",
                          env=dict(os.environ, DATABASE_URL=url, MIGRATION_ROLE=role, PYTHONUTF8="1"),
                          capture_output=True, text=True, encoding="utf-8", timeout=100)


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "project/scripts" / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.BASE_URL = BASE + "dsh_test"
    m.BACKEND = ROOT / "_experiment/_interop/from-cdx/r114-no-fixtures"
    return m


try:
    db = "cdx_r114_" + uuid.uuid4().hex[:12]
    owned.add(db)
    ddl(f'CREATE DATABASE "{db}" OWNER dsh_migrator')
    url = BASE + db
    r = call(["-m", "alembic", "upgrade", "head"], url)
    assert r.returncode == 0, r.stderr
    eng = create_engine(url)
    with eng.connect() as c:
        enum = c.execute(text("SELECT typname FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
                              "WHERE n.nspname='app' AND typtype='e' ORDER BY typname LIMIT 1")).scalar()
        tbl, trg = c.execute(text("SELECT x.relname,t.tgname FROM pg_trigger t JOIN pg_class x ON x.oid=t.tgrelid "
                                  "JOIN pg_namespace n ON n.oid=x.relnamespace WHERE n.nspname='app' "
                                  "AND NOT t.tgisinternal ORDER BY tgname LIMIT 1")).first()
        idx = c.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname='app' "
                              "AND indexname='ix_steps_status_updated'")).scalar()
        ft, fk, fdef = c.execute(text("SELECT x.relname,conname,pg_get_constraintdef(k.oid) "
                                     "FROM pg_constraint k JOIN pg_class x ON x.oid=k.conrelid "
                                     "JOIN pg_namespace n ON n.oid=x.relnamespace "
                                     "WHERE n.nspname='app' AND contype='f' AND array_length(conkey,1)=2 "
                                     "ORDER BY conname LIMIT 1")).first()
    cases = [
        ("auth_rename", "ALTER TABLE auth.verification RENAME TO cdx_bad_verification",
         "ALTER TABLE auth.cdx_bad_verification RENAME TO verification", 1),
        ("n1_wrong_columns", "DROP INDEX app.ix_steps_status_updated; CREATE INDEX ix_steps_status_updated ON app.workflow_steps(id)",
         "DROP INDEX app.ix_steps_status_updated; " + idx, 1),
        ("trigger_disabled", f'ALTER TABLE app."{tbl}" DISABLE TRIGGER "{trg}"',
         f'ALTER TABLE app."{tbl}" ENABLE TRIGGER "{trg}"', 1),
        ("enum_rename", f'ALTER TYPE app."{enum}" RENAME TO cdx_wrong_enum',
         f'ALTER TYPE app.cdx_wrong_enum RENAME TO "{enum}"', 0),
        ("trigger_rename", f'ALTER TRIGGER "{trg}" ON app."{tbl}" RENAME TO cdx_wrong_trigger',
         f'ALTER TRIGGER cdx_wrong_trigger ON app."{tbl}" RENAME TO "{trg}"', 0),
        ("composite_fk_missing", f'ALTER TABLE app."{ft}" DROP CONSTRAINT "{fk}"',
         f'ALTER TABLE app."{ft}" ADD CONSTRAINT "{fk}" {fdef}', 0),
        ("n1_false_predicate", "DROP INDEX app.ix_steps_status_updated; CREATE INDEX ix_steps_status_updated "
         "ON app.workflow_steps(status, updated_at) WHERE false", "DROP INDEX app.ix_steps_status_updated; " + idx, 0),
    ]
    for label, change, restore, expected in cases:
        with eng.begin() as c:
            c.execute(text(change))
        try:
            r = call(["scripts/assert_t9_catalog.py"], url)
            print(f"HEAD_MUTANT={label} RC={r.returncode}", flush=True)
            assert r.returncode == expected, r.stdout + r.stderr
        finally:
            with eng.begin() as c:
                c.execute(text(restore))
    r = call(["-m", "alembic", "downgrade", "base"], url)
    assert r.returncode == 0, r.stderr
    assert call(["scripts/assert_t9_base.py"], url).returncode == 0
    with eng.begin() as c:
        pk = c.execute(text("SELECT conname FROM pg_constraint WHERE conrelid='app.alembic_version'::regclass "
                            "AND contype='p'")).scalar()
        c.execute(text(f'ALTER TABLE app.alembic_version DROP CONSTRAINT "{pk}"; '
                       'CREATE INDEX alembic_version_pk_fake ON app.alembic_version(version_num)'))
    r = call(["scripts/assert_t9_base.py"], url)
    print(f"BASE_NON_PK_PREFIX_INDEX_RC={r.returncode}", flush=True)
    assert r.returncode == 0, r.stdout
    with eng.begin() as c:
        c.execute(text("DROP INDEX app.alembic_version_pk_fake; ALTER TABLE app.alembic_version "
                       "ADD PRIMARY KEY (version_num); CREATE EXTENSION btree_gist; "
                       "COMMENT ON EXTENSION btree_gist IS 'created_by_migration_32f34131a28a'"))
    r = call(["scripts/assert_t9_base.py"], url)
    print(f"BASE_MIGRATION_OWNED_EXTENSION_LEFTOVER_RC={r.returncode}", flush=True)
    assert r.returncode == 0, r.stdout
    with eng.begin() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS auth; CREATE TABLE auth.cdx_leftover(id int)"))
    r = call(["scripts/assert_t9_base.py"], url)
    print(f"BASE_AUTH_TABLE_LEFTOVER_RC={r.returncode}", flush=True)
    assert r.returncode == 1
    with eng.begin() as c:
        c.execute(text("DROP TABLE auth.cdx_leftover; DROP SCHEMA auth; DROP EXTENSION btree_gist"))
    eng.dispose()
    r = call(["scripts/test_extension_ownership.py"], url)
    print(f"EXISTING_EXTENSION_BOTH_PATHS_RC={r.returncode} {r.stdout.splitlines()[-1:]}", flush=True)
    assert r.returncode == 0, r.stdout + r.stderr

    for script in ("t9_rollback_drill", "t9_ci_layers"):
        for fault in ("owner", "base_assert"):
            m = load(script)
            created = []
            calls = []

            def admin_hook(sql):
                if sql.startswith("CREATE DATABASE "):
                    target = sql.split()[-1]
                    assert target.startswith(("dsh_test_t9_", "dsh_test_ci_"))
                    owned.add(target)
                    created.append(target)
                if fault == "owner" and sql.startswith("ALTER DATABASE "):
                    raise RuntimeError("R114_OWNER_FAULT")
                ddl(sql)

            def run_hook(cmd, **kwargs):
                calls.append(cmd)
                if fault == "base_assert" and "scripts/assert_t9_base.py" in cmd:
                    raise SystemExit(17)

            m._admin_sql = admin_hook
            m.run = run_hook
            try:
                m.main()
            except (RuntimeError, SystemExit) as exc:
                assert str(exc) in ("R114_OWNER_FAULT", "17")
            else:
                raise AssertionError("fault did not surface")
            with admin.connect() as c:
                remains = c.execute(text("SELECT count(*) FROM pg_database WHERE datname=:n"),
                                    {"n": created[0]}).scalar()
            print(f"FAULT={script}/{fault} DATABASE_REMAINS={remains} LAST_CALL={calls[-1:]}", flush=True)
            assert remains == 0

    # A separate PostgreSQL cluster models a new Actions service, not a shared role catalog.
    name = "cdx-r114-ci-" + uuid.uuid4().hex[:10]
    r = subprocess.run(["docker", "run", "-d", "--name", name, "-e", "POSTGRES_USER=dsh",
                        "-e", "POSTGRES_PASSWORD=dsh", "-e", "POSTGRES_DB=dsh_test",
                        "-p", "127.0.0.1::5432", "postgres:16"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    container = name
    for _ in range(50):
        ready = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "dsh"], capture_output=True)
        if ready.returncode == 0:
            break
        time.sleep(.2)
    port = subprocess.check_output(["docker", "port", name, "5432/tcp"], text=True).strip().rsplit(":", 1)[1]
    ci_url = f"postgresql+psycopg2://dsh:dsh@127.0.0.1:{port}/dsh_test"
    r = call(["-m", "alembic", "upgrade", "head"], ci_url)
    print(f"FRESH_JOB4_SERVICE_MIGRATION_RC={r.returncode}", flush=True)
    print(r.stderr[-700:], flush=True)
    assert r.returncode != 0 and "dsh_migrator" in r.stderr
finally:
    if container:
        r = subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        print("CONTAINER_REMOVED=" + container, flush=True)
    for db in sorted(owned):
        assert db.startswith(("cdx_r114_", "dsh_test_t9_", "dsh_test_ci_"))
        ddl(f'DROP DATABASE IF EXISTS "{db}" (FORCE)')
        print("DATABASE_REMOVED=" + db, flush=True)
    admin.dispose()
