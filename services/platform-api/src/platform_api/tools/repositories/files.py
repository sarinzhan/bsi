"""Audit log: one JSON line per call (who, what, where, approved by, result)."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from platform_api.tools.interfaces import AuditLog, AuditRecord


class JsonlAuditLog(AuditLog):
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: AuditRecord) -> None:
        line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **asdict(record)}
        with self._path.open("a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
