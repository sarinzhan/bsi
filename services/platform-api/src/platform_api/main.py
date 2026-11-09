"""Composition root of platform-api. Today: the access module. Next: chat, agent, approval, project, history, skills.

Run:  uv run uvicorn platform_api.main:app --port 8000      (API docs: http://localhost:8000/docs)
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from fastapi import FastAPI, Request

from platform_api.access import create_access_module
from platform_api.access.adapters.http_api import access_router

HERE = Path(__file__).resolve().parents[2]


def build_app() -> FastAPI:
    env = os.environ.get
    mode = env("SUPERAI_MODE", "dev")

    # Postgres when SUPERAI_DATABASE_URL is set (required in prod); otherwise YAML + JSONL files.
    database_url = env("SUPERAI_DATABASE_URL")
    if mode == "prod" and not database_url:
        raise RuntimeError("SUPERAI_DATABASE_URL is required in prod")
    engine = None
    if database_url:
        from platform_api.db import make_engine, migrate

        migrate(database_url)  # alembic upgrade head
        engine = make_engine(database_url)

    access = create_access_module(
        Path(env("SUPERAI_USERS_FILE", str(HERE / "config/users.yaml"))),  # seeds an empty database
        Path(env("SUPERAI_ROLE_LOG", str(HERE / "var/role-changes.jsonl"))),
        engine,
    )

    def current_user(request: Request) -> str | None:
        if mode == "dev":
            return request.headers.get("x-user-id")  # dev only: "Viewing as" switcher in the web app
        return None  # prod: company SSO session (not wired yet) -> every request is 401

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    app = FastAPI(title="superAI platform-api", lifespan=lifespan)
    app.include_router(access_router(access.admin, current_user))
    return app


app = build_app()
