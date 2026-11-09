"""Secrets never go back to the agent or the chat."""

from __future__ import annotations

import json
import re

_KV = re.compile(
    r"(?i)\b([A-Z0-9_.-]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY|CREDENTIALS?)[A-Z0-9_.-]*)"
    r"(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)
_URL_CREDS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+):([^\s@/]+)@")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)

MASK = "***"
MAX_LINES = 500
MAX_BYTES = 200_000


def mask(text: str) -> str:
    text = _PEM.sub("-----PRIVATE KEY REMOVED-----", text)
    text = _KV.sub(lambda m: f"{m[1]}{m[2]}{MASK}", text)
    text = _URL_CREDS.sub(lambda m: f"{m[1]}:{MASK}@", text)
    return _BEARER.sub(lambda m: f"{m[1]}{MASK}", text)


def env_names_only(text: str) -> str:
    """For .env files: keep variable names, drop values."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            out.append(line)
        else:
            out.append(s.split("=", 1)[0] + "=" + MASK)
    return "\n".join(out)


def strip_inspect_env(text: str) -> str:
    """docker inspect: keep env variable names, drop values."""
    try:
        data = json.loads(text)
    except ValueError:
        return text
    for item in data if isinstance(data, list) else [data]:
        cfg = item.get("Config") or {}
        if isinstance(cfg.get("Env"), list):
            cfg["Env"] = [e.split("=", 1)[0] + "=" + MASK for e in cfg["Env"]]
    return json.dumps(data, indent=2)


def cap(text: str, keep: str = "head") -> str:
    lines = text.splitlines()
    cut = len(lines) > MAX_LINES
    lines = lines[-MAX_LINES:] if keep == "tail" else lines[:MAX_LINES]
    out = "\n".join(lines)
    if len(out.encode()) > MAX_BYTES:
        out = out.encode()[-MAX_BYTES:].decode(errors="ignore") if keep == "tail" else out.encode()[:MAX_BYTES].decode(errors="ignore")
        cut = True
    if cut:
        note = f"[output cut to {MAX_LINES} lines / {MAX_BYTES // 1000} KB]"
        out = f"{note}\n{out}" if keep == "tail" else f"{out}\n{note}"
    return out
