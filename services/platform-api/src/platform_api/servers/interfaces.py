"""What the servers module needs from the outside world."""

from __future__ import annotations

from dataclasses import dataclass
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


class ProbeFailed(RuntimeError):
    """The host could not be reached or did not answer as expected. The message says why."""


@dataclass(frozen=True)
class ProbeResult:
    docker_version: str | None
    memory_total_bytes: int | None
    memory_used_bytes: int | None
    error: str | None = None  # connected, but e.g. the SSH user may not use Docker


class HostProbe(Protocol):
    """SSH to a server, outside agent runs: when a person adds or checks a server."""

    def public_key(self) -> str: ...  # the platform's SSH public key

    async def host_key(self, host: str, port: int) -> str: ...  # raises ProbeFailed

    async def check(self, host: str, port: int, user: str, host_key: str) -> ProbeResult: ...  # raises ProbeFailed
