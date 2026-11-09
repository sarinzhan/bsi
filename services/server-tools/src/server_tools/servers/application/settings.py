"""Use case: change the list of tools the agent may use on a server. Implements ServerSettings."""

from __future__ import annotations

from datetime import datetime, timezone

from server_tools.servers.application.catalog import to_info
from server_tools.servers.domain.server import AccessChanged, InvalidServer
from server_tools.servers.ports.provided import (
    AccessChange, AccessChangeRejected, ServerInfo, ServerNotFound, ServerSettings,
)
from server_tools.servers.ports.required import AccessChangeLog, KnownTools, ServerRepository


class ServerSettingsService(ServerSettings):
    def __init__(self, repository: ServerRepository, log: AccessChangeLog, known: KnownTools) -> None:
        self._repository, self._log, self._known = repository, log, known

    def change_allowed_tools(self, name: str, tools: list[str], by: str, reason: str) -> ServerInfo:
        server = next((s for s in self._repository.all() if s.name == name), None)
        if server is None:
            raise ServerNotFound(name)
        reason = (reason or "").strip()
        if not reason or len(reason) > 200:
            raise AccessChangeRejected("say why you change the access (one line, up to 200 characters)")
        wanted = frozenset(tools)
        unknown = sorted(wanted - self._known.names())
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
