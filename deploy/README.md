# Deploying superAI

Two VMs (stage 1). Architecture and security model: [../docs/architecture.md](../docs/architecture.md).

```
bsi-app     platform-api, server-tools, web (nginx, HTTPS)      deploy/bsi-app/compose.yml
bsi-runner  Docker only: one agent container per run             deploy/bsi-runner/README.md
Postgres    company managed (or its own VM): databases "platform" and "server_tools", one login each
```

## Images (built by CI, tagged with the release version, never `latest`)

| image | from |
|---|---|
| `registry/superai/platform-api:<v>` | `services/platform-api/Dockerfile` |
| `registry/superai/server-tools:<v>` | `services/server-tools/Dockerfile` |
| `registry/superai/web:<v>` | `web/Dockerfile` |
| `registry/superai/agent-runner:<v>` | not built yet (next step) |

## Variables for `docker compose -f deploy/bsi-app/compose.yml`

| variable | example |
|---|---|
| `BSI_VERSION` | `1.4.0` |
| `REGISTRY` | `registry.beeline.example` |
| `BSI_APP_HOST` | `bsi-app.internal` (how agent containers reach this VM) |
| `BSI_APP_PRIVATE_IP` | `10.40.0.10` (ports 8000/8100 are published here only) |
| `BSI_RUNNER_HOST` | `bsi-runner.internal` |

Secrets are files on the host, rendered from Vault (list at the top of `bsi-app/compose.yml`).

## Firewall of bsi-app

| from | port | |
|---|---|---|
| users (company network / VPN) | 443 | web + `/api` |
| bsi-runner | 8000, 8100 | agent containers: `/runner`, `/mcp` |
| everything else | — | blocked |

Out: server-tools → target servers :22, platform-api → bsi-runner :2376 and the Anthropic API :443,
both → Postgres. Target servers accept SSH only from bsi-app.

## Database migrations

Each service runs `alembic upgrade head` on start (with a lock, safe for several copies).

## Not ready for prod yet

- **Company SSO**: in prod mode every web request is 401 until sign-in is wired.
- **Approval module**: in prod mode server-tools asks platform-api `POST /internal/approvals`, which does
  not exist yet, so every tool call is **denied** (the safe default).
- **agent-runner image** and the model proxy.

Until then, run the local stack (`docker compose up` at the repo root), which uses dev mode.
