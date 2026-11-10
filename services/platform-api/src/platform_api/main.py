"""Composition root of platform-api. Modules: access, servers, agent, chat, approval, tools. Next: project, history.

Run:  uv run uvicorn platform_api.main:app --port 8000      (API docs: http://localhost:8000/docs)

One process: the web API, the agent runs, and the server tools the agents call over MCP (/mcp/).
This process holds the SSH key (BSI_SSH_KEY). See docs/architecture.md, "Why one process".
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from mcp.server.transport_security import TransportSecuritySettings

from platform_api.access import create_access_module
from platform_api.access.router import access_router
from platform_api.agent import create_agent_module
from platform_api.agent.router import runner_router, runs_router
from platform_api.agent.integrations.fake_sandbox import FakeSandbox
from platform_api.agent.service import RunSettings
from platform_api.agent.interfaces import Sandbox
from platform_api.approval import create_approval_module
from platform_api.approval.router import approvals_router
from platform_api.chat import create_chat_module
from platform_api.chat.router import chats_router, runner_chat_router
from platform_api.servers import create_servers_module
from platform_api.servers.router import servers_router
from platform_api.tools import create_tools_module
from platform_api.tools.router import create_mcp_server
from platform_api.tools.repositories.files import JsonlAuditLog
from platform_api.tools.repositories.postgres import PostgresAuditLog
from platform_api.tools.integrations.dev_doubles import (
    AnswerAllApprovals, FirstMatchRunAuthority, StaticRunAuthority,
)
from platform_api.tools.integrations.fake_ssh import FakeExecutor
from platform_api.tools.integrations.platform_modules import ApprovalCards, RunTokenAuthority, ServerCatalogTargets
from platform_api.tools.catalog import ImagePolicy
from platform_api.tools.interfaces import Approvals, AuditLog, Executor, RunAuthority
from platform_api.wiring import ChatRunListener, ToolCatalog

HERE = Path(__file__).resolve().parents[2]
REAPER_INTERVAL_S = 60
log = logging.getLogger("platform_api")


def build_app() -> FastAPI:
    env = os.environ.get
    mode = env("BSI_MODE", "dev")

    # Postgres when BSI_DATABASE_URL is set (required in prod); otherwise YAML/JSONL files and memory.
    database_url = env("BSI_DATABASE_URL")
    if mode == "prod" and not database_url:
        raise RuntimeError("BSI_DATABASE_URL is required in prod")
    engine = None
    if database_url:
        from platform_api.db import make_engine, migrate

        migrate(database_url)  # alembic upgrade head
        engine = make_engine(database_url)

    access = create_access_module(
        Path(env("BSI_USERS_FILE", str(HERE / "config/users.yaml"))),  # seeds an empty database
        Path(env("BSI_ROLE_LOG", str(HERE / "var/role-changes.jsonl"))),
        engine,
    )
    tool_catalog = ToolCatalog()  # which tools exist: answered by the tools module, created below
    servers = create_servers_module(
        Path(env("BSI_SERVERS_FILE", str(HERE / "config/servers.yaml"))),  # seeds an empty database
        Path(env("BSI_ACCESS_LOG", str(HERE / "var/access-changes.jsonl"))),
        tool_catalog,
        access.check,
        engine,
    )

    # Agent runs: Docker containers in prod; in dev a fake that starts nothing (default), or local processes.
    sandbox: Sandbox
    sandbox_kind = env("BSI_SANDBOX", "docker" if mode == "prod" else "fake")
    if sandbox_kind == "docker":
        from platform_api.agent.integrations.docker_sandbox import DockerSandbox

        sandbox = DockerSandbox(os.environ["BSI_AGENT_IMAGE"],  # e.g. registry/bsi/agent-runner:0.1.0
                                env("BSI_SANDBOX_NETWORK", "bsi-agent-sandbox"))
    elif sandbox_kind == "process" and mode != "prod":  # dev only: no isolation at all
        from platform_api.agent.integrations.process_sandbox import ProcessSandbox

        command = env("BSI_RUNNER_COMMAND", "uv run --project ../agent-runner python -m agent_runner")
        sandbox = ProcessSandbox(command, HERE, HERE / "var/runs")
    else:
        sandbox = FakeSandbox()
    # Passed into every agent container. No model proxy yet, so the API key goes in too (see docs/architecture.md).
    run_env = {"BSI_MODEL": env("BSI_MODEL", "claude-opus-5-5"),
               "BSI_EFFORT": env("BSI_EFFORT", "high"),
               "BSI_LLM": env("BSI_LLM", "anthropic")}  # "scripted": a fake model, no key needed
    if env("ANTHROPIC_API_KEY"):
        run_env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
    listener = ChatRunListener()
    agent = create_agent_module(access.check, sandbox, RunSettings(
        mcp_url=env("BSI_RUN_MCP_URL", "http://platform-api:8000/mcp/"),  # as the container sees them
        platform_url=env("BSI_RUN_PLATFORM_URL", "http://platform-api:8000"),
        ttl=timedelta(seconds=int(env("BSI_RUN_TTL_S", "1800"))),
        extra_env=tuple(sorted(run_env.items())),
    ), engine, listener)
    chat = create_chat_module(agent.runs, access.check, engine)
    listener.chat = chat.runner
    approval = create_approval_module(chat.events, access.check, engine)

    # ---- tools: the server tools agents call over MCP ----
    executor: Executor
    if mode == "prod" or env("BSI_EXECUTOR") == "ssh":  # dev can try one real server with BSI_EXECUTOR=ssh
        from platform_api.tools.integrations.ssh import SshExecutor

        executor = SshExecutor(Path(os.environ["BSI_SSH_KEY"]), Path(os.environ["BSI_KNOWN_HOSTS"]))
    else:
        executor = FakeExecutor()
    approvals: Approvals = ApprovalCards(approval.tools)  # cards in the chat
    if mode != "prod" and env("BSI_APPROVALS") == "auto":  # dev only: answered automatically
        approvals = AnswerAllApprovals(allow=env("BSI_DEV_APPROVE", "allow") == "allow")
    authority: RunAuthority = RunTokenAuthority(agent.tokens)
    if mode != "prod" and env("BSI_DEV_TOKENS", "on") == "on":
        # dev: also fixed tokens "dev-<system>-<env>", to try the tools from your own MCP client
        authority = FirstMatchRunAuthority(StaticRunAuthority(), authority)
    audit: AuditLog = (PostgresAuditLog(engine) if engine is not None
                       else JsonlAuditLog(Path(env("BSI_AUDIT_FILE", str(HERE / "var/audit.jsonl")))))
    tools = create_tools_module(ServerCatalogTargets(servers.catalog), approvals, executor, audit,
                                ImagePolicy(registry=env("BSI_REGISTRY", "registry")))
    tool_catalog.list_tools = tools.list_tools
    mcp = create_mcp_server(tools.call_tool, authority)
    # DNS rebinding protection stays on: only these Host headers are accepted. Agent containers call
    # http://platform-api:8000/mcp/, so that name must be in the list.
    hosts = env("BSI_MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,platform-api:*").split(",")
    mcp_app = mcp.streamable_http_app(
        stateless_http=True, json_response=True, streamable_http_path="/",
        transport_security=TransportSecuritySettings(allowed_hosts=[h.strip() for h in hosts if h.strip()]))

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
            async with mcp.session_manager.run():
                yield
        finally:
            reaper.cancel()
            if engine is not None:
                engine.dispose()

    app = FastAPI(title="BSI platform-api", lifespan=lifespan)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(access_router(access.admin, current_user))
    app.include_router(servers_router(servers.catalog, servers.settings, current_user))
    app.include_router(runs_router(agent.runs, current_user))
    app.include_router(chats_router(chat.chats, current_user))
    app.include_router(approvals_router(approval.answers, current_user))
    # agent containers (run token): context, events, finish, and the server tools
    app.include_router(runner_chat_router(chat.runner, agent.tokens))
    app.include_router(runner_router(agent.tokens))
    app.mount("/mcp", mcp_app)
    return app


app = build_app()
