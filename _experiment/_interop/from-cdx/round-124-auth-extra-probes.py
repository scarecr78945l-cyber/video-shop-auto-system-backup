# -*- coding: utf-8 -*-
"""Round-124: prove whether the auth catalog gate rejects extra objects."""

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


def sql(url: str, statement: str, *, autocommit: bool = False) -> None:
    engine = create_engine(url, isolation_level="AUTOCOMMIT" if autocommit else None)
    try:
        with engine.begin() as conn:
            conn.execute(text(statement))
    finally:
        engine.dispose()


def run_gate(url: str) -> subprocess.CompletedProcess[str]:
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
    dbname = "cdx_r124_" + uuid.uuid4().hex[:10]
    url = BASE_URL.rsplit("/", 1)[0] + "/" + dbname
    created = False
    results: list[tuple[str, int]] = []
    try:
        sql(ADMIN_URL, f"CREATE DATABASE {dbname}", autocommit=True)
        created = True
        sql(ADMIN_URL, f"ALTER DATABASE {dbname} OWNER TO dsh_migrator", autocommit=True)
        env = dict(os.environ)
        env.update(DATABASE_URL=url, MIGRATION_ROLE="dsh_migrator", PYTHONUTF8="1")
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJECT,
            env=env,
            check=True,
            timeout=300,
        )
        baseline = run_gate(url)
        print(f"BASELINE_RC={baseline.returncode}")
        if baseline.returncode != 0:
            print(baseline.stdout[-3000:])
            print(baseline.stderr[-3000:])
            return 2

        mutations = (
            (
                "EXTRA_COLUMN",
                'ALTER TABLE auth."user" ADD COLUMN cdx_extra text',
                'ALTER TABLE auth."user" DROP COLUMN cdx_extra',
            ),
            (
                "EXTRA_UNIQUE_INDEX",
                'CREATE UNIQUE INDEX cdx_extra_user_name_uidx ON auth."user" (name)',
                'DROP INDEX auth.cdx_extra_user_name_uidx',
            ),
            (
                "EXTRA_FOREIGN_KEY",
                'ALTER TABLE auth.account ADD CONSTRAINT cdx_extra_account_user_fk '
                'FOREIGN KEY (user_id) REFERENCES auth."user" (id) ON DELETE CASCADE',
                'ALTER TABLE auth.account DROP CONSTRAINT cdx_extra_account_user_fk',
            ),
        )
        for name, apply_sql, restore_sql in mutations:
            sql(url, apply_sql)
            try:
                result = run_gate(url)
                results.append((name, result.returncode))
                print(f"{name}_RC={result.returncode}")
                if result.returncode != 0:
                    decisive = [line for line in result.stdout.splitlines() if "auth " in line and "FAIL" in line]
                    print(f"{name}_FAIL_LINES={decisive}")
            finally:
                sql(url, restore_sql)
            restored = run_gate(url)
            print(f"{name}_RESTORE_RC={restored.returncode}")

        missed = [name for name, rc in results if rc == 0]
        print(f"MISSED_EXTRA_OBJECTS={missed}")
        return 1 if missed else 0
    finally:
        if created:
            sql(ADMIN_URL, f"DROP DATABASE IF EXISTS {dbname} (FORCE)", autocommit=True)
            print(f"TEMP_DB_DROPPED={dbname}")


if __name__ == "__main__":
    raise SystemExit(main())
