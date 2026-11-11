"""What the tools service needs, answered in-process by the other platform-api modules (through their schemas).

  Targets       -> servers.ServerCatalog      which server, which tools are allowed on it
  Approvals     -> approval.ToolApprovals     ask a person (card in the chat), show the outcome
  RunAuthority  -> agent.RunTokens            run token -> chat, system, env, user
"""

from __future__ import annotations

import asyncio

from platform_api.agent.schemas import RunTokens
from platform_api.approval.schemas import ApprovalRequest as CardRequest
from platform_api.approval.schemas import ToolApprovals
from platform_api.servers.schemas import ServerCatalog
from platform_api.tools.models import RunContext, Target
from platform_api.tools.interfaces import (
    ApprovalDecision, ApprovalRequest, Approvals, RunAuthority, SshAddress, Targets,
)


class ServerCatalogTargets(Targets):
    """Asked on every call, so an access change applies to the next call, even one waiting for approval."""

    def __init__(self, servers: ServerCatalog) -> None:
        self._servers = servers

    async def find(self, name: str) -> Target | None:
        s = await asyncio.to_thread(self._servers.get, name)
        if s is None:
            return None
        return Target(name=s.name, env=s.env, systems=s.systems, allowed_tools=s.allowed_tools)

    async def address(self, name: str) -> SshAddress:
        s = await asyncio.to_thread(self._servers.get, name)
        if s is None:
            raise LookupError(name)
        return SshAddress(s.host, s.ssh_port, s.ssh_user, s.host_key)


class ApprovalCards(Approvals):
    def __init__(self, approvals: ToolApprovals) -> None:
        self._approvals = approvals

    async def request(self, req: ApprovalRequest) -> ApprovalDecision:
        outcome = await self._approvals.request(CardRequest(req.ctx.run_id, req.ctx.chat_id, req.tool, req.kind.value,
                                                            req.server, req.command, req.reason))
        return ApprovalDecision(outcome.allowed, outcome.by, outcome.call_id)

    async def report(self, call_id: str, status: str, output: str) -> None:
        await asyncio.to_thread(self._approvals.report, call_id, status, output)


class RunTokenAuthority(RunAuthority):
    def __init__(self, tokens: RunTokens) -> None:
        self._tokens = tokens

    async def resolve(self, token: str) -> RunContext | None:
        run = await asyncio.to_thread(self._tokens.resolve, token)
        if run is None:
            return None
        return RunContext(run.run_id, run.chat_id, run.system, run.env, run.requested_by)
