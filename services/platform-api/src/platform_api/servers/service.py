"""Servers service: look up servers (ServerCatalog), change the tools the agent may use on them
(ServerSettings), add and check servers (ServerAdmin). Changes: devops and admins only, every one logged."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from platform_api.access.schemas import AccessCheck
from platform_api.servers.interfaces import (
    AccessChangeLog, HostProbe, KnownTools, ProbeFailed, ServerRepository, ToolCatalogUnavailable,
)
from platform_api.servers.models import AccessChanged, Env, Health, InvalidServer, Server, fingerprint
from platform_api.servers.schemas import (
    AccessChange, AccessChangeNotAllowed, AccessChangeRejected, HostKey, HostUnreachable, NewServer, ServerAdmin,
    ServerCatalog, ServerInfo, ServerNotFound, ServerRejected, ServerSettings, SystemInfo,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_info(s: Server) -> ServerInfo:
    h = s.health
    return ServerInfo(
        name=s.name, host=s.host, env=s.env.value, allowed_tools=tuple(sorted(s.allowed_tools)),
        systems=tuple(sorted(s.systems)), ssh_user=s.ssh_user, ssh_port=s.ssh_port,
        host_key=s.host_key, host_key_fingerprint=fingerprint(s.host_key) if s.host_key else None,
        checked_at=h.checked_at if h else None, docker_version=h.docker_version if h else None,
        memory_total_bytes=h.memory_total_bytes if h else None, memory_used_bytes=h.memory_used_bytes if h else None,
        check_error=h.error if h else None,
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

    def systems(self) -> list[SystemInfo]:
        envs: dict[str, set[str]] = {}
        for s in self._repository.all():
            for system in s.systems:
                envs.setdefault(system, set()).add(s.env.value)
        order = [e.value for e in Env]
        return [SystemInfo(system, tuple(sorted(e, key=order.index))) for system, e in sorted(envs.items())]


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
            by, reason, _now(),
        ))
        return to_info(changed)

    def access_history(self, name: str) -> list[AccessChange]:
        return [AccessChange(e.server, e.added, e.removed, e.by, e.reason, e.at)
                for e in reversed(self._log.for_server(name))]  # newest first


class ServerAdminService(ServerAdmin):
    def __init__(self, repository: ServerRepository, log: AccessChangeLog, probe: HostProbe,
                 access: AccessCheck) -> None:
        self._repository, self._log, self._probe, self._access = repository, log, probe, access

    def _allowed(self, by: str) -> None:
        if not self._access.can(by, MANAGE_SERVERS):
            raise AccessChangeNotAllowed(f"only devops and admins add and check servers (needs {MANAGE_SERVERS})")

    def platform_public_key(self, by: str) -> str:
        self._allowed(by)
        return self._probe.public_key()

    async def fetch_host_key(self, host: str, port: int, by: str) -> HostKey:
        self._allowed(by)
        try:
            Server("probe", host, Env.DEV, ssh_port=port)  # the same host and port rules as a real server
        except InvalidServer as e:
            raise ServerRejected(str(e)) from e
        try:
            key = await self._probe.host_key(host, port)
        except ProbeFailed as e:
            raise HostUnreachable(str(e)) from e
        return HostKey(key, fingerprint(key))

    def add(self, new: NewServer, by: str) -> ServerInfo:
        self._allowed(by)
        systems = frozenset(s.strip() for s in new.systems if s.strip())
        if not systems:
            raise ServerRejected("name at least one system this server is for")
        try:
            env = Env(new.env)
        except ValueError as e:
            raise ServerRejected(f"env must be one of {[x.value for x in Env]}") from e
        try:
            server = Server(name=new.name.strip(), host=new.host.strip(), env=env, systems=systems,
                            ssh_user=new.ssh_user.strip(), ssh_port=new.ssh_port, host_key=new.host_key.strip())
        except InvalidServer as e:
            raise ServerRejected(str(e)) from e
        if any(s.name == server.name for s in self._repository.all()):
            raise ServerRejected(f"a server named {server.name!r} already exists")
        self._repository.save(server)
        self._log.append(AccessChanged(server.name, (), (), by,
                                       f"added the server ({server.ssh_user}@{server.host}:{server.ssh_port})", _now()))
        return to_info(server)

    async def check(self, name: str, by: str) -> ServerInfo:
        self._allowed(by)
        server = next((s for s in await asyncio.to_thread(self._repository.all) if s.name == name), None)
        if server is None:
            raise ServerNotFound(name)
        if not server.host_key:
            health = Health(_now(), error="no pinned host key: add the server again with its host key")
        else:
            try:
                r = await self._probe.check(server.host, server.ssh_port, server.ssh_user, server.host_key)
                health = Health(_now(), r.docker_version, r.memory_total_bytes, r.memory_used_bytes, r.error)
            except ProbeFailed as e:
                health = Health(_now(), error=str(e))
        checked = server.with_health(health)
        await asyncio.to_thread(self._repository.save, checked)
        return to_info(checked)
