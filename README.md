# Letta + Doubao Standalone Bundle

This directory is self-contained. You can copy `standalone/letta-doubao` anywhere and run it without the rest of the Letta repo.

## What It Uses

- pinned upstream Letta image (`letta/letta:0.16.7` by default, overridable via `LETTA_SERVER_IMAGE`)
- `pgvector/pgvector:0.8.1-pg15` for Postgres + pgvector
- `redis:7-alpine` for an explicit external Redis dependency
- Doubao Ark through Letta's OpenAI-compatible provider path
- Letta's built-in `letta/letta-free` embedding handle for agent memory
- prebuilt Web UI image from GHCR (`DEV_UI_IMAGE`)

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

## Option A Deployment (GHCR + Pinned Upstream Letta)

This repo now supports a pull-first deployment model:

- `letta_server` uses a pinned upstream image (`LETTA_SERVER_IMAGE`)
- `dev_ui` uses a prebuilt image (`DEV_UI_IMAGE`)

The GitHub Actions workflow that publishes `dev_ui` to GHCR is:

- `.github/workflows/publish-dev-ui-ghcr.yml`

Workflow behavior:

- on push to `main` (for relevant files), it pushes branch and `sha-*` tags
- on git tag like `v1.2.3`, it pushes a matching version tag
- it also updates `latest` on the default branch

Remote Ubuntu run sequence (no local build required):

```bash
docker compose --env-file .env3 pull letta_server dev_ui
docker compose --env-file .env3 up -d
```

For this pull-first model, avoid `--build` on remote unless you intentionally want to rebuild locally.

Set these in `.env3` (or copy from `.env3.example`) for image control:

- `LETTA_SERVER_IMAGE=letta/letta:0.16.7`
- `DEV_UI_IMAGE=ghcr.io/wenjun-mao/letta-doubao-dev-ui:latest`

If you keep the GHCR package public, remote hosts can pull without registry credentials.

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

If startup repeatedly stalls around `Checking NLTK data availability...`, pre-seed NLTK once and restart:

```bash
chmod +x scripts/seed_nltk_data.sh
./scripts/seed_nltk_data.sh
docker compose --env-file .env3 up -d --force-recreate letta_server
```

`compose.yaml` mounts `data/nltk_data` into the Letta container and enables a startup patch that prefers local `punkt_tab` data instead of network download.

If `dev_ui` logs show runtime dependency install lines like `Creating virtual environment at: /opt/venv` or `Downloading pydantic-core`, pull the latest prebuilt image and recreate `dev_ui`:

```bash
docker compose --env-file .env3 pull dev_ui
docker compose --env-file .env3 up -d --force-recreate dev_ui
```

After this, `dev_ui` should start directly with Uvicorn and no startup-time package download.

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

## Developer Testing Workflow

Current baseline assumptions for development tests:

- Default system prompt baseline: `MEMGPT_V2_CHAT_PROMPT`
- Default test embedding: `letta/letta-free`

Testing runners live under `tests/`:

```bash
uv run tests/run_conversation_suite.py --config tests/configs/suites --embedding letta/letta-free
uv run tests/test_provider_embedding_matrix.py
uv run tests/test_prompts.py
uv run tests/verify_agent.py
```

Conversation suite outputs are written to timestamped directories under `tests/outputs/`.
For quick historical review, a lean central index is appended on each run:

- `tests/outputs/run_index.csv`
- `tests/outputs/run_index.jsonl`

These index files capture run time, suite/config, pass/fail, durations, and result artifact paths.