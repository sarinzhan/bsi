"""Shared fixtures. Postgres tests need a database:

    docker compose up -d postgres
    export BSI_TEST_DATABASE_URL=postgresql://platform:dev-platform@localhost:5432/platform_test

Each test gets its own schema (dropped afterwards), so tests never see each other's rows.
Without the variable, Postgres tests are skipped.
"""

import os
import uuid
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from platform_api.db import make_engine, migrate, sqlalchemy_url

TEST_DATABASE_URL = os.environ.get("BSI_TEST_DATABASE_URL")

# Tests never use the developer's own service settings (e.g. an exported BSI_DATABASE_URL):
# some test modules import main.py, which builds the app at import time.
for _name in [n for n in os.environ if n.startswith("BSI_") and n != "BSI_TEST_DATABASE_URL"]:
    del os.environ[_name]


@pytest.fixture
def pg():
    """(engine, url) bound to a fresh schema, migrated to the newest Alembic revision."""
    if not TEST_DATABASE_URL:
        pytest.skip("set BSI_TEST_DATABASE_URL to run the Postgres tests")
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


# ---- test data (the platform itself has none: users sign in, servers are added in the web app) ----

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def sample_users():
    """sarinzha (developer), aibek (devops), timur (developer + devops), dana (admin)."""
    from platform_api.access.models import Role, User

    raw = yaml.safe_load((FIXTURES / "users.yaml").read_text())["users"]
    return [User(uid, u["name"], frozenset(Role(r) for r in u["roles"])) for uid, u in raw.items()]


def sample_servers():
    """dev-docker-01 (superapp), dev-docker-02 (tiffany), stage-docker-01, prod-docker-01."""
    from platform_api.servers.models import Env, Server

    raw = yaml.safe_load((FIXTURES / "servers.yaml").read_text())["servers"]
    return [Server(name, s["host"], Env(s["env"]), frozenset(s.get("allowed_tools") or []),
                   frozenset(s.get("systems") or [])) for name, s in raw.items()]


def make_access(engine=None, admins=()):
    from platform_api.access import create_access_module

    return create_access_module(engine, admins=admins, users=sample_users())
