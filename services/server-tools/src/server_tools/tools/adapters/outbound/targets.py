"""Targets port implemented on top of the servers module's provided port."""

from __future__ import annotations

from server_tools.servers.ports.provided import ServerCatalog
from server_tools.tools.domain.model import Target
from server_tools.tools.ports.required import SshAddress, Targets


class ServerCatalogTargets(Targets):
    def __init__(self, servers: ServerCatalog) -> None:
        self._servers = servers

    def find(self, name: str) -> Target | None:
        s = self._servers.get(name)
        if s is None:
            return None
        return Target(name=s.name, env=s.env, systems=s.systems, allowed_tools=s.allowed_tools)

    def address(self, name: str) -> SshAddress:
        s = self._servers.get(name)
        if s is None:
            raise LookupError(name)
        return SshAddress(s.host, s.ssh_port, s.ssh_user)
