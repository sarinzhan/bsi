# server-tools

The only superAI service that holds the SSH key. Serves the server tools to the agent over MCP.
Architecture: [../../docs/architecture.md](../../docs/architecture.md). Tool rules: [../../agent/server-tools.md](../../agent/server-tools.md).

```
src/server_tools/
  servers/   module: servers and the tools the agent may use on each (config/servers.yaml)
  tools/     module: the 11 tools, argument rules, masking, the CallTool use case
  main.py    composition root
```

## Run (dev mode: fake SSH, approvals answered automatically)

```bash
uv sync
uv run uvicorn server_tools.main:app --port 8100
curl localhost:8100/api/tools
open http://localhost:8100/docs   # API docs (FastAPI)
```

MCP endpoint: `http://localhost:8100/mcp/`, header `Authorization: Bearer dev-superapp-dev`
(dev tokens look like `dev-<system>-<env>`).

`SUPERAI_DEV_APPROVE=deny` makes every approval a denial.

## Server settings API (used by the server settings page)

```
GET /api/servers
PUT /api/servers/{name}/allowed-tools  {"tools": ["docker_ps", "docker_logs", ...], "reason": "..."}
GET /api/servers/{name}/access-history
```
The change is written back to `config/servers.yaml` and appended to `var/access-changes.jsonl`.
In prod, PUT needs `X-Service-Token` (only platform-api calls it, after checking the user has `servers.manage`: devops or admin)
and `X-User`. Unknown tools and `ssh_exec` on a prod server are refused (422).
A tool that is not in a server's list is rejected before the developer is even asked.

## Check

```bash
uv run pytest        # domain + use case tests
uv run lint-imports  # architecture rules (layers, module boundaries, pure domain)
```

## Prod settings

| variable | |
|---|---|
| `SUPERAI_MODE=prod` | real SSH, approvals and run tokens from platform-api |
| `SUPERAI_PLATFORM_URL` | e.g. `http://platform-api:8000` |
| `SUPERAI_SERVICE_TOKEN` | shared secret with platform-api (Vault) |
| `SUPERAI_SSH_KEY`, `SUPERAI_KNOWN_HOSTS` | private key of the `deploy` user, pinned host keys |
| `SUPERAI_DATABASE_URL` | Postgres (required in prod). Servers, access changes and the audit log live there |
| `SUPERAI_SERVERS_FILE` | YAML that seeds an empty database (default `config/servers.yaml`) |
| `SUPERAI_ACCESS_LOG`, `SUPERAI_AUDIT_FILE`, `SUPERAI_REGISTRY` | optional; the two files are used only without a database |
