"""Composition root of platform-api. Today: the access module. Next: chat, agent, approval, project, history, skills.

Run:  uv run uvicorn platform_api.main:app --port 8000
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request

from platform_api.access import create_access_module
from platform_api.access.adapters.http_api import access_routes

HERE = Path(__file__).resolve().parents[2]


def build_app() -> Starlette:
    env = os.environ.get
    mode = env("SUPERAI_MODE", "dev")

    # Postgres when SUPERAI_DATABASE_URL is set (required in prod); otherwise YAML + JSONL files.
    database_url = env("SUPERAI_DATABASE_URL")
    if mode == "prod" and not database_url:
        raise RuntimeError("SUPERAI_DATABASE_URL is required in prod")
    pool = None
    if database_url:
        from platform_api.db import migrate, open_pool

        migrate(database_url)
        pool = open_pool(database_url)

    access = create_access_module(
        Path(env("SUPERAI_USERS_FILE", str(HERE / "config/users.yaml"))),  # seeds an empty database
        Path(env("SUPERAI_ROLE_LOG", str(HERE / "var/role-changes.jsonl"))),
        pool,
    )

    def current_user(request: Request) -> str | None:
        if mode == "dev":
            return request.headers.get("x-user-id")  # dev only: "Viewing as" switcher in the web app
        return None  # prod: company SSO session (not wired yet) -> every request is 401

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette):
        try:
            yield
        finally:
            if pool is not None:
                pool.close()

    return Starlette(routes=[*access_routes(access.admin, current_user)], lifespan=lifespan)


app = build_app()
