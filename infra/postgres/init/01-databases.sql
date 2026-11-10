-- Runs once, when the postgres volume is created (docker compose, local dev only).
-- One database + login for platform-api (the only service with a database).

CREATE ROLE platform LOGIN PASSWORD 'dev-platform';
CREATE DATABASE platform OWNER platform;
REVOKE ALL ON DATABASE platform FROM PUBLIC;

-- Databases for the Postgres adapter tests (each test run uses its own schema and drops it).
CREATE DATABASE platform_test OWNER platform;
REVOKE ALL ON DATABASE platform_test FROM PUBLIC;
