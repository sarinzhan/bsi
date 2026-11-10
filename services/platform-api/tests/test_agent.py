"""Agent runs: one container per run, and the run token that is the container's only credential."""

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from platform_api.access import create_access_module
from platform_api.agent.router import runner_router, runs_router
from platform_api.agent.integrations.docker_sandbox import DockerSandbox
from platform_api.agent.integrations.fake_sandbox import FakeSandbox
from platform_api.agent.repositories.memory import InMemoryRunRepository
from platform_api.agent.service import RunService, RunSettings
from platform_api.agent.schemas import RunNotAllowed, RunNotFound, RunRejected
from platform_api.agent.interfaces import SandboxError, SandboxSpec

USERS = Path(__file__).resolve().parents[1] / "config/users.yaml"
SETTINGS = RunSettings(mcp_url="http://platform-api:8000/mcp/", platform_url="http://platform-api:8000",
                       ttl=timedelta(minutes=30))
T0 = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


@pytest.fixture
def env(tmp_path):
    shutil.copy(USERS, tmp_path / "users.yaml")
    access = create_access_module(tmp_path / "users.yaml", tmp_path / "roles.jsonl")
    repo, sandbox, clock = InMemoryRunRepository(), FakeSandbox(), Clock()
    tokens = iter(f"token-{i}" for i in range(100))
    service = RunService(repo, sandbox, access.check, SETTINGS, clock=clock, new_token=lambda: next(tokens))
    return service, repo, sandbox, clock


def token_of(sandbox, i=-1):
    return sandbox.started[i].env["BSI_RUN_TOKEN"]


def test_start_creates_a_container_that_gets_the_token_and_where_to_find_the_tools(env):
    service, repo, sandbox, _ = env
    run = service.start("sarinzha", "chat_1", "superapp", "dev")
    assert run.status == "running" and run.requested_by == "sarinzha"
    assert run.expires_at == "2026-11-09T10:30:00+00:00"
    [spec] = sandbox.started
    assert spec.env["BSI_MCP_URL"] == "http://platform-api:8000/mcp/"
    assert spec.env["BSI_RUN_ID"] == run.run_id and spec.env["BSI_RUN_TOKEN"] == "token-0"
    assert spec.labels["bsi.system"] == "superapp" and spec.labels["bsi.env"] == "dev"


def test_only_a_hash_of_the_token_is_stored(env):
    service, repo, sandbox, _ = env
    run = service.start("sarinzha", "chat_1", "superapp", "dev")
    stored = repo.get(run.run_id)
    assert "token-0" not in repr(stored) and len(stored.token_hash) == 64


def test_token_resolves_to_this_runs_system_and_env_only(env):
    service, _, sandbox, _ = env
    run = service.start("sarinzha", "chat_1", "superapp", "dev")
    resolved = service.resolve(token_of(sandbox))
    assert (resolved.run_id, resolved.system, resolved.env, resolved.chat_id) == (run.run_id, "superapp", "dev",
                                                                                 "chat_1")
    assert service.resolve("made-up") is None and service.resolve("") is None


def test_users_without_chat_permission_and_bad_input_are_refused(env):
    service, _, sandbox, _ = env
    with pytest.raises(RunNotAllowed):
        service.start("nobody", "chat_1", "superapp", "dev")
    with pytest.raises(RunRejected, match="env"):
        service.start("sarinzha", "chat_1", "superapp", "qa")
    with pytest.raises(RunRejected, match="system"):
        service.start("sarinzha", "chat_1", "../etc", "dev")
    assert sandbox.started == []


def test_container_that_does_not_start_fails_the_run_and_kills_the_token(env):
    service, _, sandbox, _ = env
    sandbox.fail = True
    run = service.start("sarinzha", "chat_1", "superapp", "dev")
    assert run.status == "failed" and "image not found" in run.error
    assert service.resolve("token-0") is None


def test_token_dies_at_the_deadline_and_the_reaper_stops_the_container(env):
    service, _, sandbox, clock = env
    run = service.start("sarinzha", "chat_1", "superapp", "dev")
    clock.now = T0 + timedelta(minutes=29)
    assert service.resolve(token_of(sandbox)) is not None and service.expire_overdue() == 0
    clock.now = T0 + timedelta(minutes=30)
    assert service.resolve(token_of(sandbox)) is None  # even before the reaper runs
    assert service.expire_overdue() == 1
    assert sandbox.stopped == [run.run_id] and service.get(run.run_id).status == "expired"
    assert service.expire_overdue() == 0  # once only


def test_finish_by_the_container_ends_the_run_once(env):
    service, _, sandbox, _ = env
    run = service.start("sarinzha", "chat_1", "superapp", "dev")
    done = service.finish(token_of(sandbox), "finished")
    assert done.status == "finished" and sandbox.stopped == [run.run_id]
    assert service.resolve(token_of(sandbox)) is None
    with pytest.raises(RunNotFound):
        service.finish(token_of(sandbox), "failed", "again")


def test_only_the_requester_cancels(env):
    service, _, sandbox, _ = env
    run = service.start("sarinzha", "chat_1", "superapp", "dev")
    with pytest.raises(RunNotAllowed):
        service.cancel("timur", run.run_id)
    assert service.cancel("sarinzha", run.run_id).status == "cancelled"
    assert sandbox.stopped == [run.run_id] and service.resolve(token_of(sandbox)) is None
    assert service.cancel("sarinzha", run.run_id).status == "cancelled"  # no error, no second stop
    assert sandbox.stopped == [run.run_id]


# ---- HTTP ----

@pytest.fixture
def client(env):
    service, _, sandbox, _ = env
    app = FastAPI()
    app.include_router(runs_router(service, lambda r: r.headers.get("x-user-id")))
    app.include_router(runner_router(service))
    return TestClient(app), sandbox


def test_http_start_never_returns_the_token(client):
    c, sandbox = client
    assert c.post("/api/runs", json={"chatId": "c1", "system": "superapp", "env": "dev"}).status_code == 401
    r = c.post("/api/runs", json={"chatId": "c1", "system": "superapp", "env": "dev"},
               headers={"X-User-Id": "sarinzha"})
    assert r.status_code == 201 and r.json()["status"] == "running"
    assert token_of(sandbox) not in r.text
    bad = c.post("/api/runs", json={"chatId": "c1", "system": "superapp", "env": "qa"}, headers={"X-User-Id": "dana"})
    assert bad.status_code == 422


def test_http_runner_finishes_with_its_own_token(client):
    c, sandbox = client
    c.post("/api/runs", json={"chatId": "c1", "system": "superapp", "env": "dev"}, headers={"X-User-Id": "sarinzha"})
    auth = {"Authorization": f"Bearer {token_of(sandbox)}"}
    assert c.post("/runner/finish", json={"outcome": "finished"}).status_code == 401
    assert c.post("/runner/finish", json={"outcome": "finished"}, headers=auth).json()["status"] == "finished"
    assert c.post("/runner/finish", json={"outcome": "finished"}, headers=auth).status_code == 401  # ended


# ---- Docker sandbox (fake Docker client: no daemon needed) ----

class FakeDocker:
    class NotFound(Exception):
        pass

    def __init__(self):
        self.run_kwargs, self.stopped = None, []
        self.containers = self

    def run(self, image, **kwargs):
        self.run_kwargs = {"image": image, **kwargs}

    def get(self, name):
        if name != "bsi-run_1":
            raise FakeDocker.NotFound(name)
        docker = self

        class Container:
            def stop(self, timeout):
                docker.stopped.append(name)

        return Container()


def test_docker_container_is_locked_down():
    docker = FakeDocker()
    DockerSandbox("registry/bsi/agent-runner:0.1.0", "bsi-agent-sandbox", client=docker).start(
        SandboxSpec("run_1", {"BSI_RUN_TOKEN": "t"}, {"bsi.system": "superapp"}))
    k = docker.run_kwargs
    assert k["image"] == "registry/bsi/agent-runner:0.1.0" and k["name"] == "bsi-run_1"
    assert k["network"] == "bsi-agent-sandbox" and k["auto_remove"] and k["detach"]
    assert k["user"] == "1000:1000" and k["read_only"] and k["cap_drop"] == ["ALL"]
    assert k["security_opt"] == ["no-new-privileges"] and k["pids_limit"] == 256
    assert k["mem_limit"] == k["memswap_limit"] == "2g" and k["nano_cpus"] == 1_000_000_000
    assert "privileged" not in k and "volumes" not in k  # no Docker socket, no host folders
    assert k["environment"] == {"BSI_RUN_TOKEN": "t"}


def test_docker_stop_is_idempotent_and_latest_images_are_refused():
    docker = FakeDocker()
    sandbox = DockerSandbox("registry/bsi/agent-runner:0.1.0", "net", client=docker)
    sandbox.stop("run_1")
    sandbox.stop("run_gone")  # NotFound: already removed, fine
    assert docker.stopped == ["bsi-run_1"]
    for image in ["registry/bsi/agent-runner:latest", "registry/bsi/agent-runner"]:
        with pytest.raises(ValueError, match="pinned"):
            DockerSandbox(image, "net", client=docker)


def test_docker_errors_become_sandbox_errors():
    class Broken(FakeDocker):
        def run(self, image, **kwargs):
            raise RuntimeError("daemon not running")

    with pytest.raises(SandboxError, match="daemon not running"):
        DockerSandbox("registry/bsi/agent-runner:0.1.0", "net", client=Broken()).start(SandboxSpec("r", {}))
