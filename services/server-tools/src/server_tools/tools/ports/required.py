"""What the tools module needs. Adapters implement these; tests use fakes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from server_tools.tools.domain.model import Command, ExecResult, RunContext, Target, ToolKind


class Targets(Protocol):
    """Finds the server to run on (adapter over the servers module)."""

    def find(self, name: str) -> Target | None: ...
    def address(self, name: str) -> "SshAddress": ...


@dataclass(frozen=True)
class SshAddress:
    host: str
    port: int
    user: str


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


class Approvals(Protocol):
    """Asks the developer in the chat (platform-api). Blocks until answered or timed out."""

    async def request(self, req: ApprovalRequest) -> ApprovalDecision: ...


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
