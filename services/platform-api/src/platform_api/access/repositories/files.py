"""Users in a readable YAML file (config/users.yaml), role changes in a JSONL log.

Good enough for a pilot team. When users come from company SSO/LDAP, replace UserRepository only.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path

import yaml

from platform_api.access.models import Role, RolesChanged, User
from platform_api.access.interfaces import RoleChangeLog, UserRepository

HEADER = """\
# Platform users and their roles. Admins change roles on the Users page; this file is written back.
# roles: developer, devops, admin (a user may have several; admin includes developer + devops).
"""


class YamlUserRepository(UserRepository):
    def __init__(self, path: Path) -> None:
        self._path, self._lock = path, threading.Lock()
        self._raw = yaml.safe_load(path.read_text()) or {}
        self._users = {
            uid: User(uid, u["name"], frozenset(Role(r) for r in u.get("roles", [])))
            for uid, u in (self._raw.get("users") or {}).items()
        }

    def all(self) -> list[User]:
        return list(self._users.values())

    def save(self, user: User) -> None:
        with self._lock:
            self._raw.setdefault("users", {})[user.id] = {"name": user.name, "roles": sorted(r.value for r in user.roles)}
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(HEADER + yaml.safe_dump(self._raw, sort_keys=False, default_flow_style=None, allow_unicode=True))
            os.replace(tmp, self._path)
            self._users[user.id] = user


class JsonlRoleChangeLog(RoleChangeLog):
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: RolesChanged) -> None:
        with self._path.open("a") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def for_user(self, user_id: str) -> list[RolesChanged]:
        if not self._path.exists():
            return []
        out = []
        for line in self._path.read_text().splitlines():
            d = json.loads(line)
            if d["user"] == user_id:
                out.append(RolesChanged(d["user"], tuple(d["added"]), tuple(d["removed"]), d["by"], d["reason"], d["at"]))
        return out
