FROM python:3.11-slim

RUN pip install --no-cache-dir uv
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so they're cached across rebuilds that only touch app code.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY agent/ agent/
COPY storage/ storage/
COPY compliance/ compliance/
RUN uv sync --frozen --no-dev

# VAD + turn-detector model weights, fetched once at build time so the
# running container never needs network access to HuggingFace.
RUN uv run -m livekit.agents download-files

CMD ["uv", "run", "python", "-m", "agent.worker", "start"]
