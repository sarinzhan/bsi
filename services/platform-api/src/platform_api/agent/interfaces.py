"""What the agent module needs from the outside world."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from platform_api.agent.models import Run
from platform_api.agent.schemas import RunInfo


class RunRepository(Protocol):
    def add(self, run: Run) -> None: ...

    def save(self, run: Run) -> None: ...

    def get(self, run_id: str) -> Run | None: ...

    def by_token_hash(self, token_hash: str) -> Run | None: ...

    def active_overdue(self, now: datetime) -> list[Run]: ...


@dataclass(frozen=True)
class SandboxSpec:
    """Everything a sandbox needs to start one run's container."""

    run_id: str
    env: dict[str, str]  # includes the run token: sandboxes must not log it
    labels: dict[str, str] = field(default_factory=dict)


class SandboxError(RuntimeError):
    pass


class RunListener(Protocol):
    """Told when a run ends after it started (finished, failed, cancelled, expired). Must not raise."""

    def ended(self, run: "RunInfo") -> None: ...


class Sandbox(Protocol):
    """Starts and stops the container of one run (Docker today, Kubernetes later)."""

    def start(self, spec: SandboxSpec) -> None: ...  # raises SandboxError

    def stop(self, run_id: str) -> None: ...  # idempotent: an already stopped container is fine
