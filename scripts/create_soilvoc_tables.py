"""Create the Option 1 tables (soilvoc_types, subject_soilvoc). Idempotent.

Usage: python scripts/create_soilvoc_tables.py [--db 1]

--db 1 = stage (DB_*1 in .env). Stage only: dev is never written.
Runs scripts/sql/create_soilvoc_tables.sql in one transaction as k2xadmin.
"""
import argparse
import sys
from pathlib import Path

import psycopg2
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "scripts" / "sql" / "create_soilvoc_tables.sql"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", choices=("1",), default="1", help="1=stage (msp-kh-stage, schema validate). Dev is never written.")
    args = ap.parse_args()

    env = dotenv_values(ROOT / ".env")
    sfx = args.db
    for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
        if key + sfx not in env:
            sys.exit(f"missing {key}{sfx} in .env")
        env[key] = env[key + sfx]

    conn = psycopg2.connect(host=env["DB_HOST"], port=env["DB_PORT"], dbname=env["DB_NAME"],
                            user=env["DB_USER"], password=env["DB_PASSWORD"], connect_timeout=10)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_FILE.read_text())
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"OK: tables ensured in {env['DB_NAME']}.{env.get('DB_SCHEMA', 'validate')} (db {sfx})")


if __name__ == "__main__":
    main()
