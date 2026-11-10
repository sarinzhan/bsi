"""agent module: agent runs, one container per run, and the run tokens those containers use."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from platform_api.access.schemas import AccessCheck
from platform_api.agent.repositories.memory import InMemoryRunRepository
from platform_api.agent.service import RunService, RunSettings
from platform_api.agent.schemas import RunReaper, Runs, RunTokens
from platform_api.agent.interfaces import RunListener, RunRepository, Sandbox

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True)
class AgentModule:
    runs: Runs  # web app, chat module (later)
    tokens: RunTokens  # the tools module (MCP), agent containers
    reaper: RunReaper  # background task in main.py


def create_agent_module(access: AccessCheck, sandbox: Sandbox, settings: RunSettings,
                        engine: "Engine | None" = None, listener: RunListener | None = None) -> AgentModule:
    """engine given: runs live in Postgres. No engine: in memory (tests, quick local runs)."""
    runs: RunRepository
    if engine is None:
        runs = InMemoryRunRepository()
    else:
        from platform_api.agent.repositories.postgres import PostgresRunRepository

        runs = PostgresRunRepository(engine)
    service = RunService(runs, sandbox, access, settings, listener=listener)
    return AgentModule(runs=service, tokens=service, reaper=service)
