# Letta + Doubao Standalone Bundle

This directory is self-contained. You can copy `standalone/letta-doubao` anywhere and run it without the rest of the Letta repo.

## What It Uses

- `letta/letta:latest` for the Letta server
- `pgvector/pgvector:0.8.1-pg15` for Postgres + pgvector
- `redis:7-alpine` for an explicit external Redis dependency
- Doubao Ark through Letta's OpenAI-compatible provider path
- Letta's built-in `letta/letta-free` embedding handle for agent memory

## Why Redis Is Explicit In Compose

Letta can start an internal Redis process when `LETTA_REDIS_HOST` is unset. That is what produces the log line:

- `No external Redis configuration detected, starting internal Redis...`

That line is normal by itself. It does not prove a failure. This standalone bundle now provides Redis as a separate Compose service anyway, because it is easier to debug, makes startup more deterministic across hosts, and avoids relying on the image's in-container Redis bootstrap path.

## Why The Embedding Handle Is Not Doubao

The tested Ark key worked for:

- `GET /models`
- `POST /chat/completions`
- OpenAI-style tool calling

The same key did not expose a usable text embedding model through the tested OpenAI-compatible `/embeddings` path, so the end-to-end Letta stack uses Doubao for the chat model and Letta's built-in embedding service for embeddings.

## Quick Start

1. Review `.env` or copy `.env.example` to `.env` and update values.
2. Start the stack:

```powershell
docker compose up -d
```

3. Confirm all three services become healthy:

```powershell
docker compose ps
```

4. Install the notebook dependencies with `uv`:

```powershell
uv sync
```

5. Run the direct Doubao smoke test from the marimo notebook file:

```powershell
$env:MARIMO_SMOKE_ONLY="1"
uv run python notebooks\01_doubao_api_smoke.py
Remove-Item Env:MARIMO_SMOKE_ONLY
```

6. Run the end-to-end Letta smoke test from the marimo notebook file:

```powershell
$env:MARIMO_SMOKE_ONLY="1"
uv run python notebooks\02_letta_e2e.py
Remove-Item Env:MARIMO_SMOKE_ONLY
```

7. Open either notebook interactively in marimo if you want the UI:

```powershell
uv run marimo run notebooks\01_doubao_api_smoke.py --headless
uv run marimo run notebooks\02_letta_e2e.py --headless
```

8. Read [MANUAL.md](./MANUAL.md) before making changes or moving this directory. It captures the decisions, verified behavior, rejected paths, and next-step guidance so the setup can be reconstructed later without redoing the same investigation.

## Troubleshooting

If `curl http://127.0.0.1:8283/openapi.json` connects and then resets, check these first:

```powershell
docker compose ps
docker compose logs --tail=200 letta_server
docker compose logs --tail=100 redis
```

If the stack is healthy, the OpenAPI route should respond cleanly:

```powershell
curl http://127.0.0.1:8283/openapi.json
```

## Files

- `compose.yaml`: standalone Letta + Postgres + Redis stack
- `init.sql`: database bootstrap for the Letta schema and pgvector extension
- `.env.example`: sanitized config template
- `.env`: local runtime config
- `pyproject.toml`: `uv` dependency manifest for the notebooks
- `uv.lock`: `uv` lockfile
- `.dockerignore`: future-proof build-context filter
- `MANUAL.md`: detailed decision log and handoff guide
- `notebooks/01_doubao_api_smoke.py`: direct Ark/Doubao validation
- `notebooks/02_letta_e2e.py`: Letta end-to-end validation against the running stack