"""Servers and access changes in memory. For tests only: the platform itself always uses Postgres."""

from __future__ import annotations

from typing import Iterable

from platform_api.servers.interfaces import AccessChangeLog, ServerRepository
from platform_api.servers.models import AccessChanged, Server


class InMemoryServerRepository(ServerRepository):
    def __init__(self, servers: Iterable[Server] = ()) -> None:
        self._servers = {s.name: s for s in servers}

    def all(self) -> list[Server]:
        return sorted(self._servers.values(), key=lambda s: s.name)

    def save(self, server: Server) -> None:
        self._servers[server.name] = server


class InMemoryAccessChangeLog(AccessChangeLog):
    def __init__(self) -> None:
        self._events: list[AccessChanged] = []

    def append(self, event: AccessChanged) -> None:
        self._events.append(event)

    def for_server(self, name: str) -> list[AccessChanged]:
        return [e for e in self._events if e.server == name]
