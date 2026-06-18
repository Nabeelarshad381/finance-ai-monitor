"""
scripts/apply_schema.py
Apply (or re-apply) the PostgreSQL schema to the finance_monitor database.
Safe to run multiple times — uses IF NOT EXISTS and ON CONFLICT throughout.

Usage:
    python scripts/apply_schema.py
    python scripts/apply_schema.py --host localhost --port 5432
    python scripts/apply_schema.py --drop   # WARNING: drops all tables first
"""

import argparse
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("apply_schema")

SCHEMA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "database", "schema.sql")

DROP_SQL = """
DO $$ DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;
DROP EXTENSION IF EXISTS "uuid-ossp" CASCADE;
DROP EXTENSION IF EXISTS "pg_trgm" CASCADE;
"""


def apply_schema(host: str, port: int, dbname: str,
                 user: str, password: str, drop_first: bool = False):
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    dsn = f"host={host} port={port} dbname={dbname} user={user} password={password}"
    logger.info("Connecting to: %s:%s/%s as %s", host, port, dbname, user)

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        cur = conn.cursor()

        if drop_first:
            confirm = input("⚠️  This will DROP ALL TABLES. Type 'yes' to confirm: ").strip()
            if confirm.lower() != "yes":
                logger.info("Aborted.")
                sys.exit(0)
            logger.warning("Dropping all tables...")
            cur.execute(DROP_SQL)
            logger.info("All tables dropped.")

        logger.info("Reading schema from: %s", SCHEMA_FILE)
        with open(SCHEMA_FILE, "r") as f:
            schema_sql = f.read()

        cur.execute(schema_sql)
        logger.info("✅ Schema applied successfully.")

        # Verify tables created
        cur.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        tables = [row[0] for row in cur.fetchall()]
        logger.info("Tables in database: %s", ", ".join(tables))

        cur.close()
        conn.close()

    except psycopg2.OperationalError as exc:
        logger.error("❌ Connection failed: %s", exc)
        logger.error("Check your PostgreSQL credentials and ensure the server is running.")
        sys.exit(1)
    except Exception as exc:
        logger.error("❌ Schema apply failed: %s", exc)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Apply Finance Monitor DB schema")
    parser.add_argument("--host",     default=os.getenv("POSTGRES_HOST",     "localhost"))
    parser.add_argument("--port",     default=int(os.getenv("POSTGRES_PORT", "5432")), type=int)
    parser.add_argument("--dbname",   default=os.getenv("POSTGRES_DB",       "finance_monitor"))
    parser.add_argument("--user",     default=os.getenv("POSTGRES_USER",     "finance_user"))
    parser.add_argument("--password", default=os.getenv("POSTGRES_PASSWORD", "finance_pass"))
    parser.add_argument("--drop",     action="store_true",
                        help="Drop all tables before applying schema (DESTRUCTIVE)")
    args = parser.parse_args()

    apply_schema(
        host=args.host, port=args.port, dbname=args.dbname,
        user=args.user, password=args.password, drop_first=args.drop,
    )


if __name__ == "__main__":
    main()
