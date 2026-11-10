# Deploying BSI

Two VMs (stage 1). Architecture and security model: [../docs/architecture.md](../docs/architecture.md).

Simplest start, by hand on one server (git pull + docker compose, login in the server's nginx):
[single-vm/README.md](single-vm/README.md).

```
bsi-app     platform-api (holds the SSH key), web (nginx, HTTPS)   deploy/bsi-app/compose.yml
bsi-runner  Docker only: one agent container per run             deploy/bsi-runner/README.md
Postgres    company managed (or its own VM): database "platform"
```

## Images (built by CI, tagged with the release version, never `latest`)

| image | from |
|---|---|
| `registry/bsi/platform-api:<v>` | `services/platform-api/Dockerfile` |
| `registry/bsi/web:<v>` | `web/Dockerfile` |
| `registry/bsi/agent-runner:<v>` | `services/agent-runner/Dockerfile` (build from the repo root) |

## Variables for `docker compose -f deploy/bsi-app/compose.yml`

| variable | example |
|---|---|
| `BSI_VERSION` | `1.4.0` |
| `REGISTRY` | `registry.beeline.example` |
| `BSI_APP_HOST` | `bsi-app.internal` (how agent containers reach this VM) |
| `BSI_APP_PRIVATE_IP` | `10.40.0.10` (port 8000 is published here only) |
| `BSI_RUNNER_HOST` | `bsi-runner.internal` |

Secrets are files on the host, rendered from Vault (list at the top of `bsi-app/compose.yml`).

## Firewall of bsi-app

| from | port | |
|---|---|---|
| users (company network / VPN) | 443 | web + `/api` |
| bsi-runner | 8000 | agent containers: `/runner`, `/mcp` |
| everything else | — | blocked |

Out: platform-api → target servers :22, bsi-runner :2376 and the Anthropic API :443,
→ Postgres. Target servers accept SSH only from bsi-app.

## Database migrations

Each service runs `alembic upgrade head` on start (with a lock, safe for several copies).

## Not ready for prod yet

- **Company SSO**: in prod mode every web request is 401 until sign-in is wired.
- **Model proxy**: until platform-api proxies model calls, the Anthropic API key is passed into every agent
  container and the containers need egress to `api.anthropic.com`. AI-written code in a container could read
  the key. Acceptable for a pilot on read-only tools; fix before the agent writes and runs code.

Until then, run the local stack (`docker compose up` at the repo root), which uses dev mode.
