"""Servers live in a readable YAML file (config/servers.yaml).

DevOps and admins change the allowed tools from the server settings page; this adapter writes it back to the
same file (atomic replace), so the file stays the single readable source. Commit it to git.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import yaml

from server_tools.servers.domain.server import Env, Server
from server_tools.servers.ports.required import ServerRepository

HEADER = """\
# Servers the platform may use. DevOps and admins change allowed_tools in the server settings page.
# allowed_tools: the tools the agent may call on this server (empty or missing = nothing).
#   read:  folder_list, file_read, docker_ps, docker_logs, docker_inspect, docker_stats
#   write: file_write, docker_run, compose_run, compose_restart
#   full:  ssh_exec (any command) - refused on prod
"""


class YamlServerRepository(ServerRepository):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._raw = yaml.safe_load(path.read_text()) or {}
        self._servers = {name: self._to_server(name, s) for name, s in (self._raw.get("servers") or {}).items()}
        # invalid servers (e.g. full access on prod) fail at startup, not at call time

    @staticmethod
    def _to_server(name: str, s: dict) -> Server:
        return Server(
            name=name, host=s["host"], env=Env(s["env"]),
            allowed_tools=frozenset(s.get("allowed_tools") or []),
            systems=frozenset(s.get("systems", [])),
            ssh_user=s.get("ssh_user", "deploy"), ssh_port=int(s.get("ssh_port", 22)),
        )

    def all(self) -> list[Server]:
        return list(self._servers.values())

    def save(self, server: Server) -> None:
        with self._lock:
            entry = self._raw.setdefault("servers", {}).setdefault(server.name, {})
            entry.update({"host": server.host, "env": server.env.value, "systems": sorted(server.systems),
                          "allowed_tools": sorted(server.allowed_tools)})
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(HEADER + yaml.safe_dump(self._raw, sort_keys=False, default_flow_style=None))
            os.replace(tmp, self._path)
            self._servers[server.name] = server
