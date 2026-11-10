"""Round-120: replay round-119 claims and probe residual definition gaps."""
import os
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
old = Path(__file__).with_name("round-118-t9-probes.py")
source = old.read_text(encoding="utf-8")
replacements = {
    '"cdx_r118_defs_"': '"cdx_r120_replay_"',
    'assert r.returncode == 0, r.stdout + r.stderr\n        finally:':
        'assert r.returncode == 1, r.stdout + r.stderr\n        finally:',
    'assert r.returncode == 1 and "INVALID_POLICY_REF" in r.stdout, r.stdout + r.stderr':
        'assert r.returncode == 0 and "T3-PROBES: PASS" in r.stdout, r.stdout + r.stderr',
}
for before, after in replacements.items():
    assert source.count(before) == 1, before
    source = source.replace(before, after)
print("REPLAY=13_existing_plus_3_round119_mutants_expect_RC1_and_T3_expect_PASS", flush=True)
exec(compile(source, str(old), "exec"), {"__name__": "__main__", "__file__": str(old)})

BASE = "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/"
db = "cdx_r120_defs_" + uuid.uuid4().hex[:12]
admin = create_engine(BASE + "postgres", isolation_level="AUTOCOMMIT")
eng = None
created = False


def call(script):
    return subprocess.run(
        [sys.executable, script], cwd=ROOT / "project",
        env=dict(os.environ, DATABASE_URL=BASE + db, MIGRATION_ROLE="dsh_migrator", PYTHONUTF8="1"),
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )


def mutate(label, sql):
    with eng.begin() as conn:
        conn.execute(text(sql))
    result = call("scripts/assert_t9_catalog.py")
    print(f"RESIDUAL_MUTANT={label} RC={result.returncode}", flush=True)
    if result.returncode:
        print(result.stdout[-1200:], flush=True)
    assert result.returncode == 0, result.stdout + result.stderr


try:
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db}" OWNER dsh_migrator'))
    created = True
    eng = create_engine(BASE + db)
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "project",
        env=dict(os.environ, DATABASE_URL=BASE + db, MIGRATION_ROLE="dsh_migrator", PYTHONUTF8="1"),
        capture_output=True, text=True, encoding="utf-8", timeout=180,
    )
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr

    mutate(
        "same_name_notice_return_new_body",
        """CREATE OR REPLACE FUNCTION app.fn_cost_context_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE NOTICE 'r120'; RETURN NEW; END $$""",
    )
    mutate(
        "partial_index_wrong_columns",
        """DROP INDEX app.px_tenants_name;
        CREATE UNIQUE INDEX px_tenants_name ON app.tenants(public_id) WHERE deleted_at IS NULL""",
    )
    mutate(
        "unlisted_composite_fk_delete_action",
        """ALTER TABLE app.shops DROP CONSTRAINT fk_shops_platform_accounts;
        ALTER TABLE app.shops ADD CONSTRAINT fk_shops_platform_accounts
        FOREIGN KEY (tenant_id, account_id) REFERENCES app.platform_accounts(tenant_id, id)
        ON DELETE SET NULL""",
    )
finally:
    if eng is not None:
        eng.dispose()
    if created:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db}" (FORCE)'))
        print("DATABASE_REMOVED=" + db, flush=True)
    admin.dispose()
