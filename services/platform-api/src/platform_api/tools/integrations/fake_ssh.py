"""Executor for local development and tests: records commands, returns canned output."""

from __future__ import annotations

from platform_api.tools.models import Command, ExecResult
from platform_api.tools.interfaces import Executor, SshAddress

_CANNED = {  # checked in order: logs/stats scripts also contain "docker ps"
    "docker logs": "2026-11-09T10:01:12 INFO  Starting OrdersApplication\n"
                   "2026-11-09T10:01:15 ERROR HikariPool-1 - Connection is not available, request timed out\n"
                   "2026-11-09T10:01:15 ERROR password=hunter2 rejected for user app\n"
                   "2026-11-09T10:01:16 INFO  Shutting down",
    "docker stats": '{"Name":"superapp-dev-orders-db-1","CPUPerc":"0.4%","MemUsage":"212MiB / 1GiB"}',
    "docker ps": '{"Names":"superapp-dev-orders-service-1","State":"restarting","Status":"Restarting (1) 8 seconds ago"}\n'
                 '{"Names":"superapp-dev-orders-db-1","State":"running","Status":"Up 2 hours (healthy)"}',
}


class FakeExecutor(Executor):
    def __init__(self) -> None:
        self.calls: list[tuple[SshAddress, Command]] = []

    async def run(self, address: SshAddress, command: Command) -> ExecResult:
        self.calls.append((address, command))
        for needle, out in _CANNED.items():
            if needle in command.script:
                return ExecResult(0, out, "")
        return ExecResult(0, f"(fake) ran on {address.host}", "")
