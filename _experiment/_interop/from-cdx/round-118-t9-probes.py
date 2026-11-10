"""Replay the reviewed historical harness with corrected expectations; add focused definition probes."""
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
old = Path(__file__).with_name("round-116-t9-probes.py")
source = old.read_text(encoding="utf-8")
replacements = {
    '"cdx_r116_"': '"cdx_r118_replay_"',
    'restore_ix, 0),': 'restore_ix, 1),',
    'f\'DROP INDEX app."{px}"; \' + pd, 0),': 'f\'DROP INDEX app."{px}"; \' + pd, 1),',
    'drop_fk + "; " + restore_fk, 0),': 'drop_fk + "; " + restore_fk, 1),',
    '+ "; DROP FUNCTION app.cdx_noop()", 0)': '+ "; DROP FUNCTION app.cdx_noop()", 1)',
    'assert len(left) == 1': 'assert len(left) == 0',
}
for before, after in replacements.items():
    assert source.count(before) == 1, before
    source = source.replace(before, after)
print("REPLAY=13_negative_cases_expect_RC1_and_lint_cleanup_expect_zero", flush=True)
exec(compile(source, str(old), "exec"), {"__name__": "__main__", "__file__": str(old)})

BASE = "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/"
db = "cdx_r118_defs_" + uuid.uuid4().hex[:12]
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


try:
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{db}" OWNER dsh_migrator'))
    created = True
    eng = create_engine(BASE + db)
    r = call(["-m", "alembic", "upgrade", "head"])
    assert r.returncode == 0, r.stderr
    with eng.connect() as c:
        table, trigger, definition = c.execute(text(
            "SELECT x.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t "
            "JOIN pg_class x ON x.oid=t.tgrelid JOIN pg_namespace n ON n.oid=x.relnamespace "
            "WHERE n.nspname='app' AND NOT t.tgisinternal ORDER BY tgname LIMIT 1")).first()
        px, pd = c.execute(text("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='app' "
                                "AND indexname LIKE 'px_%' ORDER BY indexname LIMIT 1")).first()
        ft, fk, fd = c.execute(text("SELECT x.relname,conname,pg_get_constraintdef(k.oid) FROM pg_constraint k "
                                   "JOIN pg_class x ON x.oid=k.conrelid JOIN pg_namespace n ON n.oid=x.relnamespace "
                                   "WHERE n.nspname='app' AND contype='f' AND array_length(conkey,1)=2 "
                                   "ORDER BY conname LIMIT 1")).first()
    drop_trg = f'DROP TRIGGER "{trigger}" ON app."{table}"; '
    bad_def = re.sub(r"EXECUTE FUNCTION .*$", "EXECUTE FUNCTION app.fn_fixture_passthrough()", definition)
    fd_changed = re.sub(r" ON DELETE (NO ACTION|RESTRICT|CASCADE|SET NULL|SET DEFAULT)", "", fd) + " ON DELETE SET NULL"
    drop_fk = f'ALTER TABLE app."{ft}" DROP CONSTRAINT "{fk}"; '
    add_fk = f'ALTER TABLE app."{ft}" ADD CONSTRAINT "{fk}" '
    cases = [
        ("renamed_noop_function", "CREATE FUNCTION app.fn_fixture_passthrough() RETURNS trigger LANGUAGE plpgsql "
         "AS $$ BEGIN RETURN NEW; END $$; " + drop_trg + bad_def,
         drop_trg + definition + "; DROP FUNCTION app.fn_fixture_passthrough()"),
        ("partial_predicate_false", f'DROP INDEX app."{px}"; ' + re.sub(r" WHERE .*$", " WHERE false", pd),
         f'DROP INDEX app."{px}"; ' + pd),
        ("fk_delete_action_changed", drop_fk + add_fk + fd_changed, drop_fk + add_fk + fd),
    ]
    for name, sql, undo in cases:
        change(sql)
        try:
            r = call(["scripts/assert_t9_catalog.py"])
            print(f"DEFINITION_MUTANT={name} RC={r.returncode}", flush=True)
            assert r.returncode == 0, r.stdout + r.stderr
        finally:
            change(undo)
    r = call(["scripts/assert_t3_probes.py"])
    print(f"T3_HEAD_PROBE_RC={r.returncode}", flush=True)
    print(r.stdout[-2200:], flush=True)
    assert r.returncode == 1 and "INVALID_POLICY_REF" in r.stdout, r.stdout + r.stderr
    with eng.connect() as c:
        print("T3_PROBE_REMAINING_TENANTS=" + str(c.execute(text("SELECT count(*) FROM app.tenants")).scalar()), flush=True)
finally:
    if eng:
        eng.dispose()
    if created:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" (FORCE)'))
        print("DATABASE_REMOVED=" + db, flush=True)
    admin.dispose()
