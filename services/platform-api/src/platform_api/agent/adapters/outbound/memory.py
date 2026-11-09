"""Outbound adapter: runs in memory, for running without a database (tests, quick local runs).

Runs are lost on restart, which is fine: their containers are short-lived too.
"""

from __future__ import annotations

import threading
from datetime import datetime

from platform_api.agent.domain.run import Run
from platform_api.agent.ports.required import RunRepository


class InMemoryRunRepository(RunRepository):
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def add(self, run: Run) -> None:
        with self._lock:
            if run.id in self._runs:
                raise ValueError(f"run {run.id} exists")
            self._runs[run.id] = run

    def save(self, run: Run) -> None:
        with self._lock:
            self._runs[run.id] = run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def by_token_hash(self, token_hash: str) -> Run | None:
        return next((r for r in self._runs.values() if r.token_hash == token_hash), None)

    def active_overdue(self, now: datetime) -> list[Run]:
        return [r for r in self._runs.values() if r.active and r.expires_at <= now]
