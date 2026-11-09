# superAI

AI-driven platform: a developer describes what they need in a chat, the agent
decides what to create (services, databases, brokers), writes readable code and
infrastructure files (Compose / Kubernetes YAML), and the platform applies them
to servers that humans provide.

## Layout

- `web/` — React frontend (Vite + TypeScript). Uses a mock API for now.
- `services/platform-api/` — main backend (users and roles today; chat, agent, approvals next).
- `services/server-tools/` — the only service with the SSH key; serves server tools to the agent over MCP.
- `infra/postgres/` — local Postgres setup (one database and login per service).
- `docs/` — architecture and roles.

## Database (Postgres)

    docker compose up -d postgres

| service | `SUPERAI_DATABASE_URL` (local dev) |
|---|---|
| server-tools | `postgresql://server_tools:dev-server-tools@localhost:5432/server_tools` |
| platform-api | `postgresql://platform:dev-platform@localhost:5432/platform` |

With the variable set, a service applies its migrations (`src/<package>/migrations/*.sql`) on start and,
if the database is empty, imports `config/*.yaml` once. Without it, the service uses the YAML and JSONL
files as before (handy for quick runs). In prod the variable is required.

Postgres tests run when `SUPERAI_TEST_DATABASE_URL` is set (see `tests/conftest.py` in each service),
otherwise they are skipped.

## Run the frontend

    cd web
    npm install
    npm run dev      # http://localhost:5173
