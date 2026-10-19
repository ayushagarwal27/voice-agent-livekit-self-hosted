FROM python:3.11-slim

RUN pip install --no-cache-dir uv
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so they're cached across rebuilds that only touch app code.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ backend/
COPY storage/ storage/
COPY web/ web/
COPY scripts/ scripts/
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
