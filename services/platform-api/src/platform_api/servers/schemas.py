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
    host_key: str | None = None  # pinned SSH host key; None = SSH to this server is refused
    host_key_fingerprint: str | None = None  # "SHA256:...", as `ssh-keygen -lf` shows it
    checked_at: str | None = None  # last connection check
    docker_version: str | None = None
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    check_error: str | None = None


@dataclass(frozen=True)
class NewServer:
    """The Add server form."""

    name: str
    host: str
    env: str
    systems: tuple[str, ...]
    ssh_user: str
    ssh_port: int
    host_key: str  # as fetched with fetch_host_key and confirmed by the person


@dataclass(frozen=True)
class HostKey:
    key: str  # "ssh-ed25519 AAAA..."
    fingerprint: str  # "SHA256:..."


@dataclass(frozen=True)
class SystemInfo:
    """A system the platform works on: it exists once a server serves it."""

    id: str
    envs: tuple[str, ...]  # environments that have a server for it


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


class ServerRejected(ValueError):
    """The new server is not valid (name taken, bad host, no system...). Message is shown in the form."""


class HostUnreachable(RuntimeError):
    """SSH to the host did not work (no route, wrong port, key not accepted...). Message is shown to the person."""


class AccessChangeRejected(ValueError):
    """The change breaks a rule (unknown tool, ssh_exec on prod, no reason). Message is shown to the admin."""


class ServerCatalog(Protocol):
    """Read side: the Servers page, and the tools module on every tool call."""

    def get(self, name: str) -> ServerInfo | None: ...

    def list(self) -> list[ServerInfo]: ...

    def tools(self) -> list[dict[str, str]]: ...  # the tools that exist (the tools module's catalog), for the web app

    def systems(self) -> list[SystemInfo]: ...  # every system some server serves, sorted


class ServerSettings(Protocol):
    """Write side: the server settings page. Needs servers.manage (devops or admin); `by` is the user id."""

    def change_allowed_tools(self, name: str, tools: list[str], by: str, reason: str) -> ServerInfo: ...

    def access_history(self, name: str) -> list[AccessChange]: ...


class ServerAdmin(Protocol):
    """Adding servers and checking them. Needs servers.manage (devops or admin); `by` is the user id."""

    def platform_public_key(self, by: str) -> str: ...  # goes into ~/.ssh/authorized_keys on the server

    async def fetch_host_key(self, host: str, port: int, by: str) -> HostKey: ...  # raises HostUnreachable

    def add(self, server: NewServer, by: str) -> ServerInfo: ...  # no tools allowed yet

    async def check(self, name: str, by: str) -> ServerInfo: ...  # SSH in, read Docker version and memory
