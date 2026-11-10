"""One Docker container per run, locked down.

The container is untrusted (later it runs code the agent wrote), so it gets nothing valuable:
- only the run token (no SSH key, no database password, no Docker socket)
- a network that reaches platform-api only (create it with `internal: true`: no internet)
- non-root user, read-only root filesystem, no Linux capabilities, no privilege escalation
- CPU, memory and process limits; removed as soon as it exits
Uses the Docker API (not the CLI), so the token never shows up in a process list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform_api.agent.interfaces import Sandbox, SandboxError, SandboxSpec


@dataclass(frozen=True)
class SandboxLimits:
    memory: str = "2g"
    cpus: float = 1.0
    pids: int = 256
    tmp_size: str = "512m"
    workspace_size: str = "2g"


def container_name(run_id: str) -> str:
    return f"bsi-{run_id}"


class DockerSandbox(Sandbox):
    def __init__(self, image: str, network: str, limits: SandboxLimits = SandboxLimits(), client: Any = None) -> None:
        name, _, tag = image.rpartition(":")
        if not name or not tag or "/" in tag or tag == "latest":
            raise ValueError(f"agent image needs a pinned tag (not latest): {image!r}")
        self._image, self._network, self._limits = image, network, limits
        if client is None:
            import docker  # imported here so tests and fake-sandbox runs do not need the package

            client = docker.from_env()
        self._docker = client

    def start(self, spec: SandboxSpec) -> None:
        lim = self._limits
        try:
            self._docker.containers.run(
                self._image,
                name=container_name(spec.run_id),
                detach=True,
                auto_remove=True,
                environment=spec.env,
                labels={**spec.labels, "bsi.role": "agent-run"},
                network=self._network,
                user="1000:1000",
                read_only=True,
                tmpfs={"/tmp": f"rw,noexec,nosuid,size={lim.tmp_size}",
                       "/workspace": f"rw,nosuid,size={lim.workspace_size}"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                mem_limit=lim.memory,
                memswap_limit=lim.memory,  # no swap on top of the memory limit
                nano_cpus=int(lim.cpus * 1_000_000_000),
                pids_limit=lim.pids,
                init=True,
            )
        except Exception as e:  # docker.errors.* : image missing, daemon down, name taken...
            raise SandboxError(f"{type(e).__name__}: {e}") from e

    def stop(self, run_id: str) -> None:
        try:
            self._docker.containers.get(container_name(run_id)).stop(timeout=10)  # auto_remove deletes it
        except Exception as e:
            if type(e).__name__ == "NotFound":  # already gone (exited and auto-removed): fine
                return
            raise SandboxError(f"{type(e).__name__}: {e}") from e
