"""What the servers module needs from the outside world."""

from __future__ import annotations

from typing import Protocol

from platform_api.servers.models import AccessChanged, Server


class ServerRepository(Protocol):
    def all(self) -> list[Server]: ...

    def save(self, server: Server) -> None: ...


class AccessChangeLog(Protocol):
    def append(self, event: AccessChanged) -> None: ...

    def for_server(self, name: str) -> list[AccessChanged]: ...


class ToolCatalogUnavailable(RuntimeError):
    """The list of existing tools could not be read (the tools module is not ready). Access is then not changed."""


class KnownTools(Protocol):
    """Names of the tools that exist. The tools module owns the list."""

    def names(self) -> frozenset[str]: ...  # raises ToolCatalogUnavailable

    def infos(self) -> list[dict[str, str]]: ...  # the whole catalog (name, kind, summary, params, approval)
