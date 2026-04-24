FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY model_router ./model_router
COPY utils ./utils
COPY agent_platform_api/catalog_data ./agent_platform_api/catalog_data

EXPOSE 8290

CMD ["/app/.venv/bin/uvicorn", "model_router.app:app", "--host", "0.0.0.0", "--port", "8290"]
