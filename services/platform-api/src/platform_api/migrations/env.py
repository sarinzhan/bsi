"""Alembic environment for platform-api. Run from the service folder: `uv run alembic <command>`.

The URL comes from `migrate()` (config.attributes["url"]) or from BSI_DATABASE_URL.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool, text

from platform_api.db import Base, sqlalchemy_url

# Import every module's ORM models, so autogenerate sees all tables. Add new modules here.
import platform_api.access.repositories.postgres  # noqa: E402,F401
import platform_api.agent.repositories.postgres  # noqa: E402,F401
import platform_api.servers.repositories.postgres  # noqa: E402,F401
import platform_api.chat.repositories.postgres  # noqa: E402,F401
import platform_api.approval.repositories.postgres  # noqa: E402,F401
import platform_api.tools.repositories.postgres  # noqa: E402,F401

LOCK = 7_420_002  # two replicas starting at once do not migrate twice

config = context.config
url = config.attributes.get("url") or sqlalchemy_url(os.environ["BSI_DATABASE_URL"])


def run_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it (for review)."""
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK})  # released on commit
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
