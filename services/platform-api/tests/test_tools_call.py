"""Tools service tests, with fakes for everything it needs."""

import asyncio
from pathlib import Path

import pytest

from platform_api.tools import create_tools_module
from platform_api.tools.integrations.dev_doubles import AnswerAllApprovals, StaticTargets
from platform_api.tools.integrations.fake_ssh import FakeExecutor
from platform_api.tools.models import RunContext
from platform_api.tools.interfaces import ApprovalDecision, AuditRecord

SERVERS = Path(__file__).resolve().parent / "fixtures/servers.yaml"
SUPERAPP = RunContext("r1", "c1", "superapp", "dev", "Sarinzha K.")


class MemoryAudit:
    def __init__(self):
        self.records: list[AuditRecord] = []

    def write(self, record):
        self.records.append(record)


def make(allow=True, approvals=None):
    executor, audit = FakeExecutor(), MemoryAudit()
    approvals = approvals or AnswerAllApprovals(allow)
    module = create_tools_module(StaticTargets(SERVERS), approvals, executor, audit)
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
    import platform_api.tools.service as uc

    class Silent:
        async def request(self, req):
            await asyncio.sleep(10)
            return ApprovalDecision(True, "late")

    monkeypatch.setattr(uc, "APPROVAL_TIMEOUT_S", 0.05)
    call, _, executor, _ = make(approvals=Silent())
    out = await call(SUPERAPP, "docker_ps", "dev-docker-01", {})
    assert out.status == "denied" and "5 minutes" in out.text and executor.calls == []


async def test_removing_a_tool_while_waiting_for_approval_blocks_the_command():
    targets = StaticTargets(SERVERS)

    class AdminRemovesThenDeveloperAllows:
        async def request(self, req):  # a devops removes ssh_exec in platform-api while the card is open
            targets.servers["dev-docker-02"]["allowed_tools"].remove("ssh_exec")
            return ApprovalDecision(True, "Sarinzha K. · once")

    executor = FakeExecutor()
    tools = create_tools_module(targets, AdminRemovesThenDeveloperAllows(), executor, MemoryAudit())
    ctx = RunContext("r", "c", "tiffany", "dev", "Sarinzha K.")
    out = await tools.call_tool(ctx, "ssh_exec", "dev-docker-02", {"command": "uptime", "reason": "load"})
    assert out.status == "rejected" and "after approval" in out.text and executor.calls == []


async def test_no_server_info_means_no_call():
    class Down:
        async def find(self, name):
            raise ConnectionError("servers module unavailable")

        async def address(self, name):
            raise ConnectionError("servers module unavailable")

    executor, audit = FakeExecutor(), MemoryAudit()
    tools = create_tools_module(Down(), AnswerAllApprovals(True), executor, audit)
    out = await tools.call_tool(SUPERAPP, "docker_ps", "dev-docker-01", {})
    assert out.status == "rejected" and "cannot look up server" in out.text and executor.calls == []
    assert audit.records[0].status == "rejected"


async def test_outcome_is_reported_to_the_approval_card():
    class CardApprovals:
        def __init__(self):
            self.reports = []

        async def request(self, req):
            return ApprovalDecision(True, "Sarinzha K. · once", call_id="call_1")

        async def report(self, call_id, status, output):
            self.reports.append((call_id, status, output))

    approvals = CardApprovals()
    tools = create_tools_module(StaticTargets(SERVERS), approvals, FakeExecutor(), MemoryAudit())
    out = await tools.call_tool(SUPERAPP, "docker_ps", "dev-docker-01", {})
    [(call_id, status, output)] = approvals.reports
    assert out.status == "done" and call_id == "call_1" and status == "done" and output.startswith("exit 0")


async def test_a_broken_card_never_breaks_the_call():
    class Broken:
        async def request(self, req):
            return ApprovalDecision(True, "x", call_id="call_1")

        async def report(self, call_id, status, output):
            raise RuntimeError("platform-api down")

    tools = create_tools_module(StaticTargets(SERVERS), Broken(), FakeExecutor(), MemoryAudit())
    assert (await tools.call_tool(SUPERAPP, "docker_ps", "dev-docker-01", {})).status == "done"
