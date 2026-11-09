"""servers module: which machines exist and what the agent may do on them."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from server_tools.servers.adapters.access_log_jsonl import JsonlAccessChangeLog
from server_tools.servers.adapters.yaml_repository import YamlServerRepository
from server_tools.servers.application.catalog import ServerCatalogService
from server_tools.servers.application.settings import ServerSettingsService
from server_tools.servers.ports.provided import ServerCatalog, ServerSettings
from server_tools.servers.ports.required import KnownTools


@dataclass(frozen=True)
class ServersModule:
    catalog: ServerCatalog  # read side, used by the tools module
    settings: ServerSettings  # write side, used by the settings page


def create_servers_module(config_path: Path, access_log_path: Path, known_tools: KnownTools) -> ServersModule:
    """Wires the module and returns only its provided ports."""
    repository = YamlServerRepository(config_path)
    return ServersModule(ServerCatalogService(repository),
                         ServerSettingsService(repository, JsonlAccessChangeLog(access_log_path), known_tools))
