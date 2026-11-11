"""Servers module: the machines, the tools the agent may use on each, and who may change that."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import make_access, sample_servers
from platform_api.servers import create_servers_module
from platform_api.servers.integrations.fake_probe import FAKE_HOST_KEY, FakeHostProbe
from platform_api.servers.router import servers_router
from platform_api.servers.integrations.static_tools import StaticKnownTools
from platform_api.servers.models import Env, InvalidServer, Server, fingerprint
from platform_api.servers.schemas import (
    AccessChangeNotAllowed, AccessChangeRejected, HostUnreachable, NewServer, ServerRejected,
)
from platform_api.servers.interfaces import ToolCatalogUnavailable

READ = ["docker_inspect", "docker_logs", "docker_ps", "docker_stats", "file_read", "folder_list"]
WRITE = ["compose_restart", "compose_run", "docker_run", "file_write"]
TOOLS = StaticKnownTools(frozenset(READ + WRITE + ["ssh_exec"]))


def make(d=None, known=TOOLS, probe=None, servers=None):
    return create_servers_module(known, make_access().check, probe=probe,
                                 servers=sample_servers() if servers is None else servers)


@pytest.fixture
def d():
    return None


def test_change_is_saved_and_logged_as_added_removed(d):
    servers = make(d)
    info = servers.settings.change_allowed_tools("stage-docker-01", READ, "aibek", "stage is read-only now")
    assert list(info.allowed_tools) == READ
    assert list(servers.catalog.get("stage-docker-01").allowed_tools) == READ
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


def test_ssh_exec_on_prod_can_not_even_be_built():
    with pytest.raises(InvalidServer, match="never allowed on prod"):
        Server("prod-docker-01", "10.0.0.1", Env.PROD, frozenset({"ssh_exec"}), frozenset({"superapp"}))


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
    app.include_router(servers_router(servers.catalog, servers.settings, servers.admin,
                                      lambda r: r.headers.get("x-user-id")))
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





# ---- adding servers ----

def new(name="dev-docker-09", **kw):
    base = dict(name=name, host="10.20.1.19", env="dev", systems=("superapp",), ssh_user="deploy", ssh_port=22,
                host_key=FAKE_HOST_KEY)
    base.update(kw)
    return NewServer(**base)


def test_nothing_exists_until_someone_adds_it():
    servers = make(servers=[])
    assert servers.catalog.list() == [] and servers.catalog.systems() == []


def test_add_a_server_with_its_pinned_host_key_and_no_tools():
    servers = make(servers=[])
    key = asyncio.run(servers.admin.fetch_host_key("10.20.1.19", 22, "aibek"))
    assert key.key == FAKE_HOST_KEY and key.fingerprint == fingerprint(FAKE_HOST_KEY)
    info = servers.admin.add(new(host_key=key.key), "aibek")
    assert info.allowed_tools == () and info.host_key == FAKE_HOST_KEY  # tools: chosen in the settings
    assert info.host_key_fingerprint.startswith("SHA256:")
    assert [s.name for s in servers.catalog.list()] == ["dev-docker-09"]
    [event] = servers.settings.access_history("dev-docker-09")
    assert event.by == "aibek" and "added the server" in event.reason
    assert [(s.id, s.envs) for s in servers.catalog.systems()] == [("superapp", ("dev",))]


def test_only_devops_and_admins_add_servers():
    servers = make(servers=[])
    with pytest.raises(AccessChangeNotAllowed):
        servers.admin.add(new(), "sarinzha")
    with pytest.raises(AccessChangeNotAllowed):
        asyncio.run(servers.admin.fetch_host_key("10.20.1.19", 22, "sarinzha"))
    with pytest.raises(AccessChangeNotAllowed):
        servers.admin.platform_public_key("sarinzha")
    assert servers.admin.platform_public_key("dana").startswith("ssh-ed25519 ")


@pytest.mark.parametrize("change, error", [
    (dict(name="Bad Name"), "bad server name"),
    (dict(host="10.0.0.1; rm -rf /"), "bad host"),
    (dict(env="qa"), "env must be"),
    (dict(systems=()), "at least one system"),
    (dict(systems=("Super App",)), "bad system names"),
    (dict(ssh_user="root;id"), "bad SSH user"),
    (dict(host_key="ssh-ed25519 not-base64!"), "bad host key"),
    (dict(name="dev-docker-01"), "already exists"),
])
def test_add_rejects_bad_input(change, error):
    servers = make()
    with pytest.raises(ServerRejected, match=error):
        servers.admin.add(new(**change), "dana")


def test_unreachable_host_is_a_clear_error():
    servers = make(servers=[], probe=FakeHostProbe(unreachable=frozenset({"10.9.9.9"})))
    with pytest.raises(HostUnreachable, match="cannot reach 10.9.9.9:22"):
        asyncio.run(servers.admin.fetch_host_key("10.9.9.9", 22, "dana"))
    with pytest.raises(ServerRejected, match="bad host"):
        asyncio.run(servers.admin.fetch_host_key("evil host", 22, "dana"))


def test_check_saves_docker_version_and_memory_or_the_error():
    probe = FakeHostProbe()
    servers = make(servers=[], probe=probe)
    servers.admin.add(new(), "dana")
    info = asyncio.run(servers.admin.check("dev-docker-09", "dana"))
    assert info.docker_version and info.memory_total_bytes == 8 * 1024**3 and info.check_error is None
    probe.unreachable.add("10.20.1.19")
    info = asyncio.run(servers.admin.check("dev-docker-09", "dana"))
    assert "connection refused" in info.check_error and info.checked_at
    assert servers.catalog.get("dev-docker-09").check_error == info.check_error  # saved


def test_fingerprint_is_what_ssh_keygen_shows():
    asyncssh = pytest.importorskip("asyncssh")
    key = asyncssh.generate_private_key("ssh-ed25519")
    line = key.export_public_key().decode().strip()
    assert fingerprint(line) == key.convert_to_public().get_fingerprint("sha256")


def test_http_add_server_flow(client):
    admin, dev = {"X-User-Id": "dana"}, {"X-User-Id": "sarinzha"}
    assert client.get("/api/servers/ssh-public-key", headers=dev).status_code == 403
    assert client.get("/api/servers/ssh-public-key", headers=admin).json()["public_key"].startswith("ssh-")
    key = client.post("/api/servers/host-key", json={"host": "10.20.1.19", "port": 22}, headers=admin).json()
    body = {"name": "dev-docker-09", "host": "10.20.1.19", "env": "dev", "systems": ["superapp", "billing"],
            "ssh_user": "deploy", "ssh_port": 22, "host_key": key["key"]}
    assert client.post("/api/servers", json=body, headers=dev).status_code == 403
    r = client.post("/api/servers", json=body, headers=admin)
    assert r.status_code == 201 and r.json()["host_key_fingerprint"] == key["fingerprint"]
    assert client.post("/api/servers", json=body, headers=admin).status_code == 422  # name taken
    checked = client.post("/api/servers/dev-docker-09/check", headers=admin).json()
    assert checked["docker_version"] and checked["check_error"] is None
    systems = {s["id"]: s["envs"] for s in client.get("/api/systems", headers=dev).json()}
    assert systems["billing"] == ["dev"] and "superapp" in systems
