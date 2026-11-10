"""Round-122: apply and restore each round-121 definition mutant independently."""
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
BASE = "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/"
db = "cdx_r122_defs_" + uuid.uuid4().hex[:12]
admin = create_engine(BASE + "postgres", isolation_level="AUTOCOMMIT")
eng = None
created = False


def gate(env):
    return subprocess.run(
        [sys.executable, "scripts/assert_t9_catalog.py"], cwd=ROOT / "project", env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=240,
    )


def change(sql):
    with eng.begin() as conn:
        conn.execute(text(sql))


try:
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db}" OWNER dsh_migrator'))
    created = True
    env = dict(os.environ, DATABASE_URL=BASE + db, MIGRATION_ROLE="dsh_migrator", PYTHONUTF8="1")
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "project", env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=180,
    )
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    eng = create_engine(BASE + db)
    with eng.connect() as conn:
        original_fn = conn.execute(text(
            "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='app' AND p.proname='fn_cost_context_consistency'"
        )).scalar_one()
        original_px = conn.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='app' AND indexname='px_tenants_name'"
        )).scalar_one()
        original_fk = conn.execute(text(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
            "JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='app' "
            "AND c.conname='fk_shops_platform_accounts'"
        )).scalar_one()

    cases = [
        (
            "same_name_notice_return_new_body",
            """CREATE OR REPLACE FUNCTION app.fn_cost_context_consistency() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE NOTICE 'r122'; RETURN NEW; END $$""",
            original_fn,
        ),
        (
            "partial_index_wrong_columns",
            """DROP INDEX app.px_tenants_name;
            CREATE UNIQUE INDEX px_tenants_name ON app.tenants(public_id) WHERE deleted_at IS NULL""",
            "DROP INDEX app.px_tenants_name; " + original_px,
        ),
        (
            "unlisted_composite_fk_delete_action",
            """ALTER TABLE app.shops DROP CONSTRAINT fk_shops_platform_accounts;
            ALTER TABLE app.shops ADD CONSTRAINT fk_shops_platform_accounts
            FOREIGN KEY (tenant_id, account_id) REFERENCES app.platform_accounts(tenant_id, id)
            ON DELETE SET NULL""",
            "ALTER TABLE app.shops DROP CONSTRAINT fk_shops_platform_accounts; "
            "ALTER TABLE app.shops ADD CONSTRAINT fk_shops_platform_accounts " + original_fk,
        ),
    ]
    for label, mutation, restore in cases:
        change(mutation)
        try:
            result = gate(env)
            print(f"INDEPENDENT_MUTANT={label} RC={result.returncode}", flush=True)
            assert result.returncode == 1, result.stdout + result.stderr
        finally:
            change(restore)
    clean = gate(env)
    print("RESTORED_BASELINE_RC=" + str(clean.returncode), flush=True)
    assert clean.returncode == 0, clean.stdout + clean.stderr
finally:
    if eng is not None:
        eng.dispose()
    if created:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db}" (FORCE)'))
        print("DATABASE_REMOVED=" + db, flush=True)
    admin.dispose()
