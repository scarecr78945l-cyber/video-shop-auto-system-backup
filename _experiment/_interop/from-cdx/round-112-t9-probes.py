"""Independent T9 gate probes; exclusively owned temporary databases."""
import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
BASE = "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/"
PREFIX = "cdx_r112_"
admin = create_engine(BASE + "postgres", isolation_level="AUTOCOMMIT")
owned = set()


def ddl(sql):
    with admin.connect() as c:
        c.execute(text(sql))


def call(args, db):
    env = dict(os.environ, DATABASE_URL=BASE + db,
               MIGRATION_ROLE="dsh_migrator", PYTHONUTF8="1")
    return subprocess.run([sys.executable, *args], cwd=ROOT / "project",
                          env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=60)


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "project/scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    db = PREFIX + uuid.uuid4().hex[:12]
    owned.add(db)
    ddl(f'CREATE DATABASE "{db}" OWNER dsh_migrator')
    engine = create_engine(BASE + db)
    # Replay the delivered extension preinstall transaction exactly.
    with engine.connect() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    with engine.connect() as c:
        print("PREINSTALL_AFTER_CONNECTION_CLOSE=" + str(c.execute(text(
            "SELECT count(*) FROM pg_extension WHERE extname='btree_gist'"
        )).scalar()), flush=True)
    r = call(["-m", "alembic", "upgrade", "head"], db)
    assert r.returncode == 0, r.stderr
    with engine.connect() as c:
        print("ACTUAL_EXTENSION_OWNER_MARK=" + str(c.execute(text(
            "SELECT pg_get_userbyid(extowner), obj_description(oid,'pg_extension') "
            "FROM pg_extension WHERE extname='btree_gist'"
        )).first()), flush=True)
    r = call(["scripts/assert_t9_catalog.py"], db)
    assert r.returncode == 0, r.stdout
    mutations = [
        ("auth_table_renamed", 'ALTER TABLE auth.verification RENAME TO cdx_wrong_verification'),
        ("workflow_index_wrong_columns", "DROP INDEX app.ix_steps_status_updated; "
         "CREATE INDEX ix_steps_status_updated ON app.workflow_steps(id)"),
    ]
    with engine.connect() as c:
        table, trigger = c.execute(text(
            "SELECT x.relname,t.tgname FROM pg_trigger t JOIN pg_class x ON x.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=x.relnamespace "
            "WHERE n.nspname='app' AND NOT t.tgisinternal ORDER BY t.tgname LIMIT 1"
        )).first()
    mutations.append(("trigger_disabled", f'ALTER TABLE app."{table}" DISABLE TRIGGER "{trigger}"'))
    for label, sql in mutations:
        with engine.begin() as c:
            c.execute(text(sql))
        r = call(["scripts/assert_t9_catalog.py"], db)
        print(f"CATALOG_MUTANT={label} RC={r.returncode} RESULT={r.stdout.splitlines()[-1]}", flush=True)
        assert r.returncode == 0, r.stdout
    engine.dispose()

    empty_db = PREFIX + uuid.uuid4().hex[:12]
    owned.add(empty_db)
    ddl(f'CREATE DATABASE "{empty_db}" OWNER dsh_migrator')
    empty_engine = create_engine(BASE + empty_db)
    with empty_engine.begin() as c:
        c.execute(text("CREATE SCHEMA app; CREATE SCHEMA auth; "
                       "CREATE TABLE app.alembic_version(version_num varchar(32) PRIMARY KEY); "
                       "ALTER INDEX app.alembic_version_pkey RENAME TO cdx_wrong_metadata_index; "
                       "CREATE TABLE auth.cdx_leftover(id int PRIMARY KEY)"))
    r = call(["scripts/assert_downgrade_base.py"], empty_db)
    print(f"BASE_AUTH_LEFTOVER_LEGACY_ASSERT_RC={r.returncode}", flush=True)
    assert r.returncode == 0
    for script in ("t9_rollback_drill", "t9_ci_layers"):
        tree = ast.parse((ROOT / "project/scripts" / (script + ".py")).read_text(encoding="utf-8"))
        inline = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                      and isinstance(n.value, str) and "SELECT count(*) FROM pg_tables" in n.value)
        r = call(["-c", inline], empty_db)
        print(f"BASE_MUTANT={script} AUTH_TABLE=1 WRONG_METADATA_INDEX=1 RC={r.returncode}", flush=True)
        assert r.returncode == 0, r.stderr
    empty_engine.dispose()

    # Fault at ALTER OWNER: CREATE already committed, created flag still false.
    for name in ("t9_rollback_drill", "t9_ci_layers"):
        m = load(name)
        m.BASE_URL = BASE + "dsh_test"
        m.ADMIN_URL = BASE + "postgres"
        m.BACKEND = ROOT / "_experiment/_interop/from-cdx/r112-nonexistent-fixture-root"
        m.uuid.uuid4 = lambda: type("Fixed", (), {"hex": uuid.uuid1().hex})()
        leaked = []

        def injected(sql):
            if sql.startswith("CREATE DATABASE "):
                target = sql.split()[-1]
                assert target.startswith(("dsh_test_t9_", "dsh_test_ci_"))
                owned.add(target)
                leaked.append(target)
                ddl(sql)
            elif sql.startswith("ALTER DATABASE "):
                raise RuntimeError("R112_INJECT_AFTER_CREATE")
            else:
                ddl(sql)

        m._admin_sql = injected
        # Skip pre-DB lint/unit only; database/finally execute original main.
        m.run = lambda *a, **k: None
        try:
            m.main()
        except RuntimeError as exc:
            assert str(exc) == "R112_INJECT_AFTER_CREATE"
        else:
            raise AssertionError("injected error missing")
        with admin.connect() as c:
            remains = c.execute(text("SELECT count(*) FROM pg_database WHERE datname=:n"),
                                {"n": leaked[0]}).scalar()
        print(f"EARLY_FAILURE={name} LEAKED_DATABASE={remains}", flush=True)
        assert remains == 1

    m = load("t9_ci_layers")
    m.BASE_URL = BASE + "dsh_test"
    m.BACKEND = ROOT / "_experiment/_interop/from-cdx/r112-nonexistent-fixture-root"
    phase_db = []
    executed = []

    def phase_admin(sql):
        if sql.startswith("CREATE DATABASE "):
            target = sql.split()[-1]
            assert target.startswith("dsh_test_ci_")
            owned.add(target)
            phase_db.append(target)
        ddl(sql)

    def phase_run(cmd, **kwargs):
        executed.append(cmd)
        if "alembic" in cmd:
            raise SystemExit(17)

    m._admin_sql = phase_admin
    m.run = phase_run
    try:
        m.main()
    except SystemExit as exc:
        assert exc.code == 17
    else:
        raise AssertionError("migration failure swallowed")
    with admin.connect() as c:
        remains = c.execute(text("SELECT count(*) FROM pg_database WHERE datname=:n"),
                            {"n": phase_db[0]}).scalar()
    job4_ran = any("scripts/assert_t9_catalog.py" in cmd for cmd in executed)
    print(f"MIGRATION_FAILURE_RC=17 JOB4_RAN={job4_ran} DB_REMAINS={remains}", flush=True)
    assert not job4_ran and remains == 0
finally:
    for name in sorted(owned):
        assert name.startswith((PREFIX, "dsh_test_t9_", "dsh_test_ci_"))
        ddl(f'DROP DATABASE IF EXISTS "{name}" (FORCE)')
        print("PROBE_CLEANUP=" + name, flush=True)
    admin.dispose()
