FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy

WORKDIR /app

# Install runtime dependencies at build time so container startup is instant.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy runtime source required by the Agent Platform API service.
COPY agent_platform_api ./agent_platform_api
COPY utils ./utils
COPY prompts ./prompts
COPY tests ./tests

CMD ["/opt/venv/bin/uvicorn", "agent_platform_api.main:app", "--host", "0.0.0.0", "--port", "8284"]

