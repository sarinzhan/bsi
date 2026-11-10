"""Server: a machine with Docker that humans gave to the platform, and the tools the agent may use on it."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import Enum

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_TOOL = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

# The one tool that runs any command. The servers domain knows it by name because of the prod rule.
FREE_COMMAND_TOOL = "ssh_exec"


class Env(str, Enum):
    DEV = "dev"
    STAGE = "stage"
    PROD = "prod"


class InvalidServer(ValueError):
    pass


@dataclass(frozen=True)
class Server:
    name: str
    host: str
    env: Env
    allowed_tools: frozenset[str] = frozenset()  # empty = the agent can do nothing here
    systems: frozenset[str] = field(default_factory=frozenset)  # systems allowed to deploy here
    ssh_user: str = "deploy"
    ssh_port: int = 22

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise InvalidServer(f"bad server name: {self.name!r}")
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


@dataclass(frozen=True)
class AccessChanged:
    """Domain event: kept forever, shown in the server's settings."""

    server: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    by: str
    reason: str
    at: str
