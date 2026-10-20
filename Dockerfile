# Shared image for the backend and worker services (Stretch S2) -- same
# dependencies, just a different `command:` per service in docker-compose.yml.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Dependencies first, cached independently of application code (AGENTS.md
# S2: "copy pyproject.toml and uv.lock, then uv sync --frozen").
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .

# VAD/turn-detector model weights the worker needs at runtime -- baked in at
# build time so `docker compose up` doesn't fetch (or race on) them per run.
RUN uv run python -m livekit.agents download-files

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
