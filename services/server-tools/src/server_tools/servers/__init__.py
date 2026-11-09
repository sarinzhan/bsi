"""servers module: which machines exist and what the agent may do on them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from server_tools.servers.adapters.access_log_jsonl import JsonlAccessChangeLog
from server_tools.servers.adapters.yaml_repository import YamlServerRepository
from server_tools.servers.application.catalog import ServerCatalogService
from server_tools.servers.application.settings import ServerSettingsService
from server_tools.servers.domain.server import AccessChanged
from server_tools.servers.ports.provided import ServerCatalog, ServerSettings
from server_tools.servers.ports.required import AccessChangeLog, KnownTools, ServerRepository

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True)
class ServersModule:
    catalog: ServerCatalog  # read side, used by the tools module
    settings: ServerSettings  # write side, used by the settings page


def create_servers_module(config_path: Path, access_log_path: Path, known_tools: KnownTools,
                          engine: "Engine | None" = None) -> ServersModule:
    """Wires the module and returns only its provided ports.

    engine given: servers and access changes live in Postgres; config_path seeds an empty database.
    No engine: servers.yaml is the store and access changes go to a JSONL file (tests, quick local runs).
    """
    repository: ServerRepository
    log: AccessChangeLog
    if engine is None:
        repository, log = YamlServerRepository(config_path), JsonlAccessChangeLog(access_log_path)
    else:
        from server_tools.servers.adapters.postgres import PostgresAccessChangeLog, PostgresServerRepository

        repository, log = PostgresServerRepository(engine), PostgresAccessChangeLog(engine)
        if repository.is_empty() and config_path.exists():
            _seed(repository, log, YamlServerRepository(config_path), config_path.name)
    return ServersModule(ServerCatalogService(repository), ServerSettingsService(repository, log, known_tools))


def _seed(target: ServerRepository, log: AccessChangeLog, source: ServerRepository, file: str) -> None:
    """First start on an empty database: import the YAML file, and log it like any other access change."""
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for server in source.all():
        target.save(server)
        log.append(AccessChanged(server.name, tuple(sorted(server.allowed_tools)), (), "system",
                                 f"imported from {file}", at))
