# -*- coding: utf-8 -*-
"""Round-126: test an extra auth FK that reuses an expected name on another table."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "project"
BASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test",
)
ADMIN_URL = os.environ.get(
    "T9_ADMIN_URL",
    "postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/postgres",
)


def execute(url: str, statement: str, *, autocommit: bool = False):
    engine = create_engine(url, isolation_level="AUTOCOMMIT" if autocommit else None)
    try:
        with engine.begin() as conn:
            result = conn.execute(text(statement))
            return result.all() if statement.lstrip().upper().startswith("SELECT") else None
    finally:
        engine.dispose()


def gate(url: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(DATABASE_URL=url, MIGRATION_ROLE="dsh_migrator", PYTHONUTF8="1")
    return subprocess.run(
        [sys.executable, "scripts/assert_t9_catalog.py"],
        cwd=PROJECT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def main() -> int:
    dbname = "fkcollision_" + uuid.uuid4().hex[:10]
    url = BASE_URL.rsplit("/", 1)[0] + "/" + dbname
    created = False
    try:
        execute(ADMIN_URL, f"CREATE DATABASE {dbname}", autocommit=True)
        created = True
        execute(ADMIN_URL, f"ALTER DATABASE {dbname} OWNER TO dsh_migrator", autocommit=True)
        env = dict(os.environ)
        env.update(DATABASE_URL=url, MIGRATION_ROLE="dsh_migrator", PYTHONUTF8="1")
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJECT,
            env=env,
            check=True,
            timeout=300,
        )
        print(f"BASELINE_RC={gate(url).returncode}")

        # Create the extra colliding-name FK first, then recreate the expected FK.
        # The current name-keyed dict keeps only the later expected row.
        execute(
            url,
            'ALTER TABLE auth.session DROP CONSTRAINT session_user_id_fkey; '
            'ALTER TABLE auth.account ADD CONSTRAINT session_user_id_fkey '
            'FOREIGN KEY (user_id) REFERENCES auth."user" (id) ON DELETE CASCADE; '
            'ALTER TABLE auth.session ADD CONSTRAINT session_user_id_fkey '
            'FOREIGN KEY (user_id) REFERENCES auth."user" (id) ON DELETE CASCADE;',
        )
        rows = execute(
            url,
            "SELECT x.relname, con.conname FROM pg_constraint con "
            "JOIN pg_class x ON x.oid=con.conrelid "
            "JOIN pg_namespace n ON n.oid=x.relnamespace "
            "WHERE n.nspname='auth' AND con.contype='f' "
            "AND con.conname='session_user_id_fkey' ORDER BY con.oid",
        )
        result = gate(url)
        print(f"COLLIDING_FKS={rows}")
        print(f"COLLIDING_NAME_EXTRA_FK_RC={result.returncode}")
        fail_lines = [line for line in result.stdout.splitlines() if "auth FK" in line]
        print(f"AUTH_FK_GATE_LINES={fail_lines}")

        execute(
            url,
            'ALTER TABLE auth.account DROP CONSTRAINT session_user_id_fkey; '
            'ALTER TABLE auth.session DROP CONSTRAINT session_user_id_fkey; '
            'ALTER TABLE auth.session ADD CONSTRAINT session_user_id_fkey '
            'FOREIGN KEY (user_id) REFERENCES auth."user" (id) ON DELETE CASCADE;',
        )
        print(f"RESTORE_RC={gate(url).returncode}")
        return 1 if result.returncode == 0 else 0
    finally:
        if created:
            execute(ADMIN_URL, f"DROP DATABASE IF EXISTS {dbname} (FORCE)", autocommit=True)
            print(f"TEMP_DB_DROPPED={dbname}")


if __name__ == "__main__":
    raise SystemExit(main())
