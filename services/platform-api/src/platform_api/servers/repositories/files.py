"""Servers and access changes in files, for running without a database.

Servers: a readable YAML file (config/servers.yaml), written back atomically when access changes.
Access changes: one JSON line each, never edited, only appended.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path

import yaml

from platform_api.servers.interfaces import AccessChangeLog, ServerRepository
from platform_api.servers.models import AccessChanged, Env, Server


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


class JsonlAccessChangeLog(AccessChangeLog):
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: AccessChanged) -> None:
        line = asdict(event)
        with self._path.open("a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def for_server(self, name: str) -> list[AccessChanged]:
        if not self._path.exists():
            return []
        events = []
        for line in self._path.read_text().splitlines():
            d = json.loads(line)
            if d["server"] == name:
                events.append(AccessChanged(d["server"], tuple(d["added"]), tuple(d["removed"]),
                                            d["by"], d["reason"], d["at"]))
        return events
