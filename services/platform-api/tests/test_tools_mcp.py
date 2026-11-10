"""How agent containers reach the MCP endpoint of platform-api (/mcp/)."""

import pytest
from fastapi.testclient import TestClient

from platform_api.main import build_app

MCP_HEADERS = {"Authorization": "Bearer dev-superapp-dev", "Accept": "application/json, text/event-stream"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


@pytest.mark.parametrize("base_url, status", [
    ("http://platform-api:8000", 200),   # agent containers use the service name
    ("http://localhost:8000", 200),
    ("http://evil.example:8000", 421),   # DNS rebinding protection stays on
])
def test_mcp_accepts_only_configured_host_names(base_url, status):
    with TestClient(build_app(), base_url=base_url) as client:
        assert client.post("/mcp/", headers=MCP_HEADERS, json=LIST_TOOLS).status_code == status


def test_allowed_hosts_come_from_settings(monkeypatch):
    monkeypatch.setenv("BSI_MCP_ALLOWED_HOSTS", "tools.internal:*")
    with TestClient(build_app(), base_url="http://platform-api:8000") as client:
        assert client.post("/mcp/", headers=MCP_HEADERS, json=LIST_TOOLS).status_code == 421


def test_mcp_lists_the_tools_and_the_web_app_gets_the_same_catalog():
    with TestClient(build_app(), base_url="http://localhost:8000") as client:
        listed = client.post("/mcp/", headers=MCP_HEADERS, json=LIST_TOOLS).json()["result"]["tools"]
        catalog = client.get("/api/servers/tools", headers={"X-User-Id": "sarinzha"}).json()
    assert len(listed) == 11 and {t["name"] for t in listed} == {t["name"] for t in catalog}
    assert {"docker_logs", "ssh_exec"} <= {t["name"] for t in catalog} and catalog[0]["approval"]


def test_unknown_token_is_refused():
    with TestClient(build_app(), base_url="http://localhost:8000") as client:
        r = client.post("/mcp/", headers={**MCP_HEADERS, "Authorization": "Bearer nope"},
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": "docker_ps", "arguments": {"server": "dev-docker-01"}}})
    result = r.json()["result"]
    assert result["is_error"] if "is_error" in result else result["isError"]
    assert "unknown or expired run token" in result["content"][0]["text"]
