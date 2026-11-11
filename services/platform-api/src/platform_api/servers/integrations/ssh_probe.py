"""SSH to a server when a person adds or checks it (asyncssh), with the platform's key.

host_key: connects only far enough to read the server's host key. The person compares its fingerprint with
the one on the server (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`) before saving it.
check: logs in, trusting only the pinned key, and reads the Docker version and memory.
"""

from __future__ import annotations

from pathlib import Path

import asyncssh

from platform_api.servers.interfaces import HostProbe, ProbeFailed, ProbeResult

# Docker version, then "total used" memory in bytes. Read-only, fixed: no input from the person goes in here.
CHECK_SCRIPT = (
    "docker version --format '{{.Server.Version}}' 2>&1 | head -n 1; echo '---'; "
    "free -b 2>/dev/null | awk '/^Mem:/ {print $2, $3}'"
)
TIMEOUT_S = 10


class SshHostProbe(HostProbe):
    def __init__(self, key_path: Path) -> None:
        self._key_path = key_path

    def public_key(self) -> str:
        try:
            key = asyncssh.read_private_key(str(self._key_path))
        except (OSError, asyncssh.KeyImportError) as e:
            raise ProbeFailed(f"cannot read the platform's SSH key: {e}") from e
        algorithm, data = key.export_public_key().decode().split()[:2]
        return f"{algorithm} {data} bsi-platform"

    async def host_key(self, host: str, port: int) -> str:
        """The ed25519 key if the server has one (what the person checks with ssh-keygen), else its default."""
        try:
            try:
                key = await asyncssh.get_server_host_key(host, port, server_host_key_algs=["ssh-ed25519"])
            except asyncssh.KeyExchangeFailed:
                key = await asyncssh.get_server_host_key(host, port)
        except (OSError, asyncssh.Error) as e:
            raise ProbeFailed(f"cannot reach {host}:{port}: {e}") from e
        if key is None:
            raise ProbeFailed(f"{host}:{port} sent no host key")
        algorithm, data = key.export_public_key().decode().split()[:2]
        return f"{algorithm} {data}"

    async def check(self, host: str, port: int, user: str, host_key: str) -> ProbeResult:
        try:
            trusted = asyncssh.import_public_key(host_key)
            async with asyncssh.connect(host, port=port, username=user, client_keys=[str(self._key_path)],
                                        known_hosts=([trusted], [], []), connect_timeout=TIMEOUT_S) as conn:
                result = await conn.run(CHECK_SCRIPT, check=False, timeout=TIMEOUT_S)
        except asyncssh.HostKeyNotVerifiable as e:
            raise ProbeFailed(f"the host key changed: {e}. Re-add the server only if you trust the new key") from e
        except asyncssh.PermissionDenied as e:
            raise ProbeFailed(f"{user}@{host} did not accept the platform's key: add it to "
                              f"~{user}/.ssh/authorized_keys") from e
        except (OSError, asyncssh.Error) as e:
            raise ProbeFailed(f"cannot connect to {user}@{host}:{port}: {e}") from e
        docker, _, mem = str(result.stdout or "").partition("---")
        docker = docker.strip()
        error = None
        if not docker or " " in docker or "denied" in docker.lower() or "not found" in docker.lower():
            error = f"docker: {docker or 'no answer'}"[:300]
            docker = None
        total = used = None
        parts = mem.split()
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            total, used = int(parts[0]), int(parts[1])
        return ProbeResult(docker, total, used, error)
