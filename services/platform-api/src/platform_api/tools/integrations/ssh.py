"""Runs commands over SSH with the platform's key. The key never leaves this service."""

from __future__ import annotations

from pathlib import Path

import asyncssh

from platform_api.tools.models import Command, ExecResult
from platform_api.tools.interfaces import Executor, SshAddress


class SshExecutor(Executor):
    def __init__(self, key_path: Path, known_hosts: Path | None = None) -> None:
        self._key = str(key_path)
        # Host keys are always pinned, never "accept any host": the key saved with the server (added in the
        # web app), else this known_hosts file. Neither: the call is refused.
        self._known_hosts = str(known_hosts) if known_hosts is not None and known_hosts.exists() else None

    async def run(self, address: SshAddress, command: Command) -> ExecResult:
        if address.host_key:
            known_hosts: object = ([asyncssh.import_public_key(address.host_key)], [], [])
        elif self._known_hosts:
            known_hosts = self._known_hosts
        else:
            raise RuntimeError(f"{address.host}: no pinned host key; add the server in the web app")
        async with asyncssh.connect(
            address.host, port=address.port, username=address.user,
            client_keys=[self._key], known_hosts=known_hosts, connect_timeout=10,
        ) as conn:
            result = await conn.run(command.script, input=command.stdin, encoding=None,
                                    check=False, timeout=command.timeout_s)
        out = (result.stdout or b"").decode(errors="replace")
        err = (result.stderr or b"").decode(errors="replace")
        return ExecResult(result.exit_status if result.exit_status is not None else -1, out, err)
