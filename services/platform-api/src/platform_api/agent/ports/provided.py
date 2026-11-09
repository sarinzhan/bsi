"""What the agent module offers. Plain DTOs only: no domain objects leak out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    chat_id: str
    system: str
    env: str
    requested_by: str
    status: str  # starting | running | finished | failed | cancelled | expired
    created_at: str  # ISO date-time, UTC
    expires_at: str
    error: str | None
    # never the token: it goes only into the container


class RunNotFound(LookupError):
    pass


class RunNotAllowed(PermissionError):
    pass


class RunRejected(ValueError):
    """Bad input (system, env, chat id) or a run that already ended. The message is shown as is."""


class Runs(Protocol):
    """Used by the chat module (later) and the web app: start and stop agent runs."""

    def start(self, user_id: str, chat_id: str, system: str, env: str) -> RunInfo: ...

    def cancel(self, user_id: str, run_id: str) -> RunInfo: ...

    def get(self, run_id: str) -> RunInfo: ...


class RunTokens(Protocol):
    """Used by server-tools (through /internal) and by the agent container itself."""

    def resolve(self, token: str) -> RunInfo | None: ...  # None: unknown, ended or expired

    def finish(self, token: str, outcome: Literal["finished", "failed"], error: str | None = None) -> RunInfo: ...


class RunReaper(Protocol):
    """Called every minute: stops containers of runs past their deadline."""

    def expire_overdue(self) -> int: ...
