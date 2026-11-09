"""Shared fixtures. Postgres tests need a database:

    docker compose up -d postgres
    export SUPERAI_TEST_DATABASE_URL=postgresql://platform:dev-platform@localhost:5432/platform_test

Each test gets its own schema (dropped afterwards), so tests never see each other's rows.
Without the variable, Postgres tests are skipped.
"""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from platform_api.db import make_engine, migrate, sqlalchemy_url

TEST_DATABASE_URL = os.environ.get("SUPERAI_TEST_DATABASE_URL")

# Tests never use the developer's own service settings (e.g. an exported SUPERAI_DATABASE_URL):
# some test modules import main.py, which builds the app at import time.
for _name in [n for n in os.environ if n.startswith("SUPERAI_") and n != "SUPERAI_TEST_DATABASE_URL"]:
    del os.environ[_name]


@pytest.fixture
def pg():
    """(engine, url) bound to a fresh schema, migrated to the newest Alembic revision."""
    if not TEST_DATABASE_URL:
        pytest.skip("set SUPERAI_TEST_DATABASE_URL to run the Postgres tests")
    schema = f"test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(sqlalchemy_url(TEST_DATABASE_URL), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    url = make_url(TEST_DATABASE_URL).update_query_dict({"options": f"-c search_path={schema}"})
    url = url.render_as_string(hide_password=False)
    migrate(url)
    engine = make_engine(url)
    try:
        yield engine, url
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()
