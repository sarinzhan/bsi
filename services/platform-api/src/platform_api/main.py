"""Composition root of platform-api. Modules: access, servers, agent, chat, approval, tools. Next: project, history.

Run:  BSI_DATABASE_URL=postgresql://... uv run uvicorn --factory platform_api.main:build_app --port 8000
      (API docs: http://localhost:8000/docs)

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
from platform_api.access.router import SessionCookie, access_router
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
from platform_api.servers.integrations.fake_probe import FakeHostProbe
from platform_api.servers.interfaces import HostProbe
from platform_api.servers.router import servers_router
from platform_api.tools import create_tools_module
from platform_api.tools.router import create_mcp_server
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
    if not logging.getLogger().handlers:  # our INFO lines (runs started/ended) in docker compose logs
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Everything lives in Postgres. No example data: servers are added in the web app, users by an admin.
    # The first admin: BSI_ADMIN_USERNAME / BSI_ADMIN_PASSWORD, created on first start (password changed at
    # the first sign-in).
    database_url = env("BSI_DATABASE_URL")
    if not database_url:
        raise RuntimeError("BSI_DATABASE_URL is required (postgresql://user:password@host:5432/platform)")
    from platform_api.db import make_engine, migrate

    migrate(database_url)  # alembic upgrade head
    engine = make_engine(database_url)
    real_ssh = mode == "prod" or env("BSI_EXECUTOR") == "ssh"  # dev: no SSH at all unless asked for

    admin_name = env("BSI_ADMIN_USERNAME") or "admin"
    admin_password = env("BSI_ADMIN_PASSWORD") or "admin"
    if not env("BSI_ADMIN_PASSWORD"):
        log.warning("BSI_ADMIN_PASSWORD is not set: the default admin %r starts with password 'admin' "
                    "(it must be changed at the first sign-in)", admin_name)
    session_hours = int(env("BSI_SESSION_HOURS", "12"))
    access = create_access_module(engine, default_admin=(admin_name, admin_password),
                                  session_ttl=timedelta(hours=session_hours))
    cookie = SessionCookie(path=env("BSI_BASE_PATH", "/"), secure=env("BSI_COOKIE_SECURE", "false") == "true",
                           max_age_s=session_hours * 3600)
    tool_catalog = ToolCatalog()  # which tools exist: answered by the tools module, created below
    probe: HostProbe
    if real_ssh:
        from platform_api.servers.integrations.ssh_probe import SshHostProbe

        probe = SshHostProbe(Path(os.environ["BSI_SSH_KEY"]))
    else:
        probe = FakeHostProbe()
    servers = create_servers_module(tool_catalog, access.check, engine, probe)

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
    # Server without direct internet: agent containers reach the Anthropic API through this proxy.
    # Calls to platform-api itself must not go through it (NO_PROXY).
    if env("BSI_AGENT_HTTPS_PROXY"):
        run_env["HTTPS_PROXY"] = os.environ["BSI_AGENT_HTTPS_PROXY"]
        run_env["NO_PROXY"] = "platform-api,localhost,127.0.0.1"
    log.info("BSI platform-api: mode=%s default admin=%s sandbox=%s agent image=%s ssh=%s approvals=%s proxy=%s",
             mode, admin_name, sandbox_kind, env("BSI_AGENT_IMAGE", "-"),
             "real" if real_ssh else "FAKE",
             env("BSI_APPROVALS", "cards"), env("BSI_AGENT_HTTPS_PROXY") or "none")
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
    if real_ssh:
        from platform_api.tools.integrations.ssh import SshExecutor

        # host keys: pinned per server in the database; BSI_KNOWN_HOSTS only as a fallback for old servers
        known_hosts = env("BSI_KNOWN_HOSTS")
        executor = SshExecutor(Path(os.environ["BSI_SSH_KEY"]), Path(known_hosts) if known_hosts else None)
    else:
        executor = FakeExecutor()
    approvals: Approvals = ApprovalCards(approval.tools)  # cards in the chat
    if mode != "prod" and env("BSI_APPROVALS") == "auto":  # dev only: answered automatically
        approvals = AnswerAllApprovals(allow=env("BSI_DEV_APPROVE", "allow") == "allow")
    authority: RunAuthority = RunTokenAuthority(agent.tokens)
    if mode != "prod" and env("BSI_DEV_TOKENS", "on") == "on":
        # dev: also fixed tokens "dev-<system>-<env>", to try the tools from your own MCP client
        authority = FirstMatchRunAuthority(StaticRunAuthority(), authority)
    audit: AuditLog = PostgresAuditLog(engine)
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
        """The session cookie's user. No one while they still have to change their password."""
        token = request.cookies.get(cookie.name)
        session = access.auth.session(token) if token else None
        return session.user_id if session and not session.must_change_password else None

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
            engine.dispose()

    app = FastAPI(title="BSI platform-api", lifespan=lifespan)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(access_router(access.admin, current_user, access.auth, cookie))
    app.include_router(servers_router(servers.catalog, servers.settings, servers.admin, current_user))
    app.include_router(runs_router(agent.runs, current_user))
    app.include_router(chats_router(chat.chats, current_user))
    app.include_router(approvals_router(approval.answers, current_user))
    # agent containers (run token): context, events, finish, and the server tools
    app.include_router(runner_chat_router(chat.runner, agent.tokens))
    app.include_router(runner_router(agent.tokens))
    app.mount("/mcp", mcp_app)
    return app
