"""Composition root of platform-api. Modules: access, agent. Next: chat, approval, project, history, skills.

Run:  uv run uvicorn platform_api.main:app --port 8000      (API docs: http://localhost:8000/docs)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request

from platform_api.access import create_access_module
from platform_api.access.adapters.http_api import access_router
from platform_api.agent import create_agent_module
from platform_api.agent.adapters.inbound.http_api import internal_router, runner_router, runs_router
from platform_api.agent.adapters.outbound.fake_sandbox import FakeSandbox
from platform_api.agent.application.runs import RunSettings
from platform_api.agent.ports.required import Sandbox

HERE = Path(__file__).resolve().parents[2]
REAPER_INTERVAL_S = 60
log = logging.getLogger("platform_api")


def build_app() -> FastAPI:
    env = os.environ.get
    mode = env("SUPERAI_MODE", "dev")

    # Postgres when SUPERAI_DATABASE_URL is set (required in prod); otherwise YAML/JSONL files and memory.
    database_url = env("SUPERAI_DATABASE_URL")
    if mode == "prod" and not database_url:
        raise RuntimeError("SUPERAI_DATABASE_URL is required in prod")
    engine = None
    if database_url:
        from platform_api.db import make_engine, migrate

        migrate(database_url)  # alembic upgrade head
        engine = make_engine(database_url)
    # Shared secret with server-tools. None = dev: /internal accepts calls without it.
    service_token = os.environ["SUPERAI_SERVICE_TOKEN"] if mode == "prod" else env("SUPERAI_SERVICE_TOKEN")

    access = create_access_module(
        Path(env("SUPERAI_USERS_FILE", str(HERE / "config/users.yaml"))),  # seeds an empty database
        Path(env("SUPERAI_ROLE_LOG", str(HERE / "var/role-changes.jsonl"))),
        engine,
    )

    # Agent containers: Docker in prod (or when asked), a fake that starts nothing in dev.
    sandbox: Sandbox
    if env("SUPERAI_SANDBOX", "docker" if mode == "prod" else "fake") == "docker":
        from platform_api.agent.adapters.outbound.docker_sandbox import DockerSandbox

        sandbox = DockerSandbox(os.environ["SUPERAI_AGENT_IMAGE"],  # e.g. registry/superai/agent-runner:0.1.0
                                env("SUPERAI_SANDBOX_NETWORK", "superai-agent-sandbox"))
    else:
        sandbox = FakeSandbox()
    agent = create_agent_module(access.check, sandbox, RunSettings(
        mcp_url=env("SUPERAI_RUN_MCP_URL", "http://server-tools:8100/mcp/"),  # as the container sees them
        platform_url=env("SUPERAI_RUN_PLATFORM_URL", "http://platform-api:8000"),
        ttl=timedelta(seconds=int(env("SUPERAI_RUN_TTL_S", "1800"))),
    ), engine)

    def current_user(request: Request) -> str | None:
        if mode == "dev":
            return request.headers.get("x-user-id")  # dev only: "Viewing as" switcher in the web app
        return None  # prod: company SSO session (not wired yet) -> every request is 401

    async def reap_forever() -> None:
        """Stops containers of runs past their deadline, so a stuck agent never runs forever."""
        while True:
            try:
                expired = await asyncio.to_thread(agent.reaper.expire_overdue)
                if expired:
                    log.info("expired %d agent run(s)", expired)
            except Exception:
                log.exception("reaper failed; trying again in %ss", REAPER_INTERVAL_S)
            await asyncio.sleep(REAPER_INTERVAL_S)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        reaper = asyncio.create_task(reap_forever())
        try:
            yield
        finally:
            reaper.cancel()
            if engine is not None:
                engine.dispose()

    app = FastAPI(title="superAI platform-api", lifespan=lifespan)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(access_router(access.admin, current_user))
    app.include_router(runs_router(agent.runs, current_user))
    app.include_router(internal_router(agent.tokens, service_token))
    app.include_router(runner_router(agent.tokens))
    return app


app = build_app()
