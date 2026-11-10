# BSI architecture

Developers ask an AI agent about their servers in a chat. The agent looks at logs, containers and files
through a fixed set of server tools; a person approves each tool call in the chat, and every call is recorded.

## Processes

```
 browser ──HTTPS──► web (nginx + React)  ── /api/* ──►  platform-api  ──SSH──► target servers
                                                          │  ▲   ▲
                                         starts one       │  │   │ /runner/*  (run token)
                                         container/run    ▼  │   │ /mcp/      (run token)
                                                     agent container (agent-runner)
                                                     Claude loop, holds only its run token (+ API key*)

 Postgres: database "platform"                               * no model proxy yet
```

| process | holds | built with |
|---|---|---|
| **web** | nothing secret | React, TypeScript, Vite; nginx serves it and forwards `/api` |
| **platform-api** | DB password, **the SSH key**, Anthropic API key* | Python, FastAPI, SQLAlchemy, Alembic, MCP server, asyncssh |
| **agent-runner** | its run token (+ API key*) | Python, Anthropic SDK, MCP client. One container per agent run |
| **Postgres** | all data | Postgres 17, one database, one login |

### Why one process (and what it costs)

The server tools used to be a separate service (agent-tools) so the SSH key lived apart from the web API.
They were merged into platform-api to keep the system simple: no internal HTTP calls, no service token,
one database. The cost: a security bug anywhere in platform-api can expose the SSH key. Mitigations to add
before connecting prod servers: short-lived SSH certificates (e.g. Vault SSH engine) instead of a long-lived
key, and keeping platform-api's dependencies small and patched. The `tools` module still reaches other
modules only through their `schemas.py`, so it can be split out again by swapping its integrations.

## Inside platform-api: modules and layers

| module | owns |
|---|---|
| **access** | users, roles (developer, devops, admin), permissions — see `docs/roles.md` |
| **servers** | machines, env, systems, the tools the agent may use on each, access history |
| **agent** | agent runs: run tokens (hash only), containers, deadlines |
| **chat** | chats, messages, live event stream (SSE) in the web app's `AgentEvent` format |
| **approval** | approval cards, "allow reads for this chat", who may approve what |
| **tools** | the 11 server tools: argument rules, fixed commands, SSH, masking, audit log; MCP endpoint `/mcp/` |

Every module has the same layers:

```
<module>/
  router.py        HTTP routes (MCP for tools): request in -> service -> response out
  service.py       business logic
  schemas.py       what the service returns to callers, and its errors (other modules import only this)
  interfaces.py    what the service needs: repositories, sandbox, SSH...
  models.py        entities and rules, plain Python
  repositories/    storage: postgres.py, and memory.py or files.py for running without a database
  integrations/    everything else outside: Docker, SSH, other modules
  __init__.py      create_<module>_module(...): builds the module
main.py            builds all modules and the app;  wiring.py: glue between modules that must not import each other
```

```
router ──► service ──► interfaces / schemas ──► models
               ▲
repositories, integrations implement interfaces
```

Rules, checked by `lint-imports` (see `[tool.importlinter]` in `services/platform-api/pyproject.toml`):
1. Inside a module, imports only go down the layers: a service never imports a router, a repository or an
   integration; models import nothing else.
2. Models, services, schemas and interfaces import no framework (FastAPI, SQLAlchemy, Docker, MCP, SSH...).
3. A module uses another module only through its `schemas.py`:
   `servers, agent -> access`; `chat -> access, agent`; `approval -> access, chat`;
   `tools -> servers, approval, agent`. `agent` tells `chat` that a run ended through its `RunListener`
   interface, connected in `wiring.py`; `servers` learns which tools exist the same way.

## Data

One Postgres database, `platform`. Each module owns its tables; no foreign keys between modules.

| module | tables |
|---|---|
| access | `users`, `role_changes` (append-only) |
| servers | `servers` (DB refuses `ssh_exec` on prod), `access_changes` (append-only) |
| agent | `runs` (token hash only) |
| chat | `chats`, `chat_messages` (upserted by id), `chat_events` (append-only) |
| approval | `approvals`, `approval_read_grants` |
| tools | `audit_log` (append-only: every tool call, who approved it, result) |

Schema changes are Alembic migrations (`src/platform_api/migrations/versions/`), applied on start.
Append-only tables have a trigger that rejects UPDATE, DELETE and TRUNCATE. `config/users.yaml` and
`config/servers.yaml` seed an empty database once. Without `BSI_DATABASE_URL` (dev, tests) the modules
use files and memory instead.

## HTTP surface

| caller | routes | auth |
|---|---|---|
| browser | `/api/me`, `/api/users…`, `/api/roles`, `/api/servers…`, `/api/servers/tools`, `/api/chats…`, `GET /api/chats/{id}/events` (SSE), `POST /api/chats/{id}/tool-calls/{call}/answer`, `/api/runs…` | user (dev: `X-User-Id`; prod: company SSO, not built) |
| agent container | `GET /runner/context`, `POST /runner/events`, `POST /runner/finish`, MCP at `/mcp/` | `Bearer <run token>` |

nginx routes only `/` and `/api/*` from outside; `/runner` and `/mcp` are reached by agent containers on the
private network.

## One message, end to end

```
 1. browser   POST /api/chats/c1/messages "why does orders keep restarting?"
 2. chat      user message event -> agent.start
 3. agent     checks the user, run + token (hash stored), starts a container: token, MCP URL, model
 4. browser   GET /api/chats/c1/events  <- live: user message, status "working", ...
 5. runner    GET /runner/context -> system, env, conversation; asks Claude with the 11 tools
 6. Claude    "call docker_logs(server=dev-docker-01, service=orders-service)"
 7. runner    MCP /mcp/ with its run token
 8. tools     token -> run (agent); server + allowed tools (servers); argument rules; fixed command
              -> approval: card "waiting" in the chat
 9. person    clicks "Allow for this chat" (approval checks their role may approve reads)
10. tools     SSH `docker logs --tail 200 ...`, mask secrets, cap output, audit row -> card "done" + output
11. runner    gives the logs to Claude -> more tools (each through 8) -> answer: POST /runner/events, /runner/finish
12. agent     run finished, token dead, container stopped -> chat status "waiting"
```

When in doubt the answer is no: a tool not allowed on the server is rejected before anyone is asked; no
answer in 5 minutes is a denial; a run past its deadline (30 min) loses its token and its container.

## Agent containers

`agent/integrations/docker_sandbox.py` runs each one as a non-root user with a read-only root filesystem, no
capabilities, no privilege escalation, CPU/memory/process limits, no Docker socket and no host folders,
removed on exit, on the network `bsi-agent-sandbox` (reaches platform-api only). Dev can run agents as
local processes instead (`BSI_SANDBOX=process`, no isolation).

**No model proxy yet**: the Anthropic API key is passed into each container and the sandbox network allows
egress to `api.anthropic.com`. Code the agent runs in its container could read the key. Fine for a pilot with
read-only tools; add a model proxy in platform-api before the agent writes and runs code.

## Security layers

1. Network: only nginx is public; agent containers reach only platform-api (+ the Anthropic API for now).
2. Identity: users by role (`access`); agent containers by short-lived run tokens bound to one chat, system
   and environment.
3. Per-server allowed tools set by DevOps (`servers`); `ssh_exec` never on prod, in code and in the database.
4. Fixed commands: the agent only fills in checked, quoted values; paths stay inside `/opt/bsi/<system>/<env>/`.
5. A person approves: reads once per server per chat, writes and `ssh_exec` every time by devops/admin.
6. Output: secrets masked, size capped. Records: append-only audit log, access and role history.

Known gaps: SSH key in the main process (see "Why one process"), API key in containers (no model proxy),
JSON-style secrets not masked yet, no SSO, the app's DB login could drop the append-only triggers.

## Deployment

Local: `docker compose up` (dev mode); `docker-compose.agents.yml` adds real agent containers.
Production (two VMs): `deploy/README.md`.
