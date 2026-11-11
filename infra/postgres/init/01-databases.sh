#!/bin/sh
# Runs once, when the postgres volume is created. One database + login for platform-api.
# The login's password comes from PLATFORM_DB_PASSWORD (.env), the same value platform-api connects with.
# Changing it later in .env does NOT change it here: run ALTER ROLE (deploy/single-vm/README.md).
set -eu
psql -v ON_ERROR_STOP=1 -v pw="${PLATFORM_DB_PASSWORD:-dev-platform}" --username "$POSTGRES_USER" --dbname postgres <<'SQL'
CREATE ROLE platform LOGIN PASSWORD :'pw';
CREATE DATABASE platform OWNER platform;
REVOKE ALL ON DATABASE platform FROM PUBLIC;

-- Databases for the Postgres repository tests (each test run uses its own schema and drops it).
CREATE DATABASE platform_test OWNER platform;
REVOKE ALL ON DATABASE platform_test FROM PUBLIC;
SQL
