"""Servers module: the machines, the tools the agent may use on each, and who may change that."""

import shutil
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from platform_api.access import create_access_module
from platform_api.servers import create_servers_module
from platform_api.servers.router import servers_router
from platform_api.servers.integrations.static_tools import StaticKnownTools
from platform_api.servers.models import InvalidServer
from platform_api.servers.schemas import AccessChangeNotAllowed, AccessChangeRejected
from platform_api.servers.interfaces import ToolCatalogUnavailable

HERE = Path(__file__).resolve().parents[1]
READ = ["docker_inspect", "docker_logs", "docker_ps", "docker_stats", "file_read", "folder_list"]
WRITE = ["compose_restart", "compose_run", "docker_run", "file_write"]
TOOLS = StaticKnownTools(frozenset(READ + WRITE + ["ssh_exec"]))


def make(d: Path, known=TOOLS):
    access = create_access_module(d / "users.yaml", d / "roles.jsonl")
    return create_servers_module(d / "servers.yaml", d / "access.jsonl", known, access.check)


@pytest.fixture
def d(tmp_path):
    shutil.copy(HERE / "config/servers.yaml", tmp_path / "servers.yaml")
    shutil.copy(HERE / "config/users.yaml", tmp_path / "users.yaml")
    return tmp_path


def test_change_is_saved_and_logged_as_added_removed(d):
    servers = make(d)
    info = servers.settings.change_allowed_tools("stage-docker-01", READ, "aibek", "stage is read-only now")
    assert list(info.allowed_tools) == READ
    assert yaml.safe_load((d / "servers.yaml").read_text())["servers"]["stage-docker-01"]["allowed_tools"] == READ
    assert list(make(d).catalog.get("stage-docker-01").allowed_tools) == READ  # survives a restart
    [change] = servers.settings.access_history("stage-docker-01")
    assert change.added == () and change.removed == ("compose_restart",) and change.by == "aibek"


@pytest.mark.parametrize("user, allowed", [("sarinzha", False), ("nobody", False), ("aibek", True),
                                           ("timur", True), ("dana", True)])
def test_only_devops_and_admins_change_access(d, user, allowed):
    servers = make(d)
    if allowed:
        servers.settings.change_allowed_tools("dev-docker-01", READ, user, "read-only for now")
    else:
        with pytest.raises(AccessChangeNotAllowed):
            servers.settings.change_allowed_tools("dev-docker-01", READ, user, "read-only for now")
        assert servers.settings.access_history("dev-docker-01") == []


def test_ssh_exec_on_prod_is_refused(d):
    servers = make(d)
    with pytest.raises(AccessChangeRejected, match="prod"):
        servers.settings.change_allowed_tools("prod-docker-01", ["docker_ps", "ssh_exec"], "dana", "please")
    assert "ssh_exec" not in servers.catalog.get("prod-docker-01").allowed_tools


def test_ssh_exec_on_prod_in_the_file_fails_at_startup(d):
    (d / "servers.yaml").write_text(
        "servers:\n  prod-docker-01: {host: 10.0.0.1, env: prod, allowed_tools: [ssh_exec], systems: [x]}\n")
    with pytest.raises(InvalidServer):
        make(d)


def test_unknown_tools_reason_and_no_op(d):
    servers = make(d)
    with pytest.raises(AccessChangeRejected, match="unknown tools: rm_rf"):
        servers.settings.change_allowed_tools("dev-docker-01", ["rm_rf"], "dana", "y")
    with pytest.raises(AccessChangeRejected, match="why"):
        servers.settings.change_allowed_tools("dev-docker-01", READ, "dana", " ")
    same = list(servers.catalog.get("dev-docker-01").allowed_tools)
    servers.settings.change_allowed_tools("dev-docker-01", same, "dana", "same as before")
    assert servers.settings.access_history("dev-docker-01") == []


def test_empty_list_means_the_agent_can_do_nothing(d):
    info = make(d).settings.change_allowed_tools("dev-docker-01", [], "dana", "freeze during migration")
    assert info.allowed_tools == ()


def test_access_is_not_changed_when_the_tool_catalog_cannot_be_read(d):
    class Down:
        def names(self):
            raise ToolCatalogUnavailable("not ready")

    servers = make(d, known=Down())
    with pytest.raises(AccessChangeRejected, match="nothing was changed"):
        servers.settings.change_allowed_tools("dev-docker-01", READ, "dana", "read-only")
    assert servers.settings.access_history("dev-docker-01") == []


# ---- HTTP ----

@pytest.fixture
def client(d):
    servers = make(d)
    app = FastAPI()
    app.include_router(servers_router(servers.catalog, servers.settings, lambda r: r.headers.get("x-user-id")))
    return TestClient(app)


def test_http_web_app_routes_use_the_signed_in_user(client):
    url = "/api/servers/stage-docker-01/allowed-tools"
    body = {"tools": READ, "reason": "read-only stage"}
    assert client.get("/api/servers").status_code == 401
    assert client.put(url, json=body).status_code == 401
    assert client.put(url, json=body, headers={"X-User-Id": "sarinzha"}).status_code == 403  # developer only
    r = client.put(url, json=body, headers={"X-User-Id": "aibek"})
    assert r.status_code == 200 and r.json()["allowed_tools"] == READ
    assert client.put(url, json={"tools": "all", "reason": "x"}, headers={"X-User-Id": "aibek"}).status_code == 422
    history = client.get("/api/servers/stage-docker-01/access-history", headers={"X-User-Id": "sarinzha"}).json()
    assert history[0]["removed"] == ["compose_restart"] and history[0]["by"] == "aibek"


