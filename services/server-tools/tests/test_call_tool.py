"""Use case tests with fakes for every required port."""

import asyncio
from pathlib import Path

import pytest

from server_tools.known_tools import CatalogToolNames
from server_tools.servers import create_servers_module
from server_tools.tools import create_tools_module
from server_tools.tools.adapters.outbound.dev_doubles import AnswerAllApprovals
from server_tools.tools.adapters.outbound.fake_executor import FakeExecutor
from server_tools.tools.adapters.outbound.targets import ServerCatalogTargets
from server_tools.tools.domain.model import RunContext
from server_tools.tools.ports.required import ApprovalDecision, AuditRecord

CONFIG = Path(__file__).resolve().parents[1] / "config/servers.yaml"
SUPERAPP = RunContext("r1", "c1", "superapp", "dev", "Sarinzha K.")


class MemoryAudit:
    def __init__(self):
        self.records: list[AuditRecord] = []

    def write(self, record):
        self.records.append(record)


def tmp_config():
    import shutil, tempfile
    d = Path(tempfile.mkdtemp())
    shutil.copy(CONFIG, d / "servers.yaml")
    return d


def servers(d):
    return create_servers_module(d / "servers.yaml", d / "access.jsonl", CatalogToolNames())


def make(allow=True, approvals=None):
    executor, audit = FakeExecutor(), MemoryAudit()
    approvals = approvals or AnswerAllApprovals(allow)
    module = create_tools_module(ServerCatalogTargets(servers(tmp_config()).catalog), approvals, executor, audit)
    return module.call_tool, approvals, executor, audit


async def test_allowed_call_runs_masks_and_audits():
    call, approvals, executor, audit = make()
    out = await call(SUPERAPP, "docker_logs", "dev-docker-01", {"service": "orders-service"})
    assert out.status == "done"
    assert "hunter2" not in out.text and "password=***" in out.text
    assert approvals.requests[0].kind.value == "read"
    assert len(executor.calls) == 1
    assert audit.records[-1].status == "done" and audit.records[-1].requested_by == "Sarinzha K."


async def test_denied_call_never_reaches_the_server():
    call, _, executor, audit = make(allow=False)
    out = await call(SUPERAPP, "compose_restart", "dev-docker-01", {"service": "orders-service", "reason": "stuck"})
    assert out.status == "denied" and "Do not retry" in out.text
    assert executor.calls == [] and audit.records[-1].status == "denied"


async def test_server_of_another_system_is_rejected_before_asking():
    call, approvals, executor, _ = make()
    out = await call(SUPERAPP, "docker_ps", "dev-docker-02", {})  # dev-docker-02 belongs to tiffany
    assert out.status == "rejected" and approvals.requests == [] and executor.calls == []


async def test_tool_not_in_server_list_is_rejected_before_asking():
    call, approvals, *_ = make()
    out = await call(SUPERAPP, "ssh_exec", "dev-docker-01", {"command": "uptime", "reason": "load"})
    assert out.status == "rejected" and "not allowed on dev-docker-01" in out.text and approvals.requests == []
    assert "docker_logs" in out.text  # the agent learns what it may use instead


async def test_ssh_exec_allowed_on_full_server_shows_exact_command():
    call, approvals, *_ = make()
    tiffany = RunContext("r2", "c2", "tiffany", "dev", "Sarinzha K.")
    out = await call(tiffany, "ssh_exec", "dev-docker-02", {"command": "uptime", "reason": "load"})
    assert out.status == "done" and approvals.requests[0].command == "uptime"


async def test_unavailable_approval_service_means_denied(monkeypatch):
    class Broken:
        async def request(self, req):
            raise ConnectionError("platform-api down")

    call, _, executor, _ = make(approvals=Broken())
    out = await call(SUPERAPP, "docker_ps", "dev-docker-01", {})
    assert out.status == "denied" and executor.calls == []


async def test_no_answer_in_time_means_denied(monkeypatch):
    import server_tools.tools.application.call_tool as uc

    class Silent:
        async def request(self, req):
            await asyncio.sleep(10)
            return ApprovalDecision(True, "late")

    monkeypatch.setattr(uc, "APPROVAL_TIMEOUT_S", 0.05)
    call, _, executor, _ = make(approvals=Silent())
    out = await call(SUPERAPP, "docker_ps", "dev-docker-01", {})
    assert out.status == "denied" and "5 minutes" in out.text and executor.calls == []


def test_ssh_exec_on_prod_fails_at_startup(tmp_path):
    from server_tools.servers.domain.server import InvalidServer

    bad = tmp_path / "servers.yaml"
    bad.write_text("servers:\n  prod-docker-01: {host: 10.0.0.1, env: prod, allowed_tools: [ssh_exec], systems: [x]}\n")
    with pytest.raises(InvalidServer):
        create_servers_module(bad, tmp_path / "log.jsonl", CatalogToolNames())
