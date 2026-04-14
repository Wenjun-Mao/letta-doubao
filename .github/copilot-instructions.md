# Project Guidelines

## Code Style
- Use Python 3.12+ and manage dependencies with `uv` (`pyproject.toml`, `uv.lock`).
- For network/SDK calls in Python, follow the retry pattern used in `utils/agent_platform_service.py` (`tenacity`).
- Keep API contracts typed (Pydantic models in `dev_ui/main.py`) and prefer shared service wrappers in `utils/` over route-level SDK logic.
- For frontend changes in `frontend-ade/`, follow existing Next.js App Router + TypeScript patterns.

## Architecture
- Runtime stack is Docker Compose: Postgres + pgvector, Redis, Letta server, FastAPI `dev_ui`, and Next.js `frontend-ade`.
- Backend API surface lives in `dev_ui/main.py`; reusable Letta operations live in `utils/`.
- Prompt and persona assets live in `prompts/system_prompts/` and `prompts/persona/`.
- Tests are role-based:
  - `tests/checks/`: focused diagnostics and smoke checks
  - `tests/runners/`: config/scenario-driven runs with artifacts in `tests/outputs/`

## Build and Test
- Install Python dependencies: `uv sync`
- Start stack: `docker compose up -d`
- Reset database for a clean state:
  - Windows: `./scripts/reset_database.ps1`
  - Linux/macOS: `./scripts/reset_database.sh`
- Core validations (run based on scope):
  - `uv run tests/checks/agent_bootstrap_check.py`
  - `uv run tests/checks/platform_api_e2e_check.py`
  - `uv run tests/checks/ade_mvp_smoke_e2e_check.py`
  - `uv run tests/checks/platform_dual_run_gate.py`
- Frontend build validation: `npm --prefix frontend-ade run build`

## Conventions
- Letta model handles for OpenAI-compatible providers must use `openai-proxy/<model-id>` (not `openai/<model-id>`).
- Default embedding handle is `letta/letta-free` unless a task explicitly changes embedding strategy.
- Use `MARIMO_SMOKE_ONLY=1` when running notebook `.py` files as non-UI smoke tests.
- Preserve startup determinism:
  - Keep `init.sql` bootstrap behavior intact unless migration work requires coordinated changes.
  - Respect local NLTK/offline startup handling in `docker/sitecustomize.py` and `data/nltk_data` mounts.
- Prefer updating linked docs below rather than embedding long runbooks into code comments.

## References
- Onboarding and run flow: `README.md`
- Design decisions and troubleshooting: `MANUAL.md`
- Script catalog and command examples: `scripts/README.md`
- Test layout and runner/check behavior: `tests/README.md`
- API docs workflow and OpenAPI source: `docs/index.mdx`, `docs/openapi/agent-platform-openapi.json`
- ADE scope and rollout status: `docs/ade-frontend-scope.mdx`, `docs/agent_platform_milestone_status.md`