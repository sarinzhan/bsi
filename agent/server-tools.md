# Server tools (MCP, served by platform-api at /mcp/)

Implementation: `services/platform-api/src/platform_api/tools/` (see `docs/architecture.md`).

The agent never gets SSH. It calls these tools; the platform checks the
arguments, asks the developer for approval, runs a **fixed** command over SSH
with its own key, masks secrets and returns the output.

## Allowed tools per server

Each server has a **list of allowed tools**, set by a platform admin in the server
settings (platform-api's servers module; seeded from `services/platform-api/config/servers.yaml`).
Missing or empty list = the agent can do nothing on that server.

Typical lists:

| server | allowed tools |
|---|---|
| dev you can rebuild | everything, including `ssh_exec` |
| dev | read + write tools |
| stage | read tools + `compose_restart` |
| prod | `docker_ps`, `docker_logs`, `docker_stats` |

- A tool not on the list is rejected **before** the developer is asked; the error lists
  the allowed tools.
- `ssh_exec` is never allowed on prod: the platform refuses to save it.
- Every change needs a reason and is logged (who, added, removed, why, when).
- A change applies to the next call, including calls already waiting for approval.

Rules the platform enforces for every tool:
- `server` and `service` must belong to the chat's system and environment
- paths must be inside `/opt/bsi/<system>/<env>/` (no `..`, no symlinks out,
  no keys/certificates: `*.pem`, `*.key`, `id_*`)
- output is capped (500 lines / 200 KB) and secrets are masked
- every call goes to the audit log: who approved, exact command, time, result
- no answer to an approval in 5 minutes = denied

## Read tools — approval once per server per chat

| tool | input | platform runs |
|---|---|---|
| `folder_list` | `server, path` | `ls -la <path>` |
| `file_read` | `server, path, from_line?, lines?` | `sed -n '<from>,<to>p' <path>` (`.env` files: names only) |
| `docker_ps` | `server` | `docker ps -a --filter label=com.docker.compose.project=<system>-<env> --format '{{json .}}'` |
| `docker_logs` | `server, service, since?, tail?` | `docker logs --since <since≤24h> --tail <≤500> <container>` |
| `docker_inspect` | `server, service` | `docker inspect <container>` with env values removed |
| `docker_stats` | `server` | `docker stats --no-stream --format '{{json .}}'` (system containers only) |

## Write tools — approval EVERY time, with a one-line reason

| tool | input | platform runs |
|---|---|---|
| `file_write` | `server, path, content, reason` | writes the file atomically, keeps a `.bak` copy |
| `docker_run` | `server, image, command?, env?, reason` | `docker run --rm --label bsi.system=<system> --label bsi.adhoc=true --network <system>-<env> <image> <command>` |
| `compose_run` | `server, service, command, reason` | `docker compose -p <system>-<env> run --rm <service> <command>` |
| `compose_restart` | `server, service, reason` | `docker compose -p <system>-<env> restart <service>` |

### Guardrails for the write tools

`file_write`
- only inside the system folder; never `.env` values, keys or certificates
- after the write, the platform shows the diff in the chat and marks the file as
  **drift** (server differs from git). The agent must commit the same change
  to `platform/` in git in the same run — otherwise the next deploy overwrites it.

`docker_run`
- images only from the company registry (`registry/<system>/…`) or an allowlist
  (`postgres`, `busybox`, `curlimages/curl`…), never `latest`
- always `--rm` (one-off task), always the system network and labels
- rejected flags: `--privileged`, `--network host`, `--pid host`, `-v /…` outside
  the system folder, `--cap-add`, `-d` (long-running containers belong in compose)
- shown on the Running page as "ad-hoc" until it exits

`compose_run`
- one-off commands in a service's context, e.g. a DB migration or a CLI task
- same flag rules as `docker_run`

## Any command — only where `ssh_exec` is in the server's list

| tool | input | platform runs |
|---|---|---|
| `ssh_exec` | `server, command, reason, timeout_s≤300` | the command as-is, as the `deploy` user, over the platform's SSH key |

- approval **every time**; the card shows the exact command, not a summary
- the key still never reaches the agent; output capped and masked like the other tools
- after the run, the platform records the commands in History as an
  "Infrastructure · manual change" entry, so changes outside git stay visible
- `drift_check` runs after every `ssh_exec` that changed files

## Approval cards (what the developer sees)

    The agent wants to read dev-docker-01 (logs, files, container state)
    for this chat.
    [Allow for this chat]  [Allow once]  [Deny]

    The agent wants to WRITE platform/infra/env/orders-service.env.example
    on dev-docker-01. Reason: "add missing ORDER_TTL variable name".
    [show diff]  [Allow]  [Deny]

    The agent wants to run on dev-docker-02 (full access):
      sudo journalctl -u docker --since "10 min ago" | tail -100
    Reason: "containers restart every minute, checking the Docker daemon".
    [Allow]  [Deny]

    The agent wants to RUN registry/superapp/orders-service:0.1.2
    "java -jar app.jar --migrate-only" on dev-docker-01.
    [Allow]  [Deny]
