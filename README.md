# Letta + Doubao Standalone Bundle

This directory is self-contained. You can copy `standalone/letta-doubao` anywhere and run it without the rest of the Letta repo.

## What It Uses

- pinned upstream Letta image (`letta/letta:0.16.7` by default, overridable via `LETTA_SERVER_IMAGE`)
- `pgvector/pgvector:0.8.1-pg15` for Postgres + pgvector
- `redis:7-alpine` for an explicit external Redis dependency
- Doubao Ark through Letta's OpenAI-compatible provider path
- Letta's built-in `letta/letta-free` embedding handle for agent memory
- prebuilt Agent Platform API image from GHCR (`AGENT_PLATFORM_API_IMAGE`)

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
   `AGENT_PLATFORM_MODEL_SOURCES` is the shared ADE model catalog used by both Agent Studio and Comment Lab, while the Letta bootstrap variables remain dedicated to the upstream `letta_server`.
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
- `agent_platform_api` uses a prebuilt image (`AGENT_PLATFORM_API_IMAGE`)

The GitHub Actions workflow that publishes `agent_platform_api` to GHCR is:

- `.github/workflows/publish-agent-platform-api-ghcr.yml`

Workflow behavior:

- on push to `main` (for relevant files), it pushes branch and `sha-*` tags
- on git tag like `v1.2.3`, it pushes a matching version tag
- it also updates `latest` on the default branch

Remote Ubuntu run sequence (no local build required):

```bash
docker compose pull letta_server agent_platform_api
docker compose up -d
```

For this pull-first model, avoid `--build` on remote unless you intentionally want to rebuild locally.

Set these in `.env` (or copy from `.env.example`) for image control:

- `LETTA_SERVER_IMAGE=letta/letta:0.16.7`
- `AGENT_PLATFORM_API_IMAGE=ghcr.io/wenjun-mao/agent-platform-api:latest`

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
docker compose up -d --force-recreate letta_server
```

`compose.yaml` mounts `data/nltk_data` into the Letta container and enables a startup patch that prefers local `punkt_tab` data instead of network download.

If `agent_platform_api` logs show runtime dependency install lines like `Creating virtual environment at: /opt/venv` or `Downloading pydantic-core`, pull the latest prebuilt image and recreate `agent_platform_api`:

```bash
docker compose pull agent_platform_api
docker compose up -d --force-recreate agent_platform_api
```

After this, `agent_platform_api` should start directly with Uvicorn and no startup-time package download.

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

- Default system prompt baseline: `CHAT_V20260418_PROMPT`
- Default test embedding: `letta/letta-free`

Testing runners live under `tests/`:

```bash
uv run tests/runners/persona_guardrail_runner.py --config tests/configs/suites --embedding letta/letta-free
uv run tests/checks/provider_embedding_matrix_check.py
uv run tests/checks/prompt_strategy_check.py
uv run tests/checks/agent_bootstrap_check.py
uv run tests/checks/platform_flag_gate_check.py
uv run tests/runners/memory_update_runner.py --rounds 10 --model lmstudio_openai/gemma-4-31b-it --embedding letta/letta-free
```

Test outputs are grouped by runner type under `tests/outputs/`:

- Persona guardrail:
	- Run folders under `tests/outputs/persona_guardrail/<run_tag>/`
	- Index files: `tests/outputs/persona_guardrail/run_index.csv`, `tests/outputs/persona_guardrail/run_index.jsonl`
- Memory update:
	- Run folders under `tests/outputs/memory_update/<run_tag>/`
	- Index files: `tests/outputs/memory_update/run_index.csv`, `tests/outputs/memory_update/run_index.jsonl`

This avoids mixing different test semantics in one shared index.

## Agent Platform API (Initial Slice)

`agent_platform_api/main.py` now exposes the control/runtime surface under `/api/v1/platform`.

- `GET /api/v1/platform/capabilities`
	- Reports whether the connected Letta SDK/server supports key mutable features.
- `POST /api/v1/platform/agents/{agent_id}/messages`
	- Sends a runtime message with optional `override_model` and `override_system`.
- `PATCH /api/v1/platform/agents/{agent_id}/system`
	- Updates the persisted agent system prompt.
- `PATCH /api/v1/platform/agents/{agent_id}/model`
	- Updates the persisted default model handle for the agent.
- `PATCH /api/v1/platform/agents/{agent_id}/core-memory/blocks/{block_label}`
	- Updates a core-memory block value (for example `persona` or `human`).
- `PATCH /api/v1/platform/agents/{agent_id}/tools/attach/{tool_id}`
	- Attaches a tool to an existing agent.
- `PATCH /api/v1/platform/agents/{agent_id}/tools/detach/{tool_id}`
	- Detaches a tool from an existing agent.
- `GET /api/v1/platform/test-runs`
	- Lists orchestrated backend test runs.
- `POST /api/v1/platform/test-runs`
	- Starts one orchestrated check/runner execution.
- `GET /api/v1/platform/test-runs/{run_id}`
	- Retrieves run status, tail logs, and exit code.
- `POST /api/v1/platform/test-runs/{run_id}/cancel`
	- Requests cancellation for a running test job.

- `GET /api/v1/platform/tools`
	- Lists available platform tools for ADE Toolbench discovery.
- `GET /api/v1/platform/metadata/prompts-personas`
	- Returns prompt and persona metadata for ADE Prompt and Persona Lab selectors.
- `GET /api/v1/platform/test-runs/{run_id}/artifacts`
	- Lists discovered artifacts for a test run (logs, summaries).
- `GET /api/v1/platform/test-runs/{run_id}/artifacts/{artifact_id}`
	- Reads artifact content with configurable line limits.

Quick capability check:

```bash
curl http://127.0.0.1:8284/api/v1/platform/capabilities
```

Platform API end-to-end check:

```bash
uv run tests/checks/platform_api_e2e_check.py
```

ADE MVP smoke check:

```bash
uv run tests/checks/ade_mvp_smoke_e2e_check.py
```

Dual-run cutover gate (backend E2E + ADE smoke):

```bash
uv run tests/checks/platform_dual_run_gate.py
```

If your running `agent_platform_api` service is on an older image, run checks against a source-backed instance:

```bash
$env:AGENT_PLATFORM_API_BASE_URL="http://127.0.0.1:8285"
uv run tests/checks/platform_dual_run_gate.py
```

## OpenAPI And Self-Hosted Docs Workflow

The repository now uses a self-hosted documentation workflow inside the ADE frontend.

- OpenAPI source artifact: `docs/openapi/agent-platform-openapi.json`
- Frontend OpenAPI artifact (served to Scalar): `frontend-ade/public/openapi/agent-platform-openapi.json`
- Chinese OpenAPI artifact: `docs/openapi/agent-platform-openapi-zh.json`
- Chinese docs pages: `docs/zh/`
- OpenAPI export/sync script: `scripts/export_openapi.py`
- Manual zh OpenAPI script: `scripts/generate_openapi_zh_manual.py`
- Missing-term report: `docs/openapi/zh_openapi_missing_terms.json`

Generate/update the OpenAPI artifact:

```bash
uv run python scripts/export_openapi.py
```

Check OpenAPI drift only:

```bash
uv run python scripts/export_openapi.py --check --output docs/openapi/agent-platform-openapi.json
```

Regenerate Chinese OpenAPI artifact (manual curated labels):

```bash
uv run python scripts/generate_openapi_zh_manual.py
```

The script writes `docs/openapi/zh_openapi_missing_terms.json`, so future updates are incremental: add only the newly introduced terms/mappings and rerun.

Update Chinese docs pages manually under `docs/zh/` when major changes land.

## ADE Frontend (Separate Profile)

The legacy in-package frontend has been removed. The Next.js ADE app is now the active UI and talks to `agent_platform_api` as its backend.

Start ADE frontend profile:

```bash
docker compose --profile ade up -d ade_frontend
```

Stop ADE frontend profile service:

```bash
docker compose --profile ade stop ade_frontend
```

Open ADE preview at `http://127.0.0.1:3000`.
