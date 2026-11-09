"""Composition root: reads settings, wires modules and adapters, builds the ASGI app.

Run:  uv run uvicorn server_tools.main:app --port 8100
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from server_tools.servers import create_servers_module
from server_tools.servers.adapters.http_api import servers_router
from server_tools.tools import create_tools_module
from server_tools.tools.adapters.inbound.http_api import tools_router
from server_tools.tools.adapters.inbound.mcp_server import create_mcp_server
from server_tools.tools.adapters.outbound.audit_jsonl import JsonlAuditLog
from server_tools.tools.adapters.outbound.audit_postgres import PostgresAuditLog
from server_tools.tools.adapters.outbound.dev_doubles import AnswerAllApprovals, StaticRunAuthority
from server_tools.tools.adapters.outbound.fake_executor import FakeExecutor
from server_tools.tools.adapters.outbound.platform_api import PlatformApprovals, PlatformRunAuthority
from server_tools.tools.adapters.outbound.ssh_executor import SshExecutor
from server_tools.tools.adapters.outbound.targets import ServerCatalogTargets
from server_tools.known_tools import CatalogToolNames
from server_tools.tools.domain.catalog import ImagePolicy
from server_tools.tools.ports.required import AuditLog

HERE = Path(__file__).resolve().parents[2]


def build_app() -> FastAPI:
    env = os.environ.get
    mode = env("SUPERAI_MODE", "dev")  # dev: fake SSH, answers approvals itself; prod: real everything

    # Postgres when SUPERAI_DATABASE_URL is set (required in prod); otherwise YAML + JSONL files.
    database_url = env("SUPERAI_DATABASE_URL")
    if mode == "prod" and not database_url:
        raise RuntimeError("SUPERAI_DATABASE_URL is required in prod")
    engine = None
    if database_url:
        from server_tools.db import make_engine, migrate

        migrate(database_url)  # alembic upgrade head
        engine = make_engine(database_url)

    servers = create_servers_module(
        Path(env("SUPERAI_SERVERS_FILE", str(HERE / "config/servers.yaml"))),  # seeds an empty database
        Path(env("SUPERAI_ACCESS_LOG", str(HERE / "var/access-changes.jsonl"))),
        CatalogToolNames(),
        engine,
    )
    audit: AuditLog = (PostgresAuditLog(engine) if engine is not None
                       else JsonlAuditLog(Path(env("SUPERAI_AUDIT_FILE", str(HERE / "var/audit.jsonl")))))
    service_token = env("SUPERAI_SERVICE_TOKEN") if mode == "prod" else None

    if mode == "prod":
        token = os.environ["SUPERAI_SERVICE_TOKEN"]
        platform = os.environ["SUPERAI_PLATFORM_URL"]
        executor = SshExecutor(Path(os.environ["SUPERAI_SSH_KEY"]), Path(os.environ["SUPERAI_KNOWN_HOSTS"]))
        approvals, authority = PlatformApprovals(platform, token), PlatformRunAuthority(platform, token)
    else:
        executor = FakeExecutor()
        approvals = AnswerAllApprovals(allow=env("SUPERAI_DEV_APPROVE", "allow") == "allow")
        # With SUPERAI_PLATFORM_URL, run tokens come from a local platform-api (real agent containers);
        # without it, fixed dev tokens "dev-<system>-<env>" work.
        platform_url = env("SUPERAI_PLATFORM_URL")
        authority = PlatformRunAuthority(platform_url, env("SUPERAI_SERVICE_TOKEN", "")) if platform_url \
            else StaticRunAuthority()

    tools = create_tools_module(
        ServerCatalogTargets(servers.catalog), approvals, executor, audit,
        ImagePolicy(registry=env("SUPERAI_REGISTRY", "registry")),
    )
    mcp = create_mcp_server(tools.call_tool, authority)
    # DNS rebinding protection stays on: only these Host headers are accepted. Agent containers call
    # http://server-tools:8100/mcp/, so that name must be in the list.
    hosts = env("SUPERAI_MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,server-tools:*").split(",")
    security = TransportSecuritySettings(allowed_hosts=[h.strip() for h in hosts if h.strip()])
    mcp_app = mcp.streamable_http_app(stateless_http=True, json_response=True, streamable_http_path="/",
                                      transport_security=security)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            if engine is not None:
                engine.dispose()

    app = FastAPI(title="superAI server-tools", lifespan=lifespan)  # API docs: /docs
    app.include_router(tools_router(tools.list_tools))
    app.include_router(servers_router(servers.catalog, servers.settings, service_token))
    app.mount("/mcp", mcp_app)
    return app


app = build_app()
