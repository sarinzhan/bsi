"""Sandbox, DEV ONLY: runs each agent as a local process instead of a container.

No isolation at all: the agent runs as you, on your machine. Use it to try the whole flow without Docker:
    BSI_SANDBOX=process  BSI_RUNNER_COMMAND="uv run --project ../agent-runner python -m agent_runner"
Output of each run goes to var/runs/<run id>.log.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from platform_api.agent.interfaces import Sandbox, SandboxError, SandboxSpec


class ProcessSandbox(Sandbox):
    def __init__(self, command: str, cwd: Path, log_dir: Path) -> None:
        self._command, self._cwd, self._log_dir = shlex.split(command), cwd, log_dir
        self._procs: dict[str, subprocess.Popen] = {}

    def start(self, spec: SandboxSpec) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log = (self._log_dir / f"{spec.run_id}.log").open("w")
        # not platform-api's own settings or virtualenv: the runner has its own
        env = {k: v for k, v in os.environ.items() if not k.startswith("BSI_") and k != "VIRTUAL_ENV"}
        try:
            self._procs[spec.run_id] = subprocess.Popen(self._command, cwd=self._cwd, env={**env, **spec.env},
                                                        stdout=log, stderr=subprocess.STDOUT)
        except OSError as e:
            raise SandboxError(f"{type(e).__name__}: {e}") from e

    def stop(self, run_id: str) -> None:
        proc = self._procs.pop(run_id, None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
