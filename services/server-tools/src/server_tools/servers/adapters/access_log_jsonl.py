"""Access changes, one JSON line each. Never edited, only appended."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from server_tools.servers.domain.server import AccessChanged
from server_tools.servers.ports.required import AccessChangeLog


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
