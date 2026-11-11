"""What the tools module needs. Adapters implement these; tests use fakes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from platform_api.tools.models import Command, ExecResult, RunContext, Target, ToolKind


class Targets(Protocol):
    """Finds the server to run on. platform-api owns the servers (its servers module); asked on every call,
    so a change in the server settings applies to the next call, even one already waiting for approval."""

    async def find(self, name: str) -> Target | None: ...

    async def address(self, name: str) -> "SshAddress": ...


@dataclass(frozen=True)
class SshAddress:
    host: str
    port: int
    user: str
    host_key: str | None = None  # pinned key from the servers module; SSH trusts only this one


@dataclass(frozen=True)
class ApprovalRequest:
    ctx: RunContext
    tool: str
    kind: ToolKind
    server: str
    command: str  # masked, exactly as shown on the card
    reason: str | None


@dataclass(frozen=True)
class ApprovalDecision:
    allowed: bool
    by: str  # "Sarinzha K. · for this chat", "timeout", ...
    call_id: str | None = None  # the approval card in the chat, if platform-api made one


class Approvals(Protocol):
    """Asks the developer in the chat (platform-api). Blocks until answered or timed out."""

    async def request(self, req: ApprovalRequest) -> ApprovalDecision: ...

    async def report(self, call_id: str, status: str, output: str) -> None:
        """After the run: show the outcome on the card ("done" | "failed"). Never raises."""
        ...


class Executor(Protocol):
    async def run(self, address: SshAddress, command: Command) -> ExecResult: ...


@dataclass(frozen=True)
class AuditRecord:
    run_id: str
    chat_id: str
    requested_by: str
    tool: str
    server: str
    command: str
    approved_by: str
    status: str
    exit_code: int | None


class AuditLog(Protocol):
    def write(self, record: AuditRecord) -> None: ...


class RunAuthority(Protocol):
    """Turns the agent run token (Authorization header) into a RunContext."""

    async def resolve(self, token: str) -> RunContext | None: ...
