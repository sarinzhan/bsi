"""Argument rules. Pure functions: each returns a clean value or raises ToolRejected."""

from __future__ import annotations

import posixpath
import re

from platform_api.tools.models import ToolRejected

_SERVICE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")
_SINCE = re.compile(r"^(\d{1,5})([smh])$")
_ENV_KEY = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")
_SECRET_FILES = (".pem", ".key", ".p12", ".jks", ".crt")

MAX_LOG_TAIL = 500
MAX_SINCE_S = 24 * 3600
MAX_FILE_BYTES = 200_000
MAX_FREE_TIMEOUT_S = 300


def service(name: str) -> str:
    if not _SERVICE.match(name or ""):
        raise ToolRejected(f"bad service name {name!r}: use the compose service name, e.g. orders-service")
    return name


def path(value: str, root: str) -> str:
    """A path inside the system folder. Symlinks are checked again on the server (realpath)."""
    if not value or "\x00" in value:
        raise ToolRejected("empty path")
    full = value if value.startswith("/") else posixpath.join(root, value)
    if ".." in full.split("/"):
        raise ToolRejected("'..' is not allowed in paths")
    full = posixpath.normpath(full)
    if full != root and not full.startswith(root + "/"):
        raise ToolRejected(f"only files inside {root} are allowed")
    name = posixpath.basename(full)
    if name.startswith("id_") or name.endswith(_SECRET_FILES):
        raise ToolRejected("keys and certificates are never read or written by the agent")
    return full


def is_env_file(p: str) -> bool:
    name = posixpath.basename(p)
    return name == ".env" or name.endswith(".env")  # .env.example is fine


def since(value: str | None) -> str:
    if value is None:
        return "1h"
    m = _SINCE.match(value)
    if not m:
        raise ToolRejected("since must look like 30m, 2h or 90s")
    seconds = int(m[1]) * {"s": 1, "m": 60, "h": 3600}[m[2]]
    if seconds > MAX_SINCE_S:
        raise ToolRejected("since is limited to 24h")
    return value


def tail(value: int | None) -> int:
    if value is None:
        return 200
    if not 1 <= value <= MAX_LOG_TAIL:
        raise ToolRejected(f"tail must be 1..{MAX_LOG_TAIL}")
    return value


def reason(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        raise ToolRejected("write tools need a one-line reason; the developer sees it on the approval card")
    if len(value) > 200 or "\n" in value:
        raise ToolRejected("reason must be one line, at most 200 characters")
    return value


def image(value: str, system: str, registry: str, allowlist: frozenset[str]) -> str:
    """Company registry images of this system, or an allowlisted public image. Never :latest."""
    name, sep, tag = value.rpartition(":")
    if not sep or "/" in tag or not _TAG.match(tag):
        raise ToolRejected("image needs an explicit tag, e.g. postgres:16-alpine")
    if tag == "latest":
        raise ToolRejected("':latest' is not allowed; pin a version")
    if name.startswith(f"{registry}/{system}/") or name in allowlist:
        return value
    raise ToolRejected(f"image must be {registry}/{system}/... or one of: {', '.join(sorted(allowlist))}")


def args(values: list[str] | None) -> list[str]:
    values = values or []
    if len(values) > 50 or any(len(v) > 1000 or "\x00" in v for v in values):
        raise ToolRejected("too many or too long command arguments")
    return values


def env_vars(values: dict[str, str] | None) -> dict[str, str]:
    values = values or {}
    for k, v in values.items():
        if not _ENV_KEY.match(k) or len(v) > 4096 or "\x00" in v:
            raise ToolRejected(f"bad env variable {k!r}")
    return values


def file_content(value: str) -> bytes:
    data = value.encode()
    if len(data) > MAX_FILE_BYTES:
        raise ToolRejected("file is larger than 200 KB")
    return data


def free_timeout(value: int | None) -> int:
    if value is None:
        return 60
    if not 1 <= value <= MAX_FREE_TIMEOUT_S:
        raise ToolRejected(f"timeout_s must be 1..{MAX_FREE_TIMEOUT_S}")
    return value
