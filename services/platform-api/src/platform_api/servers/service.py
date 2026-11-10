"""Servers service: look up servers (ServerCatalog) and change the tools the agent may use on them
(ServerSettings: devops and admins only, every change logged)."""

from __future__ import annotations

from datetime import datetime, timezone

from platform_api.access.schemas import AccessCheck
from platform_api.servers.interfaces import AccessChangeLog, KnownTools, ServerRepository, ToolCatalogUnavailable
from platform_api.servers.models import AccessChanged, InvalidServer, Server
from platform_api.servers.schemas import (
    AccessChange, AccessChangeNotAllowed, AccessChangeRejected, ServerCatalog, ServerInfo, ServerNotFound,
    ServerSettings,
)


def to_info(s: Server) -> ServerInfo:
    return ServerInfo(
        name=s.name, host=s.host, env=s.env.value, allowed_tools=tuple(sorted(s.allowed_tools)),
        systems=tuple(sorted(s.systems)), ssh_user=s.ssh_user, ssh_port=s.ssh_port,
    )


class ServerCatalogService(ServerCatalog):
    def __init__(self, repository: ServerRepository, known: KnownTools) -> None:
        self._repository, self._known = repository, known

    def get(self, name: str) -> ServerInfo | None:
        return next((to_info(s) for s in self._repository.all() if s.name == name), None)

    def list(self) -> list[ServerInfo]:
        return [to_info(s) for s in self._repository.all()]

    def tools(self) -> list[dict[str, str]]:
        try:
            return self._known.infos()
        except ToolCatalogUnavailable:
            return []  # the page shows no tools rather than failing


MANAGE_SERVERS = "servers.manage"  # access permission: devops and admins


class ServerSettingsService(ServerSettings):
    def __init__(self, repository: ServerRepository, log: AccessChangeLog, known: KnownTools,
                 access: AccessCheck) -> None:
        self._repository, self._log, self._known, self._access = repository, log, known, access

    def change_allowed_tools(self, name: str, tools: list[str], by: str, reason: str) -> ServerInfo:
        if not self._access.can(by, MANAGE_SERVERS):
            raise AccessChangeNotAllowed(f"only devops and admins change server access (needs {MANAGE_SERVERS})")
        server = next((s for s in self._repository.all() if s.name == name), None)
        if server is None:
            raise ServerNotFound(name)
        reason = (reason or "").strip()
        if not reason or len(reason) > 200:
            raise AccessChangeRejected("say why you change the access (one line, up to 200 characters)")
        wanted = frozenset(tools)
        try:
            known = self._known.names()
        except ToolCatalogUnavailable as e:
            raise AccessChangeRejected(f"cannot check the tool names right now ({e}); nothing was changed") from e
        unknown = sorted(wanted - known)
        if unknown:
            raise AccessChangeRejected(f"unknown tools: {', '.join(unknown)}")
        try:
            changed = server.with_allowed_tools(wanted)
        except InvalidServer as e:
            raise AccessChangeRejected(str(e)) from e
        if changed == server:
            return to_info(server)  # nothing to do, nothing to log
        self._repository.save(changed)
        self._log.append(AccessChanged(
            name, tuple(sorted(wanted - server.allowed_tools)), tuple(sorted(server.allowed_tools - wanted)),
            by, reason, datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ))
        return to_info(changed)

    def access_history(self, name: str) -> list[AccessChange]:
        return [AccessChange(e.server, e.added, e.removed, e.by, e.reason, e.at)
                for e in reversed(self._log.for_server(name))]  # newest first
