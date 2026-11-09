"""How agent containers reach the MCP endpoint, and how their run token is resolved."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from server_tools.main import build_app
from server_tools.tools.adapters.outbound.platform_api import PlatformRunAuthority

MCP_HEADERS = {"Authorization": "Bearer dev-superapp-dev", "Accept": "application/json, text/event-stream"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


@pytest.mark.parametrize("base_url, status", [
    ("http://server-tools:8100", 200),   # agent containers use the service name
    ("http://localhost:8100", 200),
    ("http://evil.example:8100", 421),   # DNS rebinding protection stays on
])
def test_mcp_accepts_only_configured_host_names(base_url, status):
    with TestClient(build_app(), base_url=base_url) as client:
        assert client.post("/mcp/", headers=MCP_HEADERS, json=LIST_TOOLS).status_code == status


def test_allowed_hosts_come_from_settings(monkeypatch):
    monkeypatch.setenv("SUPERAI_MCP_ALLOWED_HOSTS", "tools.internal:*")
    with TestClient(build_app(), base_url="http://server-tools:8100") as client:
        assert client.post("/mcp/", headers=MCP_HEADERS, json=LIST_TOOLS).status_code == 421


async def test_run_token_is_resolved_by_platform_api_and_sent_in_the_body_not_the_url():
    seen = []

    def platform_api(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if json.loads(request.content)["token"] != "secret-token":
            return httpx.Response(404)
        return httpx.Response(200, json={"runId": "run_1", "chatId": "chat_1", "system": "superapp", "env": "dev",
                                         "requestedBy": "sarinzha"})

    authority = PlatformRunAuthority("http://platform-api:8000", "svc", httpx.MockTransport(platform_api))
    ctx = await authority.resolve("secret-token")
    assert (ctx.run_id, ctx.system, ctx.env, ctx.requested_by) == ("run_1", "superapp", "dev", "sarinzha")
    assert await authority.resolve("unknown") is None
    request = seen[0]
    assert request.method == "POST" and request.url.path == "/internal/runs/resolve"
    assert "secret-token" not in str(request.url) and request.headers["x-service-token"] == "svc"
