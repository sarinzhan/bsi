# superAI backend architecture

Two deployable services. Inside each one: **modules**, one per domain. Every module is
hexagonal and talks to other modules only through ports.

```
            web (React)
                │  REST + SSE
                ▼
┌──────────────────────────── platform-api (modular monolith) ───────────────────────────┐
│  chat      agent      approval      project      history      skills                    │
└─────────────┬──────────────▲───────────────────────────────────────────────────────────┘
              │ starts runs  │ POST /internal/approvals, POST /internal/runs/resolve
              ▼              │
   agent sandbox ── MCP ──► server-tools (separate service, holds the SSH key)
   (claude -p)               servers      tools      ──SSH──►  Docker servers
```

Why only two services: `server-tools` is split out because it is the **only** process with the
SSH key and needs its own deploy, network rules and audit. Everything else stays one process
(a modular monolith). A module can become a service later without changing its code, because it
already talks only through ports.

## Module layout (the same in every module)

```
<module>/
  domain/          entities, value objects, rules. Pure Python: no frameworks, no I/O
  ports/
    provided.py    what the module offers (use case interfaces + plain DTOs)
    required.py    what it needs (repositories, gateways), as Protocols
  application/     use cases: implement provided ports, use required ports
  adapters/
    inbound/       HTTP routes, MCP server: call provided ports
    outbound/      SSH, HTTP clients, DB, files: implement required ports
  __init__.py      create_<module>_module(required ports...) -> provided ports
```

Rules (checked by `lint-imports` in CI, see `[tool.importlinter]` in each pyproject):
1. Layers: `adapters → application → ports → domain`, never upwards.
2. Domain imports no frameworks (mcp, starlette, fastapi, asyncssh, httpx, yaml, sqlalchemy).
   Application and ports import no web framework and no database library either: FastAPI routes are
   inbound adapters, SQLAlchemy repositories are outbound adapters.
3. Module A sees module B only through `B.ports.provided`. No shared tables, no shared domain classes.
4. Wiring happens in one place per service: `main.py` (composition root). No DI framework.

## server-tools (done)

| module | provided | required |
|---|---|---|
| **servers**: which machines exist, env, systems, the tools the agent may use on each | `ServerCatalog` (read), `ServerSettings.change_allowed_tools / access_history` (write) | `ServerRepository`, `AccessChangeLog` (Postgres; YAML/JSONL without a database), `KnownTools` (wired in `known_tools.py` from the tools catalog) |
| **tools**: the 11 server tools, argument rules, fixed commands, masking | `CallTool`, `ListTools` | `Targets` (over `ServerCatalog`), `Approvals` (platform-api), `Executor` (SSH), `AuditLog` (Postgres, append-only; JSONL without a database), `RunAuthority` (platform-api) |

Use case `CallTool`: validate → ask the developer → run over SSH → mask + cap → audit → answer.
No answer in 5 minutes, or platform-api unreachable → **denied** (never allowed by default).

Inbound: MCP at `/mcp` (streamable HTTP; the agent sends `Authorization: Bearer <run token>`),
and `GET /api/tools` for the web app.

## platform-api (done: access, agent)

| module | owns | provided | required |
|---|---|---|---|
| **access** (done) | users, roles (developer, devops, admin), permissions — see `docs/roles.md` | `AccessCheck.can / can_approve_tool / who_can`, `UserAdmin` (Users page) | `UserRepository` (Postgres; users.yaml without a database; SSO later), `RoleChangeLog` (Postgres, append-only) |
| **chat** | chats, messages, the event stream | `SendMessage`, `GetChat`, `ListChats`, `ChatEvents` (subscribe) | `ChatRepository`, `AgentRuns` (agent.provided) |
| **agent** (done; events to chat: later) | runs (one container each), run tokens (hash only), deadlines | `Runs.start / cancel / get`, `RunTokens.resolve / finish`, `RunReaper` | `RunRepository` (Postgres; memory without a database), `Sandbox` (Docker; fake in dev), `AccessCheck` (access.provided), `ChatEventSink` (chat.provided, later) |
| **approval** | pending approvals, "allow for this chat" grants | `RequestApproval` (blocks), `AnswerApproval` | `ApprovalRepository`, `ChatEventSink` (shows the card) |
| **project** | projects, repos, files the agent changed | `LinkProject`, `GetProject`, `ListProjects` | `ProjectRepository`, `GitLab` |
| **history** | decision log (ADRs), versions | `RecordDecision`, `ListDecisions` | `AdrStore` (git: `platform/docs/adr/`) |
| **skills** | skill files and their usage | `ListSkills`, `GetSkill` | `SkillStore` (git) |

The **approval** module asks `access.can_approve_tool(user, kind)` before accepting an answer: reads by
developer/devops/admin, writes and any command by devops/admin only. It also decides "once per server per chat" for read tools: when a grant exists,
it answers immediately and still shows a small "auto-approved" line in the chat.
`server-tools` always asks, so the rule lives in one place.

### Agent runs and their containers

```
message ─► agent.start(user, chat, system, env)
             ├─ access.can(user, "chat.use")?
             ├─ new run + random token; Postgres keeps sha256(token) only; deadline = now + 30 min
             └─ Sandbox.start: container superai-<run id>, env SUPERAI_RUN_TOKEN, SUPERAI_MCP_URL, ...
container ─MCP, Bearer <token>─► server-tools ─POST /internal/runs/resolve─► platform-api
             → {runId, chatId, system, env, requestedBy}: the token decides system and env, not the agent
container ─POST /runner/finish (Bearer <token>)─► run ends, token dies, container stopped
every 60 s: reaper stops containers past their deadline (the token is already dead at the deadline)
```

The container is untrusted (later it runs code the agent wrote), so it holds nothing valuable: only the token.
`DockerSandbox` runs it as a non-root user, read-only root filesystem, no capabilities, no new privileges,
CPU/memory/process limits, removed on exit, no Docker socket, no host folders, on the network
`superai-agent-sandbox`. Create that network with `internal: true` (no internet) and attach only
server-tools and platform-api to it. Model calls will go through a proxy in platform-api, so the
Anthropic key never enters the container (next step).

## Data

Each service has its **own** Postgres database and login (`server_tools`, `platform`); neither can read the
other's. Inside a service, each module owns its tables: its SQLAlchemy ORM models live in the module's
outbound adapters and never leave them (repositories convert rows to domain objects). Schema changes are
Alembic migrations in `src/<package>/migrations/versions/`, applied on start (`alembic upgrade head`).
History tables (`access_changes`, `audit_log`, `role_changes`) are append-only: a trigger rejects
UPDATE, DELETE and TRUNCATE. `config/*.yaml` seeds an empty database once.

## Contracts between the services

```
POST /internal/approvals          (server-tools → platform-api, long request ≤ 5 min)
  {runId, chatId, tool, kind, server, command, reason} → {allowed, by}
POST /internal/runs/resolve       (server-tools → platform-api)
  {token} → {runId, chatId, system, env, requestedBy} | 404
  (the token goes in the body, never in the URL: URLs end up in access logs)
header X-Service-Token: <shared secret from Vault>

POST /runner/finish               (agent container → platform-api)
  {outcome: finished | failed, error?}       header Authorization: Bearer <run token>
```
