"""Value objects of the tools domain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToolKind(str, Enum):
    READ = "read"  # approved once per server per chat
    WRITE = "write"  # approved every time, needs a reason
    FULL = "full"  # ssh_exec: only on servers with full access, approved every time


class ToolRejected(Exception):
    """The call breaks a rule. The message goes back to the agent as is, so it must say what to do."""


@dataclass(frozen=True)
class RunContext:
    """Who is calling: one agent run, started from one chat. Resolved from the run token."""

    run_id: str
    chat_id: str
    system: str
    env: str
    requested_by: str  # developer who wrote the chat message

    @property
    def root(self) -> str:
        """The only folder on a server the tools may touch."""
        return f"/opt/superai/{self.system}/{self.env}"

    @property
    def compose_project(self) -> str:
        return f"{self.system}-{self.env}"


@dataclass(frozen=True)
class Target:
    """The server a call runs on, as far as the domain cares."""

    name: str
    env: str
    systems: tuple[str, ...]
    allowed_tools: tuple[str, ...]


@dataclass(frozen=True)
class Command:
    """Exactly what will run on the server. `script` is shown to the developer verbatim."""

    script: str
    stdin: bytes | None = None
    timeout_s: int = 60
    keep: str = "head"  # which end of a long output to keep: "head" or "tail" (logs)


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ToolOutcome:
    """What the agent gets back."""

    status: str  # "done" | "failed" | "denied" | "rejected"
    text: str
    exit_code: int | None = None
