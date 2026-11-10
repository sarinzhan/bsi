"""servers module: which machines exist and what the agent may do on them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from platform_api.access.schemas import AccessCheck
from platform_api.servers.repositories.files import JsonlAccessChangeLog
from platform_api.servers.repositories.files import YamlServerRepository
from platform_api.servers.service import ServerCatalogService
from platform_api.servers.service import ServerSettingsService
from platform_api.servers.models import AccessChanged
from platform_api.servers.schemas import ServerCatalog, ServerSettings
from platform_api.servers.interfaces import AccessChangeLog, KnownTools, ServerRepository

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True)
class ServersModule:
    catalog: ServerCatalog  # read side: Servers page, the tools module (on every call)
    settings: ServerSettings  # write side, used by the settings page


def create_servers_module(config_path: Path, access_log_path: Path, known_tools: KnownTools, access: AccessCheck,
                          engine: "Engine | None" = None) -> ServersModule:
    """Builds the module and returns what it offers.

    engine given: servers and access changes live in Postgres; config_path seeds an empty database.
    No engine: servers.yaml is the store and access changes go to a JSONL file (tests, quick local runs).
    """
    repository: ServerRepository
    log: AccessChangeLog
    if engine is None:
        repository, log = YamlServerRepository(config_path), JsonlAccessChangeLog(access_log_path)
    else:
        from platform_api.servers.repositories.postgres import PostgresAccessChangeLog, PostgresServerRepository

        repository, log = PostgresServerRepository(engine), PostgresAccessChangeLog(engine)
        if repository.is_empty() and config_path.exists():
            _seed(repository, log, YamlServerRepository(config_path), config_path.name)
    return ServersModule(ServerCatalogService(repository, known_tools),
                         ServerSettingsService(repository, log, known_tools, access))


def _seed(target: ServerRepository, log: AccessChangeLog, source: ServerRepository, file: str) -> None:
    """First start on an empty database: import the YAML file, and log it like any other access change."""
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for server in source.all():
        target.save(server)
        log.append(AccessChanged(server.name, tuple(sorted(server.allowed_tools)), (), "system",
                                 f"imported from {file}", at))
