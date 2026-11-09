# platform-api

Main backend of superAI: users and roles (`access`), agent runs and their containers (`agent`).
Architecture: [../../docs/architecture.md](../../docs/architecture.md). Roles: [../../docs/roles.md](../../docs/roles.md).

```
src/platform_api/
  access/    module: users, roles, permissions
  agent/     module: runs (one container each), run tokens, deadlines
  migrations/  Alembic
  main.py    composition root
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
uv run pytest        # SUPERAI_TEST_DATABASE_URL=... adds the Postgres tests (see tests/conftest.py)
uv run lint-imports  # architecture rules
uv run alembic check # ORM models and migrations match (needs SUPERAI_DATABASE_URL)
```

## Settings

| variable | |
|---|---|
| `SUPERAI_MODE` | `dev` (default) or `prod` |
| `SUPERAI_DATABASE_URL` | Postgres. Required in prod; without it: YAML/JSONL files and runs in memory |
| `SUPERAI_SERVICE_TOKEN` | shared secret with server-tools (Vault). Required in prod; in dev `/internal` is open without it |
| `SUPERAI_SANDBOX` | `docker` (default in prod) or `fake` (default in dev) |
| `SUPERAI_AGENT_IMAGE` | agent container image with a pinned tag, e.g. `registry/superai/agent-runner:0.1.0` |
| `SUPERAI_SANDBOX_NETWORK` | Docker network for agent containers (default `superai-agent-sandbox`, `internal: true`) |
| `SUPERAI_RUN_MCP_URL`, `SUPERAI_RUN_PLATFORM_URL` | how the container reaches server-tools and platform-api (defaults `http://server-tools:8100/mcp/`, `http://platform-api:8000`) |
| `SUPERAI_RUN_TTL_S` | run deadline in seconds (default 1800) |
| `SUPERAI_USERS_FILE`, `SUPERAI_ROLE_LOG` | optional; the YAML seeds an empty database |
