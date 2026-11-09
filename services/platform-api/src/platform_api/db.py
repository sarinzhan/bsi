"""Database plumbing for the composition root: SQLAlchemy engine, ORM base class, Alembic migrations.

Each module declares its own ORM models (in its adapters) on `Base`; Alembic sees all of them.
Migrations live in `migrations/versions/`. New one after changing a model:

    uv run alembic revision --autogenerate -m "add column x"     # then read and fix the file
    uv run alembic upgrade head                                  # or just start the service
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase

MIGRATIONS = Path(__file__).with_name("migrations")


class Base(DeclarativeBase):
    # Stable constraint names, so Alembic can find and change them later.
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


def sqlalchemy_url(url: str) -> str:
    """Accepts a plain postgresql:// URL and selects the psycopg 3 driver."""
    parsed = make_url(url)
    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def make_engine(url: str) -> Engine:
    return create_engine(sqlalchemy_url(url), pool_size=5, max_overflow=5, pool_pre_ping=True)


def migrate(url: str) -> None:
    """Upgrades the database to the newest migration (`alembic upgrade head`)."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.attributes["url"] = sqlalchemy_url(url)  # not via set_main_option: '%' in URLs breaks configparser
    command.upgrade(config, "head")
