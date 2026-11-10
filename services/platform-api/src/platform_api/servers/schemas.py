"""What the servers module offers to other modules. Plain DTOs only: no domain objects leak out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ServerInfo:
    name: str
    host: str
    env: Literal["dev", "stage", "prod"]
    allowed_tools: tuple[str, ...]  # sorted
    systems: tuple[str, ...]
    ssh_user: str
    ssh_port: int


@dataclass(frozen=True)
class AccessChange:
    server: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    by: str
    reason: str
    at: str  # ISO date-time, UTC


class ServerNotFound(LookupError):
    pass


class AccessChangeNotAllowed(PermissionError):
    """The user lacks servers.manage (devops or admin)."""


class AccessChangeRejected(ValueError):
    """The change breaks a rule (unknown tool, ssh_exec on prod, no reason). Message is shown to the admin."""


class ServerCatalog(Protocol):
    """Read side: the Servers page, and the tools module on every tool call."""

    def get(self, name: str) -> ServerInfo | None: ...

    def list(self) -> list[ServerInfo]: ...

    def tools(self) -> list[dict[str, str]]: ...  # the tools that exist (the tools module's catalog), for the web app


class ServerSettings(Protocol):
    """Write side: the server settings page. Needs servers.manage (devops or admin); `by` is the user id."""

    def change_allowed_tools(self, name: str, tools: list[str], by: str, reason: str) -> ServerInfo: ...

    def access_history(self, name: str) -> list[AccessChange]: ...
