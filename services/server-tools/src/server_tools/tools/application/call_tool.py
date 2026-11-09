"""Use case: call a server tool.

validate -> ask the developer -> run over SSH -> mask -> audit -> answer the agent
"""

from __future__ import annotations

import asyncio
from typing import Any

from server_tools.tools.domain import catalog, masking
from server_tools.tools.domain.catalog import ImagePolicy
from server_tools.tools.domain.model import Command, RunContext, ToolOutcome, ToolRejected
from server_tools.tools.ports.provided import CallTool
from server_tools.tools.ports.required import (
    ApprovalDecision, ApprovalRequest, Approvals, AuditLog, AuditRecord, Executor, Targets,
)

APPROVAL_TIMEOUT_S = 300

DENIED = (
    "Denied by the developer ({by}). Do not retry the same call. "
    "Explain in the chat what you wanted to check, or find another way."
)


class CallToolService(CallTool):
    def __init__(self, targets: Targets, approvals: Approvals, executor: Executor, audit: AuditLog,
                 images: ImagePolicy = ImagePolicy()) -> None:
        self._targets, self._approvals, self._executor, self._audit = targets, approvals, executor, audit
        self._images = images

    async def __call__(self, ctx: RunContext, tool: str, server: str, args: dict[str, Any]) -> ToolOutcome:
        spec = catalog.TOOLS.get(tool)
        try:
            if spec is None:
                raise ToolRejected(f"unknown tool {tool!r}")
            command = self._check(spec, ctx, server, args)
        except ToolRejected as e:
            self._record(ctx, tool, server, "-", "-", "rejected", None)
            return ToolOutcome("rejected", f"Rejected: {e}")

        shown = catalog.display(command, tool, args)
        decision = await self._ask(ApprovalRequest(ctx, tool, spec.kind, server, shown, args.get("reason")))
        if not decision.allowed:
            self._record(ctx, tool, server, shown, decision.by, "denied", None)
            return ToolOutcome("denied", DENIED.format(by=decision.by))

        # Settings may have changed while the developer was deciding (e.g. full -> tools): check again.
        try:
            command = self._check(spec, ctx, server, args)
        except ToolRejected as e:
            self._record(ctx, tool, server, shown, decision.by, "rejected", None)
            return ToolOutcome("rejected", f"Rejected after approval: {e}")

        try:
            result = await self._executor.run(self._targets.address(server), command)
        except Exception as e:  # network, auth, timeout: the agent should know, not crash
            self._record(ctx, tool, server, shown, decision.by, "failed", None)
            return ToolOutcome("failed", f"Could not run on {server}: {type(e).__name__}: {e}")

        text = result.stdout + (("\n[stderr]\n" + result.stderr) if result.stderr.strip() else "")
        if spec.post:
            text = spec.post(text, args)
        text = masking.cap(masking.mask(text), command.keep)
        status = "done" if result.exit_code == 0 else "failed"
        self._record(ctx, tool, server, shown, decision.by, status, result.exit_code)
        return ToolOutcome(status, f"exit {result.exit_code}\n{text}", result.exit_code)

    def _check(self, spec: catalog.ToolSpec, ctx: RunContext, server: str, args: dict[str, Any]) -> Command:
        """Server belongs to this run's system and env, and the arguments build a valid command."""
        target = self._targets.find(server)
        if target is None or ctx.system not in target.systems or target.env != ctx.env:
            raise ToolRejected(f"server {server!r} is not a {ctx.env} server of {ctx.system}")
        if spec.name not in target.allowed_tools:
            allowed = ", ".join(target.allowed_tools) or "nothing"
            raise ToolRejected(f"{spec.name} is not allowed on {server} (server settings). Allowed: {allowed}")
        try:
            return spec.build(args, ctx, target, self._images)
        except KeyError as e:
            raise ToolRejected(f"missing argument {e}") from e
        except (TypeError, ValueError) as e:
            raise ToolRejected(str(e)) from e

    async def _ask(self, req: ApprovalRequest) -> ApprovalDecision:
        try:
            return await asyncio.wait_for(self._approvals.request(req), APPROVAL_TIMEOUT_S)
        except asyncio.TimeoutError:
            return ApprovalDecision(False, "no answer in 5 minutes")
        except Exception as e:  # platform-api down = denied, never "allowed by default"
            return ApprovalDecision(False, f"approval service unavailable: {type(e).__name__}")

    def _record(self, ctx: RunContext, tool: str, server: str, command: str, by: str, status: str,
                code: int | None) -> None:
        self._audit.write(AuditRecord(ctx.run_id, ctx.chat_id, ctx.requested_by, tool, server, command, by,
                                      status, code))
