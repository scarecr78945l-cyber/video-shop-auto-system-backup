"""Round-122: replay 19 mutants and probe the remaining auth boundary."""
import os
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
old = Path(__file__).with_name("round-120-t9-probes.py")
source = old.read_text(encoding="utf-8")
before = "assert result.returncode == 0, result.stdout + result.stderr"
after = "assert result.returncode == 1, result.stdout + result.stderr"
assert source.count(before) == 1
source = source.replace(before, after)
print("REPLAY=16_existing_plus_3_round121_residual_mutants_expect_RC1", flush=True)
exec(compile(source, str(old), "exec"), {"__name__": "__main__", "__file__": str(old)})

BASE = "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/"
db = "cdx_r122_auth_" + uuid.uuid4().hex[:12]
admin = create_engine(BASE + "postgres", isolation_level="AUTOCOMMIT")
eng = None
created = False
try:
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db}" OWNER dsh_migrator'))
    created = True
    env = dict(os.environ, DATABASE_URL=BASE + db, MIGRATION_ROLE="dsh_migrator", PYTHONUTF8="1")
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "project",
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=180,
    )
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    eng = create_engine(BASE + db)
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE auth.account DROP CONSTRAINT account_user_id_fkey"))
        conn.execute(text(
            'ALTER TABLE auth.account ADD CONSTRAINT account_user_id_fkey '
            'FOREIGN KEY (user_id) REFERENCES auth."user"(id) ON DELETE SET NULL'
        ))
    result = subprocess.run(
        [sys.executable, "scripts/assert_t9_catalog.py"], cwd=ROOT / "project", env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=240,
    )
    print("AUTH_MUTANT=account_fk_delete_set_null RC=" + str(result.returncode), flush=True)
    assert result.returncode == 0, result.stdout + result.stderr
finally:
    if eng is not None:
        eng.dispose()
    if created:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db}" (FORCE)'))
        print("DATABASE_REMOVED=" + db, flush=True)
    admin.dispose()
