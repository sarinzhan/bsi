"""Stand-ins for platform-api, so server-tools runs alone during development. Never used in prod."""

from __future__ import annotations

from server_tools.tools.domain.model import RunContext
from server_tools.tools.ports.required import ApprovalDecision, ApprovalRequest, Approvals, RunAuthority


class AnswerAllApprovals(Approvals):
    def __init__(self, allow: bool) -> None:
        self._allow = allow
        self.requests: list[ApprovalRequest] = []

    async def request(self, req: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(req)
        return ApprovalDecision(self._allow, "dev double · " + ("allow" if self._allow else "deny"))


class StaticRunAuthority(RunAuthority):
    """Token "dev-<system>-<env>" -> a fake run in that system."""

    async def resolve(self, token: str) -> RunContext | None:
        parts = token.split("-")
        if len(parts) != 3 or parts[0] != "dev":
            return None
        return RunContext("run-dev", "chat-dev", parts[1], parts[2], "developer")
