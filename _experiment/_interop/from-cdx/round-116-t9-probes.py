"""Focused T9 gates; mutations restored individually in an owned database."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
BASE = "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/"
db = "cdx_r116_" + uuid.uuid4().hex[:12]
admin = create_engine(BASE + "postgres", isolation_level="AUTOCOMMIT")
eng = None
created = False


def call(args):
    return subprocess.run([sys.executable, *args], cwd=ROOT / "project",
                          env=dict(os.environ, DATABASE_URL=BASE + db, MIGRATION_ROLE="dsh_migrator", PYTHONUTF8="1"),
                          capture_output=True, text=True, encoding="utf-8", timeout=100)


def change(sql):
    with eng.begin() as c:
        c.execute(text(sql))


def mutant(name, sql, undo, expect, script="assert_t9_catalog.py"):
    change(sql)
    try:
        r = call(["scripts/" + script])
        print(f"MUTANT={name} RC={r.returncode}", flush=True)
        assert r.returncode == expect, r.stdout + r.stderr
    finally:
        change(undo)


try:
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{db}" OWNER dsh_migrator'))
    created = True
    eng = create_engine(BASE + db)
    r = call(["-m", "alembic", "upgrade", "head"])
    assert r.returncode == 0, r.stderr
    assert call(["scripts/assert_t9_catalog.py"]).returncode == 0
    with eng.connect() as c:
        enum = c.execute(text("SELECT typname FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
                              "WHERE n.nspname='app' AND typtype='e' ORDER BY typname LIMIT 1")).scalar()
        tbl, trg, td = c.execute(text("SELECT x.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t "
                                     "JOIN pg_class x ON x.oid=t.tgrelid JOIN pg_namespace n ON n.oid=x.relnamespace "
                                     "WHERE n.nspname='app' AND NOT t.tgisinternal ORDER BY tgname LIMIT 1")).first()
        ix = c.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname='app' "
                             "AND indexname='ix_steps_status_updated'")).scalar()
        ft, fk, fd = c.execute(text("SELECT x.relname,conname,pg_get_constraintdef(k.oid) FROM pg_constraint k "
                                   "JOIN pg_class x ON x.oid=k.conrelid JOIN pg_namespace n ON n.oid=x.relnamespace "
                                   "WHERE n.nspname='app' AND contype='f' AND array_length(conkey,1)=2 "
                                   "ORDER BY conname LIMIT 1")).first()
        px, pd = c.execute(text("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='app' "
                                "AND indexname LIKE 'px_%' ORDER BY indexname LIMIT 1")).first()
    restore_ix = "DROP INDEX app.ix_steps_status_updated; " + ix
    restore_fk = f'ALTER TABLE app."{ft}" ADD CONSTRAINT "{fk}" {fd}'
    drop_fk = f'ALTER TABLE app."{ft}" DROP CONSTRAINT "{fk}"'
    for args in [
        ("auth_rename", "ALTER TABLE auth.verification RENAME TO cdx_bad", "ALTER TABLE auth.cdx_bad RENAME TO verification", 1),
        ("n1_wrong_columns", "DROP INDEX app.ix_steps_status_updated; CREATE INDEX ix_steps_status_updated ON app.workflow_steps(id)", restore_ix, 1),
        ("trigger_disabled", f'ALTER TABLE app."{tbl}" DISABLE TRIGGER "{trg}"', f'ALTER TABLE app."{tbl}" ENABLE TRIGGER "{trg}"', 1),
        ("enum_rename", f'ALTER TYPE app."{enum}" RENAME TO cdx_bad_enum', f'ALTER TYPE app.cdx_bad_enum RENAME TO "{enum}"', 1),
        ("trigger_rename", f'ALTER TRIGGER "{trg}" ON app."{tbl}" RENAME TO cdx_bad_trigger', f'ALTER TRIGGER cdx_bad_trigger ON app."{tbl}" RENAME TO "{trg}"', 1),
        ("composite_fk_missing", drop_fk, restore_fk, 1),
        ("n1_false_predicate", "DROP INDEX app.ix_steps_status_updated; CREATE INDEX ix_steps_status_updated ON app.workflow_steps(status,updated_at) WHERE false", restore_ix, 1),
        ("n1_wrong_table", "DROP INDEX app.ix_steps_status_updated; CREATE INDEX ix_steps_status_updated ON app.workflow_runs(status,updated_at)", restore_ix, 0),
        ("partial_nonunique", f'DROP INDEX app."{px}"; ' + pd.replace("CREATE UNIQUE INDEX", "CREATE INDEX", 1), f'DROP INDEX app."{px}"; ' + pd, 0),
        ("composite_fk_not_valid", drop_fk + "; " + restore_fk + " NOT VALID", drop_fk + "; " + restore_fk, 0),
    ]:
        mutant(*args)
    noop = "CREATE FUNCTION app.cdx_noop() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$"
    mutant("trigger_noop_binding", noop + f'; DROP TRIGGER "{trg}" ON app."{tbl}"; ' +
           re.sub(r"EXECUTE FUNCTION .*$", "EXECUTE FUNCTION app.cdx_noop()", td),
           f'DROP TRIGGER "{trg}" ON app."{tbl}"; ' + td + "; DROP FUNCTION app.cdx_noop()", 0)
    r = call(["-m", "alembic", "downgrade", "base"])
    assert r.returncode == 0, r.stderr
    with eng.connect() as c:
        pk = c.execute(text("SELECT conname FROM pg_constraint WHERE conrelid='app.alembic_version'::regclass AND contype='p'")).scalar()
    mutant("base_fake_pk", f'ALTER TABLE app.alembic_version DROP CONSTRAINT "{pk}"; CREATE INDEX alembic_version_pk_fake ON app.alembic_version(version_num)',
           f'DROP INDEX app.alembic_version_pk_fake; ALTER TABLE app.alembic_version ADD CONSTRAINT "{pk}" PRIMARY KEY(version_num)', 1, "assert_t9_base.py")
    mutant("base_owned_extension", "CREATE EXTENSION btree_gist; COMMENT ON EXTENSION btree_gist IS 'created_by_migration_32f34131a28a'",
           "DROP EXTENSION btree_gist", 1, "assert_t9_base.py")

    # Run original CI lifecycle with a first-phase fault; only reviewer-owned file roots.
    spec = importlib.util.spec_from_file_location("r116_ci", ROOT / "project/scripts/t9_ci_layers.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.BASE_URL = BASE + db
    m.BACKEND = ROOT / "_experiment/_interop/from-cdx"
    before = set(m.BACKEND.glob(".pytest-tmp-ci-*"))
    m.run = lambda *a, **k: (_ for _ in ()).throw(SystemExit(17))
    try:
        m.main()
    except SystemExit as exc:
        assert exc.code == 17
    else:
        raise AssertionError("phase fault missing")
    left = set(m.BACKEND.glob(".pytest-tmp-ci-*")) - before
    print(f"CI_LINT_FAILURE_LEFT_ROOTS={len(left)}", flush=True)
    assert len(left) == 1
    # Remove only empty directories generated by this exact invocation.
    for root in left:
        assert root.resolve().parent == m.BACKEND.resolve()
        for child in root.iterdir():
            child.rmdir()
        root.rmdir()
    print("REVIEWER_FILE_ROOT_CLEANUP=PASS", flush=True)
finally:
    if eng:
        eng.dispose()
    if created:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" (FORCE)'))
        print("DATABASE_REMOVED=" + db, flush=True)
    admin.dispose()
