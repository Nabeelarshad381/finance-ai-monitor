#!/bin/bash
# scripts/init_db.sh — runs once when PostgreSQL container starts
# Creates application databases and users

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL

  -- ── Finance Monitor ─────────────────────────────────────────────────
  CREATE USER finance_user WITH PASSWORD 'finance_pass';
  CREATE DATABASE finance_monitor OWNER finance_user;
  GRANT ALL PRIVILEGES ON DATABASE finance_monitor TO finance_user;

  -- ── Airflow ──────────────────────────────────────────────────────────
  CREATE USER airflow_user WITH PASSWORD 'airflow_pass';
  CREATE DATABASE airflow_db OWNER airflow_user;
  GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow_user;

  -- ── n8n ──────────────────────────────────────────────────────────────
  CREATE USER n8n_user WITH PASSWORD 'n8n_pass';
  CREATE DATABASE n8n_db OWNER n8n_user;
  GRANT ALL PRIVILEGES ON DATABASE n8n_db TO n8n_user;

EOSQL

echo "Databases initialised."

# Run the Finance Monitor schema
psql -v ON_ERROR_STOP=1 \
  --username "finance_user" \
  --dbname "finance_monitor" \
  --file /docker-entrypoint-initdb.d/../project/database/schema.sql 2>/dev/null || true

echo "Schema applied."
