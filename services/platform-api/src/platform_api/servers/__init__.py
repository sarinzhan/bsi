"""servers module: which machines exist, what the agent may do on them, adding and checking them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from platform_api.access.schemas import AccessCheck
from platform_api.servers.integrations.fake_probe import FakeHostProbe
from platform_api.servers.interfaces import AccessChangeLog, HostProbe, KnownTools, ServerRepository
from platform_api.servers.models import Server
from platform_api.servers.repositories.memory import InMemoryAccessChangeLog, InMemoryServerRepository
from platform_api.servers.schemas import ServerAdmin, ServerCatalog, ServerSettings
from platform_api.servers.service import ServerAdminService, ServerCatalogService, ServerSettingsService

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True)
class ServersModule:
    catalog: ServerCatalog  # read side: Servers page, the tools module (on every call)
    settings: ServerSettings  # allowed tools, on the settings page
    admin: ServerAdmin  # add and check servers


def create_servers_module(known_tools: KnownTools, access: AccessCheck, engine: "Engine | None" = None,
                          probe: HostProbe | None = None, servers: Iterable[Server] = ()) -> ServersModule:
    """engine: servers and access changes in Postgres (the platform). No engine: in memory, for tests (`servers`).
    probe: SSH to servers when they are added or checked (real SSH in prod; a fake that touches nothing in dev).
    """
    repository: ServerRepository
    log: AccessChangeLog
    if engine is None:
        repository, log = InMemoryServerRepository(servers), InMemoryAccessChangeLog()
    else:
        from platform_api.servers.repositories.postgres import PostgresAccessChangeLog, PostgresServerRepository

        repository, log = PostgresServerRepository(engine), PostgresAccessChangeLog(engine)
    probe = probe or FakeHostProbe()
    return ServersModule(ServerCatalogService(repository, known_tools),
                         ServerSettingsService(repository, log, known_tools, access),
                         ServerAdminService(repository, log, probe, access))
