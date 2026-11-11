"""A probe that touches no network. Dev mode (no real SSH) and tests."""

from __future__ import annotations

from platform_api.servers.interfaces import HostProbe, ProbeFailed, ProbeResult

# real-looking ed25519 keys whose private halves were thrown away: they open nothing
FAKE_HOST_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINSk2JMUjJQ6x2SIOXVOkEqDhxkHCRGxFKzC9MyHFzv/"


class FakeHostProbe(HostProbe):
    def __init__(self, unreachable: frozenset[str] = frozenset()) -> None:
        self.unreachable = set(unreachable)

    def public_key(self) -> str:
        return "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINvYwgTvH0pd4zHSGCxg0h8KwPqeM2H+It9QaWSgyLLJ bsi-platform-dev-fake"

    async def host_key(self, host: str, port: int) -> str:
        if host in self.unreachable:
            raise ProbeFailed(f"cannot reach {host}:{port}: connection refused")
        return FAKE_HOST_KEY

    async def check(self, host: str, port: int, user: str, host_key: str) -> ProbeResult:
        if host in self.unreachable:
            raise ProbeFailed(f"cannot connect to {user}@{host}:{port}: connection refused")
        return ProbeResult("fake (dev mode: no SSH)", 8 * 1024**3, 3 * 1024**3)
