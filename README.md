# BSI

AI-driven platform: a developer describes what they need in a chat, the agent
decides what to create (services, databases, brokers), writes readable code and
infrastructure files (Compose / Kubernetes YAML), and the platform applies them
to servers that humans provide.

## Layout

- `web/` — React frontend (Vite + TypeScript). Uses a mock API for now.
- `services/platform-api/` — main backend: users and roles, agent runs (one container each), servers and
  the tools allowed on each. Chat and approvals next.
- `services/agent-runner/` — the agent loop (Anthropic SDK + MCP) inside each agent container.
- `infra/postgres/` — local Postgres setup (one database and login per service).
- `deploy/` — production: bsi-app compose, bsi-runner setup.
- `docs/` — architecture and roles.

## Run everything (Docker)

    cp .env.example .env
    docker compose up -d --build
    open http://localhost:8080          # web app (API docs: http://localhost:8080/docs)

Postgres, platform-api (MCP at http://localhost:8000/mcp/, dev token `dev-superapp-dev`)
and the web app, in dev mode. Production: [deploy/README.md](deploy/README.md).

**With a real agent** (one container per message; set `ANTHROPIC_API_KEY` in `.env`, or
`BSI_LLM=scripted` to try the whole flow without a model):

    docker compose -f docker-compose.yml -f docker-compose.agents.yml --profile build build agent-runner
    docker compose -f docker-compose.yml -f docker-compose.agents.yml up -d --build

**Without Docker** (each agent runs as a local process, no isolation, dev only): start platform-api with
`BSI_SANDBOX=process` and `cd web && npm run dev` (it forwards `/api` to localhost:8000).
`VITE_API=mock npm run dev` runs the UI on mock data, without any backend.

## Database (Postgres)

Only the database, e.g. to run the services from source with `uv run`:

    docker compose up -d postgres

| service | `BSI_DATABASE_URL` (local dev) |
|---|---|
| platform-api | `postgresql://platform:dev-platform@localhost:5432/platform` |

With the variable set, a service runs `alembic upgrade head` on start and, if the database is empty,
imports `config/*.yaml` once. Without it, the service uses the YAML and JSONL
files as before (handy for quick runs). In prod the variable is required.

Stack: **FastAPI** (API docs at `/docs`), **SQLAlchemy 2** ORM, **Alembic** migrations. After changing
an ORM model (in a module's `repositories/postgres.py`), from `services/platform-api`:

    uv run alembic revision --autogenerate -m "what changed"   # read and fix the generated file
    uv run alembic check                                       # models and migrations match?

Postgres tests run when `BSI_TEST_DATABASE_URL` is set (see `tests/conftest.py` in each service),
otherwise they are skipped.

## Run the frontend

    cd web
    npm install
    npm run dev      # http://localhost:5173
