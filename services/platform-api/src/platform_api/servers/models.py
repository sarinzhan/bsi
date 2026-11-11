"""Server: a machine with Docker that humans gave to the platform, and the tools the agent may use on it."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass, field, replace
from enum import Enum

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_TOOL = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_SYSTEM = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
_RESERVED_SYSTEMS = {"servers", "users", "api", "mcp", "runner", "assets"}  # web app pages and routes
_HOST = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$|^[0-9A-Fa-f:]{2,39}$")
_SSH_USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_HOST_KEY = re.compile(r"^(ssh-ed25519|ecdsa-sha2-nistp(256|384|521)|ssh-rsa) [A-Za-z0-9+/]+={0,2}$")

# The one tool that runs any command. The servers domain knows it by name because of the prod rule.
FREE_COMMAND_TOOL = "ssh_exec"


class Env(str, Enum):
    DEV = "dev"
    STAGE = "stage"
    PROD = "prod"


class InvalidServer(ValueError):
    pass


def fingerprint(host_key: str) -> str:
    """SHA256 fingerprint of an OpenSSH public key line, as `ssh-keygen -lf` prints it."""
    blob = base64.b64decode(host_key.split()[1])
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


@dataclass(frozen=True)
class Health:
    """What the last connection check found."""

    checked_at: str  # ISO date-time, UTC
    docker_version: str | None = None
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    error: str | None = None  # the check failed: why


@dataclass(frozen=True)
class Server:
    name: str
    host: str
    env: Env
    allowed_tools: frozenset[str] = frozenset()  # empty = the agent can do nothing here
    systems: frozenset[str] = field(default_factory=frozenset)  # systems allowed to deploy here
    ssh_user: str = "deploy"
    ssh_port: int = 22
    host_key: str | None = None  # pinned SSH host key ("ssh-ed25519 AAAA..."); SSH refuses any other
    health: Health | None = None

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise InvalidServer(f"bad server name {self.name!r}: lowercase letters, digits and -, 2-63 characters")
        if not _HOST.match(self.host):
            raise InvalidServer(f"bad host {self.host!r}: a host name or an IP address")
        if not _SSH_USER.match(self.ssh_user):
            raise InvalidServer(f"bad SSH user {self.ssh_user!r}")
        if not 1 <= self.ssh_port <= 65535:
            raise InvalidServer(f"bad SSH port {self.ssh_port}")
        bad_systems = sorted(s for s in self.systems if not _SYSTEM.match(s) or s in _RESERVED_SYSTEMS)
        if bad_systems:
            raise InvalidServer(f"bad system names {bad_systems}: lowercase letters, digits and -")
        if self.host_key is not None:
            if not _HOST_KEY.match(self.host_key):
                raise InvalidServer("bad host key: expected one line like 'ssh-ed25519 AAAA...'")
            try:
                base64.b64decode(self.host_key.split()[1], validate=True)
            except binascii.Error as e:
                raise InvalidServer("bad host key: not base64") from e
        bad = [t for t in self.allowed_tools if not _TOOL.match(t)]
        if bad:
            raise InvalidServer(f"{self.name}: bad tool names {bad}")
        if FREE_COMMAND_TOOL in self.allowed_tools and self.env is Env.PROD:
            raise InvalidServer(f"{self.name}: {FREE_COMMAND_TOOL} (any command) is never allowed on prod")

    def serves(self, system: str, env: str) -> bool:
        return system in self.systems and self.env.value == env

    def allows(self, tool: str) -> bool:
        return tool in self.allowed_tools

    def with_allowed_tools(self, tools: frozenset[str]) -> "Server":
        """Same server, new tool list. Re-validated, so ssh_exec on prod is still refused."""
        return replace(self, allowed_tools=frozenset(tools))

    def with_health(self, health: Health) -> "Server":
        return replace(self, health=health)


@dataclass(frozen=True)
class AccessChanged:
    """Domain event: kept forever, shown in the server's settings."""

    server: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    by: str
    reason: str
    at: str
