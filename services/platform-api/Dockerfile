# superAI platform-api. Main backend: users and roles, agent runs.
# Build from this folder:  docker build -t registry/superai/platform-api:<version> .

# ---- build: install locked dependencies + the app into /app/.venv ----
FROM ghcr.io/astral-sh/uv:0.9.26 AS uv
FROM python:3.13.9-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# dependencies first: this layer is cached until uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# ---- runtime: only the virtualenv, the seed config and a non-root user ----
FROM python:3.13.9-slim-bookworm
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin superai \
 && mkdir -p /app/var && chown superai /app/var
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY config ./config
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    SUPERAI_USERS_FILE=/app/config/users.yaml \
    SUPERAI_ROLE_LOG=/app/var/role-changes.jsonl
USER superai
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
# One worker: the MCP session manager and the run reaper live in the process. Scale with more containers.
CMD ["uvicorn", "platform_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
