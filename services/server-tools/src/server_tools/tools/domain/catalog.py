"""The tool catalog: for each tool, its kind and the FIXED command it builds from validated arguments.

Every value that reaches the shell goes through shlex.quote, so the agent can never add flags
(--privileged, -v /:/host, --network host ...): it only fills in validated values.
"""

from __future__ import annotations

from dataclasses import dataclass
from shlex import quote as q
from typing import Any, Callable

from server_tools.tools.domain import masking, rules
from server_tools.tools.domain.model import Command, RunContext, Target, ToolKind, ToolRejected


@dataclass(frozen=True)
class ImagePolicy:
    registry: str = "registry"
    allowlist: frozenset[str] = frozenset({"postgres", "busybox", "curlimages/curl", "redis", "alpine"})


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: ToolKind
    summary: str  # one line, shown to the agent and on the Servers page
    params: str  # human-readable input list
    build: Callable[[dict[str, Any], RunContext, Target, ImagePolicy], Command]
    post: Callable[[str, dict[str, Any]], str] | None = None  # extra masking of the output


# ---- shell fragments (kept short so the approval card stays readable) ----


def _guard(path: str, root: str) -> str:
    """Resolve symlinks on the server and stop if the real path leaves the system folder."""
    return (
        f"p=$(realpath -m -- {q(path)}) && case \"$p\" in {q(root)}|{q(root)}/*) ;; "
        f"*) echo 'path leaves the system folder' >&2; exit 3;; esac"
    )


def _container(ctx: RunContext, service: str) -> str:
    return (
        f"c=$(docker ps -aq --filter label=com.docker.compose.project={q(ctx.compose_project)} "
        f"--filter label=com.docker.compose.service={q(service)} | head -n1); "
        f"[ -n \"$c\" ] || {{ echo 'no container for {service}' >&2; exit 4; }}"
    )


def _join(values: list[str]) -> str:
    return " ".join(q(v) for v in values)


# ---- read tools ----


def _folder_list(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    p = rules.path(a.get("path") or ".", ctx.root)
    return Command(f"{_guard(p, ctx.root)} && ls -la -- \"$p\"")


def _file_read(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    p = rules.path(a["path"], ctx.root)
    start = int(a.get("from_line") or 1)
    count = int(a.get("lines") or 200)
    if start < 1 or not 1 <= count <= 500:
        raise ToolRejected("from_line >= 1 and lines 1..500")
    return Command(f"{_guard(p, ctx.root)} && sed -n '{start},{start + count - 1}p' -- \"$p\"")


def _file_read_post(text: str, a: dict) -> str:
    return masking.env_names_only(text) if rules.is_env_file(a["path"]) else text


def _docker_ps(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    return Command(
        f"docker ps -a --filter label=com.docker.compose.project={q(ctx.compose_project)} "
        "--format '{{json .}}'"
    )


def _docker_logs(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    svc = rules.service(a["service"])
    return Command(
        f"{_container(ctx, svc)}; docker logs --since {q(rules.since(a.get('since')))} "
        f"--tail {rules.tail(a.get('tail'))} \"$c\" 2>&1",
        keep="tail",
    )


def _docker_inspect(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    svc = rules.service(a["service"])
    return Command(f"{_container(ctx, svc)}; docker inspect \"$c\"")


def _docker_stats(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    return Command(
        f"ids=$(docker ps -q --filter label=com.docker.compose.project={q(ctx.compose_project)}); "
        "if [ -n \"$ids\" ]; then docker stats --no-stream --format '{{json .}}' $ids; "
        "else echo 'no running containers'; fi"
    )


# ---- write tools ----


def _file_write(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    rules.reason(a.get("reason"))
    p = rules.path(a["path"], ctx.root)
    if rules.is_env_file(p):
        raise ToolRejected(".env files hold secrets: change them in Vault, not with file_write")
    data = rules.file_content(a["content"])
    return Command(
        f"{_guard(p, ctx.root)} && mkdir -p -- \"$(dirname -- \"$p\")\" && "
        f"{{ [ ! -f \"$p\" ] || cp -p -- \"$p\" \"$p.bak\"; }} && "
        f"cat > \"$p.superai-tmp\" && mv -- \"$p.superai-tmp\" \"$p\" && echo \"written $p ({len(data)} bytes)\"",
        stdin=data,
    )


def _docker_run(a: dict, ctx: RunContext, t: Target, images: ImagePolicy) -> Command:
    rules.reason(a.get("reason"))
    img = rules.image(a["image"], ctx.system, images.registry, images.allowlist)
    env = "".join(f" -e {q(k + '=' + v)}" for k, v in rules.env_vars(a.get("env")).items())
    return Command(
        f"docker run --rm --network {q(ctx.compose_project)} --label superai.system={q(ctx.system)} "
        f"--label superai.adhoc=true{env} {q(img)} {_join(rules.args(a.get('args')))}".rstrip(),
        timeout_s=300,
    )


def _compose_run(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    rules.reason(a.get("reason"))
    svc = rules.service(a["service"])
    return Command(
        f"cd {q(ctx.root)} && docker compose -p {q(ctx.compose_project)} run --rm {q(svc)} "
        f"{_join(rules.args(a.get('args')))}".rstrip(),
        timeout_s=300,
    )


def _compose_restart(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    rules.reason(a.get("reason"))
    svc = rules.service(a["service"])
    return Command(f"cd {q(ctx.root)} && docker compose -p {q(ctx.compose_project)} restart {q(svc)}", timeout_s=120)


# ---- full access ----


def _ssh_exec(a: dict, ctx: RunContext, t: Target, _: ImagePolicy) -> Command:
    rules.reason(a.get("reason"))
    command = (a.get("command") or "").strip()
    if not command or "\x00" in command or len(command) > 4000:
        raise ToolRejected("command must be 1..4000 characters")
    timeout = rules.free_timeout(a.get("timeout_s"))
    return Command(f"timeout {timeout} bash -c {q(command)}", timeout_s=timeout + 5)


TOOLS: dict[str, ToolSpec] = {
    s.name: s
    for s in [
        ToolSpec("folder_list", ToolKind.READ, "List a folder inside the system folder.", "server, path?", _folder_list),
        ToolSpec("file_read", ToolKind.READ, "Read lines of a file (.env: names only).",
                 "server, path, from_line?, lines?≤500", _file_read, _file_read_post),
        ToolSpec("docker_ps", ToolKind.READ, "Containers of this system and environment.", "server", _docker_ps),
        ToolSpec("docker_logs", ToolKind.READ, "Logs of a compose service.", "server, service, since?≤24h, tail?≤500",
                 _docker_logs),
        ToolSpec("docker_inspect", ToolKind.READ, "Container details, env values removed.", "server, service",
                 _docker_inspect, lambda text, a: masking.strip_inspect_env(text)),
        ToolSpec("docker_stats", ToolKind.READ, "CPU and memory of this system's containers.", "server", _docker_stats),
        ToolSpec("file_write", ToolKind.WRITE, "Write a file atomically, keep a .bak copy. Commit the same change to git.",
                 "server, path, content, reason", _file_write),
        ToolSpec("docker_run", ToolKind.WRITE, "Run a one-off container (--rm) on the system network.",
                 "server, image, args?, env?, reason", _docker_run),
        ToolSpec("compose_run", ToolKind.WRITE, "Run a one-off command in a compose service (e.g. a migration).",
                 "server, service, args, reason", _compose_run),
        ToolSpec("compose_restart", ToolKind.WRITE, "Restart a compose service.", "server, service, reason",
                 _compose_restart),
        ToolSpec("ssh_exec", ToolKind.FULL, "Any shell command. Never on prod; use only when the other tools cannot answer.",
                 "server, command, reason, timeout_s?≤300", _ssh_exec),
    ]
}


def display(cmd: Command, tool: str, a: dict[str, Any]) -> str:
    """What the approval card shows. Secrets in the command (env values) are masked."""
    shown = a.get("command", cmd.script) if tool == "ssh_exec" else cmd.script
    return masking.mask(shown)
