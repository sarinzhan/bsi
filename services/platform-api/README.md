# platform-api

The BSI backend, one process: the web API, agent runs, and the server tools agents call over MCP.
It holds the SSH key. Architecture: modules with simple layers, see docs/architecture.md.
Architecture: [../../docs/architecture.md](../../docs/architecture.md). Roles: [../../docs/roles.md](../../docs/roles.md).

```
src/platform_api/
  access/    users, roles, permissions
  servers/   machines, allowed tools per server, access history (config/servers.yaml seeds it)
  agent/     agent runs (one container each), run tokens, deadlines
  chat/      chats, messages, live event stream (SSE) in the web app's AgentEvent format
  approval/  approval cards, "allow reads for this chat", who may approve what
  tools/     the 11 server tools: MCP at /mcp/, argument rules, SSH, masking, audit log
  wiring.py  glue between modules that must not import each other
  main.py    builds everything
  migrations/  Alembic

each module:  router.py -> service.py -> repositories/ + integrations/ (through interfaces.py) -> models.py
              schemas.py: what other modules may import
```

## Run (dev mode: no database needed, fake sandbox starts no containers)

```bash
uv sync
uv run uvicorn platform_api.main:app --port 8000
open http://localhost:8000/docs
curl -X POST localhost:8000/api/runs -H 'X-User-Id: sarinzha' -H 'Content-Type: application/json' \
     -d '{"chatId": "c1", "system": "superapp", "env": "dev"}'
```

## Check

```bash
uv run pytest        # BSI_TEST_DATABASE_URL=... adds the Postgres tests (see tests/conftest.py)
uv run lint-imports  # architecture rules
uv run alembic check # ORM models and migrations match (needs BSI_DATABASE_URL)
```

## Settings

| variable | |
|---|---|
| `BSI_MODE` | `dev` (default) or `prod` |
| `BSI_DATABASE_URL` | Postgres. Required in prod; without it: YAML/JSONL files and runs in memory |
| `BSI_SANDBOX` | `docker` (default in prod), `fake` (default in dev: starts nothing) or `process` (dev only: runs agent-runner as a local process, no isolation) |
| `BSI_RUNNER_COMMAND` | `process` sandbox: command to start agent-runner (default `uv run --project ../agent-runner python -m agent_runner`) |
| `BSI_LLM`, `BSI_MODEL`, `BSI_EFFORT` | passed to agent containers: `anthropic` or `scripted` (no model), default `claude-opus-5-5`, `high` |
| `ANTHROPIC_API_KEY` | passed into agent containers (no model proxy yet) |
| `BSI_AGENT_IMAGE` | agent container image with a pinned tag, e.g. `registry/bsi/agent-runner:0.1.0` |
| `BSI_SANDBOX_NETWORK` | Docker network for agent containers (default `bsi-agent-sandbox`, `internal: true`) |
| `BSI_RUN_MCP_URL`, `BSI_RUN_PLATFORM_URL` | how agent containers reach platform-api (defaults `http://platform-api:8000/mcp/`, `http://platform-api:8000`) |
| `BSI_RUN_TTL_S` | run deadline in seconds (default 1800) |
| `BSI_SSH_KEY`, `BSI_KNOWN_HOSTS` | the deploy user's private key and pinned host keys (prod, or dev with `BSI_EXECUTOR=ssh`) |
| `BSI_EXECUTOR` | dev: `fake` (default) or `ssh` to try one real server |
| `BSI_APPROVALS` | dev: cards in the chat (default) or `auto` (answered automatically) |
| `BSI_DEV_TOKENS` | dev: `on` (default) also accepts `dev-<system>-<env>` at /mcp/ for your own MCP client |
| `BSI_MCP_ALLOWED_HOSTS` | Host headers /mcp/ accepts (default `localhost:*,127.0.0.1:*,platform-api:*`) |
| `BSI_REGISTRY`, `BSI_AUDIT_FILE` | image registry allowed for docker_run; audit file without a database |
| `BSI_USERS_FILE`, `BSI_SERVERS_FILE` | optional; the YAML files seed an empty database |
| `BSI_ROLE_LOG`, `BSI_ACCESS_LOG` | optional; used only without a database |
