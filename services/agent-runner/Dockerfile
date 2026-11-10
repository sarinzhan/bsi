# BSI agent-runner: the image of every agent container (one per run). Started by platform-api.
# Build from the REPO ROOT (it bundles the agent's instructions from agent/):
#   docker build -f services/agent-runner/Dockerfile -t registry/bsi/agent-runner:<version> .

FROM ghcr.io/astral-sh/uv:0.9.26 AS uv
FROM python:3.13.9-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY services/agent-runner/pyproject.toml services/agent-runner/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/agent-runner/src ./src
RUN uv sync --frozen --no-dev --no-editable

# platform-api runs it as 1000:1000 with a read-only root filesystem, no capabilities, /tmp and /workspace in memory
FROM python:3.13.9-slim-bookworm
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY agent /app/prompts
# readable by 1000:1000 whatever the file modes were where the image was built (e.g. 0600 on a laptop)
RUN chmod -R a+rX /app/prompts
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    BSI_PROMPTS_DIR=/app/prompts
USER 1000:1000
CMD ["python", "-m", "agent_runner"]
