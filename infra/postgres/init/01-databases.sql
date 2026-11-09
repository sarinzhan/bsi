-- Runs once, when the postgres volume is created (docker compose, local dev only).
-- One database + one login per service. A service cannot connect to another service's database.

CREATE ROLE server_tools LOGIN PASSWORD 'dev-server-tools';
CREATE DATABASE server_tools OWNER server_tools;
REVOKE ALL ON DATABASE server_tools FROM PUBLIC;

CREATE ROLE platform LOGIN PASSWORD 'dev-platform';
CREATE DATABASE platform OWNER platform;
REVOKE ALL ON DATABASE platform FROM PUBLIC;

-- Databases for the Postgres adapter tests (each test run uses its own schema and drops it).
CREATE DATABASE server_tools_test OWNER server_tools;
REVOKE ALL ON DATABASE server_tools_test FROM PUBLIC;
CREATE DATABASE platform_test OWNER platform;
REVOKE ALL ON DATABASE platform_test FROM PUBLIC;
