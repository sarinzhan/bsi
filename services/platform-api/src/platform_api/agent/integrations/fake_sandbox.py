"""A sandbox that starts nothing. Default in dev mode and in tests."""

from __future__ import annotations

import logging

from platform_api.agent.interfaces import Sandbox, SandboxError, SandboxSpec

log = logging.getLogger("platform_api.agent")


class FakeSandbox(Sandbox):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.started: list[SandboxSpec] = []
        self.stopped: list[str] = []

    def start(self, spec: SandboxSpec) -> None:
        if self.fail:
            raise SandboxError("image not found")
        self.started.append(spec)
        log.warning("FAKE sandbox: no agent container started for %s, so the chat will wait until the run "
                    "expires. Set BSI_SANDBOX=docker (docker-compose.agents.yml) for real agents.", spec.run_id)

    def stop(self, run_id: str) -> None:
        self.stopped.append(run_id)
