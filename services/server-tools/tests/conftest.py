"""Shared fixtures. Postgres tests need a database:

    docker compose up -d postgres
    export SUPERAI_TEST_DATABASE_URL=postgresql://server_tools:dev-server-tools@localhost:5432/server_tools_test

Each test gets its own schema (dropped afterwards), so tests never see each other's rows.
Without the variable, Postgres tests are skipped.
"""

import os
import uuid

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from server_tools.db import migrate, open_pool

TEST_DATABASE_URL = os.environ.get("SUPERAI_TEST_DATABASE_URL")


@pytest.fixture
def pg():
    """(pool, conninfo) bound to a fresh schema with all migrations applied."""
    if not TEST_DATABASE_URL:
        pytest.skip("set SUPERAI_TEST_DATABASE_URL to run the Postgres tests")
    schema = f"test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    conninfo = make_conninfo(TEST_DATABASE_URL, options=f"-c search_path={schema}")
    migrate(conninfo)
    pool = open_pool(conninfo)
    try:
        yield pool, conninfo
    finally:
        pool.close()
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA {schema} CASCADE")
