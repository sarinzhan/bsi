"""Calls to platform-api: approvals (shown as cards in the chat) and run tokens.

Contract (platform-api implements it in its `approval` and `agent` modules):
  POST /internal/approvals        -> {"allowed": bool, "by": str}   (long request, up to 5 min)
  GET  /internal/runs/{token}     -> {"runId","chatId","system","env","requestedBy"} or 404
Both require header  X-Service-Token: <shared secret from Vault>.
"""

from __future__ import annotations

import httpx

from server_tools.tools.domain.model import RunContext
from server_tools.tools.ports.required import ApprovalDecision, ApprovalRequest, Approvals, RunAuthority


class PlatformApprovals(Approvals):
    def __init__(self, base_url: str, service_token: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, headers={"X-Service-Token": service_token},
                                         timeout=httpx.Timeout(310, connect=5))

    async def request(self, req: ApprovalRequest) -> ApprovalDecision:
        r = await self._client.post("/internal/approvals", json={
            "runId": req.ctx.run_id, "chatId": req.ctx.chat_id, "tool": req.tool, "kind": req.kind.value,
            "server": req.server, "command": req.command, "reason": req.reason,
        })
        r.raise_for_status()
        body = r.json()
        return ApprovalDecision(bool(body["allowed"]), str(body.get("by", "")))


class PlatformRunAuthority(RunAuthority):
    def __init__(self, base_url: str, service_token: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, headers={"X-Service-Token": service_token}, timeout=5)

    async def resolve(self, token: str) -> RunContext | None:
        r = await self._client.get(f"/internal/runs/{token}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        b = r.json()
        return RunContext(b["runId"], b["chatId"], b["system"], b["env"], b["requestedBy"])
