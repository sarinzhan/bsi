"""agent module: agent runs, one container per run, and the run tokens those containers use."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from platform_api.access.ports.provided import AccessCheck
from platform_api.agent.adapters.outbound.memory import InMemoryRunRepository
from platform_api.agent.application.runs import RunService, RunSettings
from platform_api.agent.ports.provided import RunReaper, Runs, RunTokens
from platform_api.agent.ports.required import RunRepository, Sandbox

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True)
class AgentModule:
    runs: Runs  # web app, chat module (later)
    tokens: RunTokens  # server-tools, agent containers
    reaper: RunReaper  # background task in main.py


def create_agent_module(access: AccessCheck, sandbox: Sandbox, settings: RunSettings,
                        engine: "Engine | None" = None) -> AgentModule:
    """engine given: runs live in Postgres. No engine: in memory (tests, quick local runs)."""
    runs: RunRepository
    if engine is None:
        runs = InMemoryRunRepository()
    else:
        from platform_api.agent.adapters.outbound.postgres import PostgresRunRepository

        runs = PostgresRunRepository(engine)
    service = RunService(runs, sandbox, access, settings)
    return AgentModule(runs=service, tokens=service, reaper=service)
