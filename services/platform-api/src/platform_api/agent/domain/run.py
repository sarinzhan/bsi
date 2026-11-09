"""Run: one agent run in its own container, started by one chat message.

The run token is the container's only credential. Whoever holds it can call the server tools as this run:
only in this run's system and environment, only with approval, only until the run ends or expires.
The platform stores a hash of the token, never the token itself.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

_SYSTEM = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
_CHAT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ENVS = frozenset({"dev", "stage", "prod"})


class RunStatus(str, Enum):
    STARTING = "starting"  # saved, container being created
    RUNNING = "running"
    FINISHED = "finished"  # the agent said it is done
    FAILED = "failed"  # the container did not start, or the agent reported a failure
    CANCELLED = "cancelled"  # the developer stopped it
    EXPIRED = "expired"  # ran past its deadline; the container was stopped


ACTIVE = frozenset({RunStatus.STARTING, RunStatus.RUNNING})


class InvalidRun(ValueError):
    pass


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Run:
    id: str
    chat_id: str
    system: str
    env: str
    requested_by: str  # user id of the developer who wrote the message
    token_hash: str
    status: RunStatus
    created_at: datetime
    expires_at: datetime
    error: str | None = None

    def __post_init__(self) -> None:
        if not _SYSTEM.match(self.system):
            raise InvalidRun(f"bad system name {self.system!r}")
        if self.env not in ENVS:
            raise InvalidRun(f"env must be one of {', '.join(sorted(ENVS))}")
        if not _CHAT.match(self.chat_id):
            raise InvalidRun(f"bad chat id {self.chat_id!r}")
        if self.expires_at <= self.created_at:
            raise InvalidRun("a run must expire after it starts")

    @property
    def active(self) -> bool:
        return self.status in ACTIVE

    def token_usable(self, now: datetime) -> bool:
        """The token works only while the run is active and before its deadline."""
        return self.active and now < self.expires_at

    def running(self) -> "Run":
        if self.status is not RunStatus.STARTING:
            raise InvalidRun(f"run {self.id} is {self.status.value}, not starting")
        return replace(self, status=RunStatus.RUNNING)

    def ended(self, status: RunStatus, error: str | None = None) -> "Run":
        """Any end state. A run ends once: later ends are refused."""
        if status in ACTIVE:
            raise InvalidRun(f"{status.value} is not an end state")
        if not self.active:
            raise InvalidRun(f"run {self.id} already ended ({self.status.value})")
        return replace(self, status=status, error=error)
