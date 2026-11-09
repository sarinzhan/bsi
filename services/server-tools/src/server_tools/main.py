"""Composition root: reads settings, wires modules and adapters, builds the ASGI app.

Run:  uv run uvicorn server_tools.main:app --port 8100
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount

from server_tools.servers import create_servers_module
from server_tools.servers.adapters.http_api import server_routes
from server_tools.tools import create_tools_module
from server_tools.tools.adapters.inbound.http_api import http_routes
from server_tools.tools.adapters.inbound.mcp_server import create_mcp_server
from server_tools.tools.adapters.outbound.audit_jsonl import JsonlAuditLog
from server_tools.tools.adapters.outbound.dev_doubles import AnswerAllApprovals, StaticRunAuthority
from server_tools.tools.adapters.outbound.fake_executor import FakeExecutor
from server_tools.tools.adapters.outbound.platform_api import PlatformApprovals, PlatformRunAuthority
from server_tools.tools.adapters.outbound.ssh_executor import SshExecutor
from server_tools.tools.adapters.outbound.targets import ServerCatalogTargets
from server_tools.known_tools import CatalogToolNames
from server_tools.tools.domain.catalog import ImagePolicy

HERE = Path(__file__).resolve().parents[2]


def build_app() -> Starlette:
    env = os.environ.get
    mode = env("SUPERAI_MODE", "dev")  # dev: fake SSH, answers approvals itself; prod: real everything

    servers = create_servers_module(
        Path(env("SUPERAI_SERVERS_FILE", str(HERE / "config/servers.yaml"))),
        Path(env("SUPERAI_ACCESS_LOG", str(HERE / "var/access-changes.jsonl"))),
        CatalogToolNames(),
    )
    service_token = env("SUPERAI_SERVICE_TOKEN") if mode == "prod" else None

    if mode == "prod":
        token = os.environ["SUPERAI_SERVICE_TOKEN"]
        platform = os.environ["SUPERAI_PLATFORM_URL"]
        executor = SshExecutor(Path(os.environ["SUPERAI_SSH_KEY"]), Path(os.environ["SUPERAI_KNOWN_HOSTS"]))
        approvals, authority = PlatformApprovals(platform, token), PlatformRunAuthority(platform, token)
    else:
        executor = FakeExecutor()
        approvals = AnswerAllApprovals(allow=env("SUPERAI_DEV_APPROVE", "allow") == "allow")
        authority = StaticRunAuthority()

    tools = create_tools_module(
        ServerCatalogTargets(servers.catalog), approvals, executor,
        JsonlAuditLog(Path(env("SUPERAI_AUDIT_FILE", str(HERE / "var/audit.jsonl")))),
        ImagePolicy(registry=env("SUPERAI_REGISTRY", "registry")),
    )
    mcp = create_mcp_server(tools.call_tool, authority)
    mcp_app = mcp.streamable_http_app(stateless_http=True, json_response=True, streamable_http_path="/")

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette):
        async with mcp.session_manager.run():
            yield

    routes = [*http_routes(tools.list_tools), *server_routes(servers.catalog, servers.settings, service_token)]
    return Starlette(routes=[*routes, Mount("/mcp", app=mcp_app)], lifespan=lifespan)


app = build_app()
