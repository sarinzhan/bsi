"""Use cases: look up servers. Implements the provided port ServerCatalog."""

from __future__ import annotations

from server_tools.servers.domain.server import Server
from server_tools.servers.ports.provided import ServerCatalog, ServerInfo
from server_tools.servers.ports.required import ServerRepository


def to_info(s: Server) -> ServerInfo:
    return ServerInfo(
        name=s.name, host=s.host, env=s.env.value, allowed_tools=tuple(sorted(s.allowed_tools)),
        systems=tuple(sorted(s.systems)), ssh_user=s.ssh_user, ssh_port=s.ssh_port,
    )


class ServerCatalogService(ServerCatalog):
    def __init__(self, repository: ServerRepository) -> None:
        self._repository = repository

    def get(self, name: str) -> ServerInfo | None:
        return next((to_info(s) for s in self._repository.all() if s.name == name), None)

    def list(self) -> list[ServerInfo]:
        return [to_info(s) for s in self._repository.all()]
