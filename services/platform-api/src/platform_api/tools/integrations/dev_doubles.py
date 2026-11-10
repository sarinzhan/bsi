"""Dev and test stand-ins. Never used in prod."""

from __future__ import annotations

from pathlib import Path

import yaml

from platform_api.tools.models import RunContext, Target
from platform_api.tools.interfaces import (
    ApprovalDecision, ApprovalRequest, Approvals, RunAuthority, SshAddress, Targets,
)


class AnswerAllApprovals(Approvals):
    def __init__(self, allow: bool) -> None:
        self._allow = allow
        self.requests: list[ApprovalRequest] = []

    async def request(self, req: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(req)
        return ApprovalDecision(self._allow, "dev double · " + ("allow" if self._allow else "deny"))

    async def report(self, call_id: str, status: str, output: str) -> None:
        pass


class StaticRunAuthority(RunAuthority):
    """Token "dev-<system>-<env>" -> a fake run in that system."""

    async def resolve(self, token: str) -> RunContext | None:
        parts = token.split("-")
        if len(parts) != 3 or parts[0] != "dev":
            return None
        return RunContext("run-dev", "chat-dev", parts[1], parts[2], "developer")


class StaticTargets(Targets):
    """Servers from a servers.yaml file, for tests of the tools module alone. No rules are checked here:
    the servers module owns them."""

    def __init__(self, path: Path) -> None:
        raw = (yaml.safe_load(path.read_text()) or {}).get("servers") or {}
        self.servers: dict[str, dict] = {name: dict(s) for name, s in raw.items()}  # tests may change it

    async def find(self, name: str) -> Target | None:
        s = self.servers.get(name)
        if s is None:
            return None
        return Target(name, s["env"], tuple(s.get("systems") or []), tuple(sorted(s.get("allowed_tools") or [])))

    async def address(self, name: str) -> SshAddress:
        s = self.servers[name]
        return SshAddress(s["host"], int(s.get("ssh_port", 22)), s.get("ssh_user", "deploy"))


class FirstMatchRunAuthority(RunAuthority):
    """Dev: fixed dev tokens "dev-<system>-<env>" for your own MCP client, real run tokens for agent containers."""

    def __init__(self, *authorities: RunAuthority) -> None:
        self._authorities = authorities

    async def resolve(self, token: str) -> RunContext | None:
        for authority in self._authorities:
            ctx = await authority.resolve(token)
            if ctx is not None:
                return ctx
        return None
