"""What the servers module needs from the outside world."""

from __future__ import annotations

from typing import Protocol

from server_tools.servers.domain.server import AccessChanged, Server


class ServerRepository(Protocol):
    def all(self) -> list[Server]: ...

    def save(self, server: Server) -> None: ...


class AccessChangeLog(Protocol):
    def append(self, event: AccessChanged) -> None: ...

    def for_server(self, name: str) -> list[AccessChanged]: ...


class KnownTools(Protocol):
    """Names of the tools that exist. Wired in main.py from the tools module, so servers never imports tools."""

    def names(self) -> frozenset[str]: ...
