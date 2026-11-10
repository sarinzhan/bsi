"""A sandbox that starts nothing. Default in dev mode and in tests."""

from __future__ import annotations

from platform_api.agent.interfaces import Sandbox, SandboxError, SandboxSpec


class FakeSandbox(Sandbox):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.started: list[SandboxSpec] = []
        self.stopped: list[str] = []

    def start(self, spec: SandboxSpec) -> None:
        if self.fail:
            raise SandboxError("image not found")
        self.started.append(spec)

    def stop(self, run_id: str) -> None:
        self.stopped.append(run_id)
