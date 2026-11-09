"""Composition root of platform-api. Today: the access module. Next: chat, agent, approval, project, history, skills.

Run:  uv run uvicorn platform_api.main:app --port 8000
"""

from __future__ import annotations

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
    access = create_access_module(
        Path(env("SUPERAI_USERS_FILE", str(HERE / "config/users.yaml"))),
        Path(env("SUPERAI_ROLE_LOG", str(HERE / "var/role-changes.jsonl"))),
    )

    def current_user(request: Request) -> str | None:
        if mode == "dev":
            return request.headers.get("x-user-id")  # dev only: "Viewing as" switcher in the web app
        return None  # prod: company SSO session (not wired yet) -> every request is 401

    return Starlette(routes=[*access_routes(access.admin, current_user)])


app = build_app()
