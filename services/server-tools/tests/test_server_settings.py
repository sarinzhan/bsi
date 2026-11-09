"""Changing the list of allowed tools in a server's settings."""

import shutil
from pathlib import Path

import pytest
import yaml
from starlette.applications import Starlette
from starlette.testclient import TestClient

from server_tools.known_tools import CatalogToolNames
from server_tools.servers import create_servers_module
from server_tools.servers.adapters.http_api import server_routes
from server_tools.servers.ports.provided import AccessChangeRejected
from server_tools.tools import create_tools_module
from server_tools.tools.adapters.outbound.fake_executor import FakeExecutor
from server_tools.tools.adapters.outbound.targets import ServerCatalogTargets
from server_tools.tools.domain.model import RunContext
from server_tools.tools.ports.required import ApprovalDecision

CONFIG = Path(__file__).resolve().parents[1] / "config/servers.yaml"
READ = ["docker_inspect", "docker_logs", "docker_ps", "docker_stats", "file_read", "folder_list"]


@pytest.fixture
def module(tmp_path):
    shutil.copy(CONFIG, tmp_path / "servers.yaml")
    return create_servers_module(tmp_path / "servers.yaml", tmp_path / "access.jsonl", CatalogToolNames()), tmp_path


def test_change_is_saved_to_yaml_and_logged_as_added_removed(module):
    servers, d = module
    info = servers.settings.change_allowed_tools("stage-docker-01", READ, "Sarinzha K.", "stage is read-only now")
    assert list(info.allowed_tools) == READ
    assert yaml.safe_load((d / "servers.yaml").read_text())["servers"]["stage-docker-01"]["allowed_tools"] == READ
    fresh = create_servers_module(d / "servers.yaml", d / "access.jsonl", CatalogToolNames())
    assert list(fresh.catalog.get("stage-docker-01").allowed_tools) == READ
    [change] = servers.settings.access_history("stage-docker-01")
    assert change.added == () and change.removed == ("compose_restart",) and change.by == "Sarinzha K."


def test_ssh_exec_on_prod_is_refused(module):
    servers, _ = module
    with pytest.raises(AccessChangeRejected, match="prod"):
        servers.settings.change_allowed_tools("prod-docker-01", ["docker_ps", "ssh_exec"], "x", "please")
    assert "ssh_exec" not in servers.catalog.get("prod-docker-01").allowed_tools


def test_unknown_tools_reason_and_no_op(module):
    servers, _ = module
    with pytest.raises(AccessChangeRejected, match="unknown tools: rm_rf"):
        servers.settings.change_allowed_tools("dev-docker-01", ["rm_rf"], "x", "y")
    with pytest.raises(AccessChangeRejected, match="why"):
        servers.settings.change_allowed_tools("dev-docker-01", READ, "x", " ")
    same = list(servers.catalog.get("dev-docker-01").allowed_tools)
    servers.settings.change_allowed_tools("dev-docker-01", same, "x", "same as before")
    assert servers.settings.access_history("dev-docker-01") == []


def test_empty_list_means_the_agent_can_do_nothing(module):
    servers, _ = module
    info = servers.settings.change_allowed_tools("dev-docker-01", [], "admin", "freeze during migration")
    assert info.allowed_tools == ()


async def test_removing_a_tool_while_waiting_for_approval_blocks_the_command(module):
    servers, _ = module
    executor = FakeExecutor()
    without_ssh = [t for t in servers.catalog.get("dev-docker-02").allowed_tools if t != "ssh_exec"]

    class AdminRemovesThenDeveloperAllows:
        async def request(self, req):
            servers.settings.change_allowed_tools("dev-docker-02", without_ssh, "admin", "too risky")
            return ApprovalDecision(True, "Sarinzha K. · once")

    class Audit:
        def write(self, r):
            pass

    tools = create_tools_module(ServerCatalogTargets(servers.catalog), AdminRemovesThenDeveloperAllows(), executor, Audit())
    ctx = RunContext("r", "c", "tiffany", "dev", "Sarinzha K.")
    out = await tools.call_tool(ctx, "ssh_exec", "dev-docker-02", {"command": "uptime", "reason": "load"})
    assert out.status == "rejected" and "after approval" in out.text and executor.calls == []


def test_http_needs_service_token_in_prod(module):
    servers, _ = module
    client = TestClient(Starlette(routes=server_routes(servers.catalog, servers.settings, "s3cret")))
    url = "/api/servers/stage-docker-01/allowed-tools"
    body = {"tools": READ, "reason": "read-only stage"}
    assert client.put(url, json=body).status_code == 401
    r = client.put(url, json=body, headers={"X-Service-Token": "s3cret", "X-User": "admin"})
    assert r.status_code == 200 and r.json()["allowed_tools"] == READ
    assert client.put(url, json={"tools": "all", "reason": "x"}, headers={"X-Service-Token": "s3cret"}).status_code == 422
    assert client.get("/api/servers/stage-docker-01/access-history").json()[0]["removed"] == ["compose_restart"]
